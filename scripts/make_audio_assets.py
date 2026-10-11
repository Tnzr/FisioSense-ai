#!/usr/bin/env python3
"""Export a compact set of demo clips (raw + band-passed) for the README's
embedded-audio section into docs/assets/audio/.

The clips are re-encoded at PLAYBACK_SR (22.05 kHz) with gentle compression:
the source recordings are 4 kHz WAVs which play fine in Audacity but decode as
silence in HTML5 `<audio>` and many native players, and their peak-normalised
heart sounds are quiet on laptop speakers.

Usage:
  python scripts/make_audio_assets.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ml"))

import numpy as np
import soundfile as sf
import torch
import torchaudio

from cardia.config import Config
from cardia.data.hls_cmds import build_task_manifest
from cardia.data.transforms import load_wav, peak_normalize, preprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "assets", "audio")
os.makedirs(OUT, exist_ok=True)
cfg = Config()

DATA = os.environ.get("ASCULTO_DATA_DIR", cfg.data_dir)

PLAYBACK_SR = 22050


def to_playback(w, sr, target_db=-14.0, thresh_db=-24.0, ratio=3.0):
    """Lift quiet demo clips and re-encode at a standard sample rate.

    Compression (3:1 above -24 dBFS) + gain to ~-14 dBFS RMS + soft-limit
    make the peak-normalised heart sounds clearly audible; resampling to
    22.05 kHz avoids the silent playback of 4 kHz WAVs in strict decoders.
    """
    x = w.numpy().astype(np.float64)
    thresh = 10 ** (thresh_db / 20)
    amp = np.abs(x)
    over = amp > thresh
    y = x.copy()
    y[over] = np.sign(x[over]) * (thresh + (amp[over] - thresh) / ratio)
    rms = np.sqrt(np.mean(y ** 2))
    y = y * (10 ** ((target_db - 20 * np.log10(rms + 1e-12)) / 20))
    y = np.tanh(y * 1.3) / np.tanh(1.3)
    peak = np.max(np.abs(y))
    if peak > 0.97:
        y = y * 0.97 / peak
    y = torchaudio.functional.resample(torch.from_numpy(y.astype(np.float32)), sr, PLAYBACK_SR).numpy()
    return y, PLAYBACK_SR


# (name, task, scheme, label-filter, sample_id-hint)
PICKS = [
    ("heart_normal", "heart", "binary", "Normal", None),
    ("heart_abnormal", "heart", "binary", "abnormal", "F_AF_A"),
    ("lung_normal", "lung", "binary", "Normal", "M_N_RUA"),
    ("lung_wheeze", "lung", "6class", "Wheezing", "M_W_LUA"),
]


def _pick(task, scheme, label, hint):
    m = build_task_manifest(DATA, task, scheme, os.path.join(OUT, "manifests"))
    if hint:
        sub = m[m["sample_id"] == hint]
        if not sub.empty:
            return sub.iloc[0]
    f = m["task_label"] == label
    if not f.any():
        f = m["task_label"] != "Normal"
    return m[f].iloc[0]


manifest = {}
for name, task, scheme, label, hint in PICKS:
    row = _pick(task, scheme, label, hint)
    raw, sr = load_wav(row["file_path"])
    raw = peak_normalize(raw)
    filt = preprocess(row["file_path"], cfg)
    for ext, w in (("raw", raw), ("filtered", filt)):
        path = os.path.join(OUT, f"{name}_{ext}.wav")
        w, sr = to_playback(w, cfg.sample_rate)
        sf.write(path, w, sr)
        manifest[name] = {
            "sample_id": row["sample_id"], "label": str(row["task_label"]),
            "task": task, "scheme": scheme, "raw": f"docs/assets/audio/{name}_raw.wav",
            "filtered": f"docs/assets/audio/{name}_filtered.wav",
        }
        print(f"[audio] {path} ({os.path.getsize(path)//1024} KB @ {sr} Hz)")

import json

with open(os.path.join(OUT, "manifest.json"), "w") as f:
    json.dump(manifest, f, indent=2)
print(f"[audio] done -> {OUT}")