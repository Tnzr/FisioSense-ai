#!/usr/bin/env python3
"""Export a compact set of demo clips (raw + band-passed) for the README's
embedded-audio section into docs/assets/audio/.

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

from cardia.config import Config
from cardia.data.hls_cmds import build_task_manifest
from cardia.data.transforms import load_wav, peak_normalize, preprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "assets", "audio")
os.makedirs(OUT, exist_ok=True)
cfg = Config()

DATA = os.environ.get("CARDIASENSE_DATA_DIR", cfg.data_dir)

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
        sf.write(path, w.numpy(), cfg.sample_rate)
        manifest[name] = {
            "sample_id": row["sample_id"], "label": str(row["task_label"]),
            "task": task, "scheme": scheme, "raw": f"docs/assets/audio/{name}_raw.wav",
            "filtered": f"docs/assets/audio/{name}_filtered.wav",
        }
        print(f"[audio] {path} ({os.path.getsize(path)//1024} KB)")

import json

with open(os.path.join(OUT, "manifest.json"), "w") as f:
    json.dump(manifest, f, indent=2)
print(f"[audio] done -> {OUT}")