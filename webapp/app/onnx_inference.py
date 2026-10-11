"""ONNX Runtime inference backend (CPU, quantized heads).

Drop-in alternative to `inference.HeadModel` for the cloud worker and the
desktop app: heads run as quantized ONNX graphs exported by
`cardia.export.onnx_serve`, while preprocessing reuses the exact DSP in
`cardia.data.transforms` so probabilities match the torch path.

Selected by `ASCULTO_BACKEND=onnx` (default `torch`). Manifest location comes
from `ASCULTO_ONNX_DIR` (default `ml/runs/onnx_serve`).
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

import numpy as np
import torch

from . import config

ML = config.ML
import sys  # noqa: E402

if ML not in sys.path:
    sys.path.insert(0, ML)

from cardia.config import Config  # noqa: E402
from cardia.data.transforms import MelSpec, band_pass, peak_normalize, _fixed_length  # noqa: E402


def _onnx_dir() -> str:
    return os.environ.get("ASCULTO_ONNX_DIR", os.path.join(ML, "runs", "onnx_serve"))


def load_manifest(onnx_dir: Optional[str] = None) -> Dict:
    path = os.path.join(onnx_dir or _onnx_dir(), "onnx_manifest.json")
    with open(path) as f:
        return json.load(f)


class OnnxHead:
    """One prediction head served from a quantized ONNX ensemble graph."""

    def __init__(self, head: config.Head, entry: Dict, onnx_dir: str,
                 threads: Optional[int] = None) -> None:
        import onnxruntime as ort

        self.head = head
        self.cfg = Config(
            task=head.task, stage=head.stage, model=head.model, class_scheme=head.scheme,
            seed=config.SEED, data_dir=config.DATA_DIR, out_dir=head.out_dir, device="cpu",
        )
        self.mel = MelSpec(self.cfg.sample_rate, self.cfg.n_mels, self.cfg.n_fft, self.cfg.hop_length)
        path = os.path.join(onnx_dir, entry["served"]["file"])
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(threads or os.environ.get("ASCULTO_ONNX_THREADS", "0")) or 0
        self.sess = ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"])
        self.input_name = self.sess.get_inputs()[0].name
        self.classes = list(entry.get("classes") or head.classes)
        self.entry = entry

    @property
    def ready(self) -> bool:
        return self.sess is not None

    # ---------------------------------------------------------------- preprocess
    def preprocess(self, wav: torch.Tensor, sr: int) -> torch.Tensor:
        import torchaudio

        if sr != self.cfg.sample_rate:
            wav = torchaudio.functional.resample(wav, sr, self.cfg.sample_rate)
        wav = peak_normalize(wav)
        wav = band_pass(wav, self.cfg.sample_rate, self.cfg.band_low, self.cfg.band_high)
        return _fixed_length(wav, self.cfg.max_samples)

    def _prep_window(self, w: torch.Tensor, sr: int) -> torch.Tensor:
        import torch.nn.functional as F
        import torchaudio

        if sr != self.cfg.sample_rate:
            w = torchaudio.functional.resample(w, sr, self.cfg.sample_rate)
        w = peak_normalize(w)
        w = band_pass(w, self.cfg.sample_rate, self.cfg.band_low, self.cfg.band_high)
        if self.head.stage == 4:
            w = _fixed_length(w, self.cfg.max_samples)
        elif w.shape[0] < self.cfg.n_fft:
            w = F.pad(w, (0, self.cfg.n_fft - w.shape[0]))
        return w

    def _infer(self, filt: torch.Tensor) -> np.ndarray:
        spec = self.mel(filt).unsqueeze(0).unsqueeze(0).numpy().astype(np.float32)
        return np.asarray(self.sess.run(None, {self.input_name: spec})[0][0], dtype=float)

    # ------------------------------------------------------------------- predict
    def predict(self, wav: torch.Tensor, sr: int) -> Dict:
        filt = self.preprocess(wav, sr)
        probs = self._infer(filt)
        pred_idx = int(probs.argmax())
        return {
            "key": self.head.key, "label": self.head.label, "kind": self.head.kind,
            "classes": self.classes, "probs": probs.tolist(),
            "pred": self.classes[pred_idx], "pred_index": pred_idx,
            "confidence": float(probs[pred_idx]),
            "n_models": self.entry.get("folds", 1), "filtered": filt,
        }

    def predict_series(self, wav: torch.Tensor, sr: int, window_s: float = 3.0,
                       hop_s: float = 0.5) -> Dict:
        W = max(int(window_s * sr), 1)
        H = max(int(hop_s * sr), 1)
        n = int(wav.shape[0])
        starts = [0] if n <= W else list(range(0, n - W + 1, H))
        times, probs = [], []
        for s in starts:
            f = self._prep_window(wav[s:s + W], sr)
            times.append((s + W / 2.0) / sr)
            probs.append(self._infer(f))
        return {"key": self.head.key, "label": self.head.label, "classes": self.classes,
                "times": times, "probs": np.asarray(probs).tolist(),
                "window_s": window_s, "hop_s": hop_s}

    def predict_multiscale(self, wav: torch.Tensor, sr: int,
                           scales: List[float] = (1.0, 3.0, 15.0)) -> Dict:
        scale_series = []
        for sc in scales:
            hop = max(0.25, round(sc / 4.0, 2)) if sc < 15 else sc
            ser = self.predict_series(wav, sr, window_s=sc, hop_s=hop)
            scale_series.append({"scale_s": sc, "times": ser["times"], "probs": ser["probs"]})
        macro = self.predict(wav, sr)
        acc = np.zeros(len(self.classes))
        wsum = 0.0
        for s in scale_series:
            acc += s["scale_s"] * np.asarray(s["probs"]).mean(axis=0)
            wsum += s["scale_s"]
        fused = acc / max(wsum, 1e-9)
        return {"key": self.head.key, "label": self.head.label, "classes": self.classes,
                "scales": scale_series,
                "macro": {"probs": macro["probs"], "pred": macro["pred"],
                          "confidence": macro["confidence"]},
                "fused": {"probs": fused.tolist(), "pred": self.classes[int(fused.argmax())],
                          "confidence": float(fused.max())}}


class OnnxRegistry:
    """Registry mirroring `inference.Registry` but backed by ONNX sessions."""

    def __init__(self, onnx_dir: Optional[str] = None) -> None:
        self.device = torch.device("cpu")
        self.onnx_dir = onnx_dir or _onnx_dir()
        self.heads: Dict[str, OnnxHead] = {}
        self.errors: Dict[str, str] = {}

    def load(self) -> None:
        try:
            manifest = load_manifest(self.onnx_dir)
        except Exception as e:
            self.errors["_manifest"] = f"{type(e).__name__}: {e}"
            return
        by_key = {h["key"]: h for h in manifest.get("heads", [])}
        for head in config.model_registry():
            entry = by_key.get(head.key)
            if entry is None:
                self.errors[head.key] = "not in ONNX manifest"
                continue
            try:
                self.heads[head.key] = OnnxHead(head, entry, self.onnx_dir)
            except Exception as e:  # pragma: no cover - defensive
                self.errors[head.key] = f"{type(e).__name__}: {e}"

    def get(self, key: str) -> Optional[OnnxHead]:
        return self.heads.get(key)

    def available(self) -> List[str]:
        return [k for k, h in self.heads.items() if h.ready]
