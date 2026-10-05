"""Audio-token / embedding extraction for language-model integration.

The audio Transformer encoder already organises patch tokens and a pooled
class embedding in an ordered, shared space (\"the encoder serves to organize
embedding/token classes\"). This module extracts those vectors from a trained
head so a downstream model can consume them — e.g. a frozen encoder + linear
projection into an LLM embedding space, or the patch-token sequence fed like
input tokens to a decoder-only model.

Usage (script):
  python scripts/extract_embeddings.py --out-dir runs/embeddings
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional

import numpy as np
import torch
import torch.nn as nn

ML = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ml/cardia/features -> up 2 = ml
if ML not in sys.path:
    sys.path.insert(0, ML)

from cardia.config import Config, HEART_TYPES  # noqa: E402
from cardia.data.hls_cmds import build_task_manifest  # noqa: E402
from cardia.data.splits import load_splits  # noqa: E402
from cardia.data.transforms import MelSpec, preprocess  # noqa: E402
from cardia.models.transformer import ASTSmall, build_transformer  # noqa: E402


def load_ast(ckpt: str, num_classes: int, device: torch.device) -> "ASTSmall":
    cfg = Config(task="heart", stage=4, model="transformer", class_scheme="10class")
    net = build_transformer(cfg, num_classes).to(device)
    sd = torch.load(ckpt, map_location=device)["model_state"]
    if "_pos" in sd:
        net._pos = nn.Parameter(sd["_pos"].to(device))
    net.load_state_dict(sd)
    net.eval()
    return net


def clip_embeddings(net: "ASTSmall", cfg: Config, path: str, device: torch.device):
    """Encode one clip into (patch_tokens (1,T,d), cls (1,d))."""
    wav = preprocess(path, cfg)
    mel = MelSpec(cfg.sample_rate, cfg.n_mels, cfg.n_fft, cfg.hop_length)
    spec = mel(wav).unsqueeze(0).unsqueeze(0).to(device)
    with torch.no_grad():
        tokens, cls = net.encode(spec)
    return tokens, cls


def corpus_embeddings(data_dir: str, out_dir: str, seed: int = 0,
                      device: Optional[torch.device] = None) -> Dict:
    """Compute CLS embeddings + labels for the heart-10class test fold."""
    device = device or torch.device("cpu")
    cfg = Config(task="heart", stage=4, model="transformer", class_scheme="10class",
                 data_dir=data_dir, out_dir=out_dir, seed=seed, device=str(device))
    manifest = build_task_manifest(data_dir, "heart", "10class", os.path.join(out_dir, "manifests"))
    split_dir = os.path.join(out_dir, "splits", f"heart_10class_s{seed}")
    splits = load_splits(split_dir, n_folds=cfg.n_folds)
    test_ids = splits[0].test
    test = manifest.set_index("sample_id").loc[test_ids].reset_index()
    import glob

    ok = sorted(glob.glob(os.path.join(out_dir, "checkpoints",
                                       "stage4-heart-transformer-10class-allfolds-s0-fold0_best.pt")))
    if not ok:
        raise FileNotFoundError(f"no heart-10class transformer checkpoint under {out_dir}/checkpoints")
    net = load_ast(ok[0], len(HEART_TYPES), device)
    rows = {"sample_id": [], "label": [], "cls": []}
    for _, r in test.iterrows():
        _, cls = clip_embeddings(net, cfg, r["file_path"], device)
        rows["sample_id"].append(r["sample_id"])
        rows["label"].append(r["task_label"])
        rows["cls"].append(cls[0].cpu().numpy())
    return {"device": str(device), "rows": rows, "classes": HEART_TYPES}


def class_mean_matrix(rows: Dict) -> np.ndarray:
    """Cosine similarity (C x C) between per-class mean CLS embeddings."""
    cls_by_label: Dict[str, List[np.ndarray]] = {}
    for label, vec in zip(rows["rows"]["label"], rows["rows"]["cls"]):
        cls_by_label.setdefault(label, []).append(vec)
    means = []
    for c in rows["classes"]:
        arr = np.stack(cls_by_label.get(c, [np.zeros_like(rows["rows"]["cls"][0])])).mean(axis=0)
        arr = arr / (np.linalg.norm(arr) + 1e-9)
        means.append(arr)
    M = np.stack(means)
    return M @ M.T