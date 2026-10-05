#!/usr/bin/env python3
"""Generate README/report figure assets into docs/assets/report/.

Produces the synchronized inference-timeline figures (input spectrogram +
stacked-area head probabilities + confidence line) and multi-scale figures for
representative dataset clips, and copies the benchmark report figures if the
report has been generated.
"""
from __future__ import annotations

import glob
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "webapp"))

import torch  # noqa: E402
import soundfile as sf  # noqa: E402

from webapp.app import game, inference  # noqa: E402
from cardia.wandb_utils import viz  # noqa: E402

OUT = os.path.join(ROOT, "docs", "assets", "report")
os.makedirs(OUT, exist_ok=True)
reg = inference.get_registry()


def _load(sample_id, task, scheme):
    path = game.resolve_audio_path(sample_id, task, scheme)
    if not path:
        return None
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    return torch.from_numpy(data[:, 0]).squeeze(), int(sr)


def make_timeline(head_key, sample_id, task, scheme, name, window_s=3.0, hop_s=0.5):
    head = reg.get(head_key)
    if head is None or not head.ready:
        print(f"skip {head_key}: not loaded")
        return
    got = _load(sample_id, task, scheme)
    if got is None:
        print(f"skip {head_key}: sample {sample_id} not found")
        return
    wav, sr = got
    ser = head.predict_series(wav, sr, window_s, hop_s)
    spec = head.mel(head.preprocess(wav, sr)).numpy()
    duration = wav.shape[0] / sr
    fig = viz.inference_timeline_fig(
        spec, duration, ser["times"], ser["probs"], head.head.classes,
        f"{head.head.label} — sample {sample_id} (window {window_s}s, hop {hop_s}s)")
    fig.savefig(os.path.join(OUT, name), dpi=130, bbox_inches="tight")
    print(f"wrote {name}")


def make_multiscale(head_key, sample_id, task, scheme, name):
    head = reg.get(head_key)
    got = _load(sample_id, task, scheme)
    if head is None or got is None:
        print(f"skip multiscale {head_key}")
        return
    wav, sr = got
    ms = head.predict_multiscale(wav, sr, scales=(1.0, 3.0, 15.0))
    spec = head.mel(head.preprocess(wav, sr)).numpy()
    duration = wav.shape[0] / sr
    fig = viz.multiscale_fig(
        spec, duration, ms["scales"], ms["macro"]["probs"], head.head.classes,
        f"{head.head.label} — multi-scale (1/3/15 s) · sample {sample_id}")
    fig.savefig(os.path.join(OUT, name), dpi=130, bbox_inches="tight")
    print(f"wrote {name}")


def copy_report_figures():
    src = os.path.join(ROOT, "ml", "report", "figures")
    keep = [
        "benchmark.png", "dataset.png",
        "cm_heart_binary.png", "cm_lung_binary.png", "cm_sound_binary.png",
        "cm_heart_10class.png", "cm_lung_6class.png", "cm_combined.png",
        "meanprob_sound.png", "meanprob_heart.png", "meanprob_lung.png",
        "evolution_heart_10class.png", "evolution_lung_6class.png", "evolution_sound_binary.png",
        "curves_stage2-sound-resnet18-allfolds-s0.png",
        "curves_stage4-heart-transformer-10class-allfolds-s0.png",
        "curves_stage2-lung-resnet18-6class-allfolds-s0.png",
        "proc_heart.png", "proc_lung.png", "proc_mixed.png",
    ]
    copied = 0
    for name in keep:
        p = os.path.join(src, name)
        if os.path.isfile(p):
            shutil.copy(p, os.path.join(OUT, name))
            copied += 1
    print(f"copied {copied} report figures")


if __name__ == "__main__":
    make_timeline("source", "M0001", "sound", "binary", "timeline_source.png")
    make_timeline("heart_types", "H0007", "heart", "10class", "timeline_heart_types.png")
    make_timeline("lung_types", "L0054", "lung", "6class", "timeline_lung_types.png")
    make_multiscale("source", "M0001", "sound", "binary", "multiscale_source.png")
    copy_report_figures()
    print("assets ->", OUT)
