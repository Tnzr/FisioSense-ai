#!/usr/bin/env python3
"""Build the CardiaSense Jupyter notebooks (nbformat).

Usage:
  python scripts/build_notebooks.py
"""
from __future__ import annotations

import json
import os

import nbformat as nbf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PREAMBLE = f'''
import os, sys
from pathlib import Path

ROOT = Path("{ROOT}")
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT))

DATA = os.environ.get("CARDIASENSE_DATA_DIR") or \
    "/media/tnzr/AuxVolume/datasets/HLS-CMDS Heart and Lung Sounds Dataset " \\
    "Recorded from a Clinical Manikin using Digital Stethoscope"
'''

MD_HEAD = """## CardiaSense AI — {title}

This notebook covers: **{summary}**.

Run `./setup.sh` first (creates the venv, installs deps, downloads the dataset if needed).
The dataset root is resolved from `CARDIASENSE_DATA_DIR` or `.env`.

> Educational / research prototype — not a medical device.
"""


def notebook(title: str, summary: str, cells: list) -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook()
    nb.metadata["kernelspec"] = {"display_name": "Python 3 (cardiasense)", "language": "python",
                                 "name": "cardiasense"}
    nb.cells = [nbf.v4.new_markdown_cell(MD_HEAD.format(title=title, summary=summary))]
    for cell_type, src in cells:
        if cell_type == "md":
            nb.cells.append(nbf.v4.new_markdown_cell(src))
        else:
            nb.cells.append(nbf.v4.new_code_cell(src))
    return nb


def build_all(out_dir: str) -> list:
    os.makedirs(out_dir, exist_ok=True)
    paths = []

    # ---------------------------------------------------------------- 01
    cells = [
        ("code", PREAMBLE),
        ("code", """
from cardia.data.hls_cmds import build_task_manifest
m = build_task_manifest(DATA, "sound", "binary")
print("sound:", len(m), "files")
print(m["task_label"].value_counts())
for task in ("heart", "lung"):
    mm = build_task_manifest(DATA, task, "binary")
    print(task, len(mm), "samples")
    print(mm["task_label"].value_counts().to_dict())
"""),
        ("md", "### Listen to a few clips (embedded audio)"),
        ("code", """
import IPython.display as d
from cardia.data.transforms import load_wav, peak_normalize

for label in ("heart", "lung", "mixed"):
    row = m[m["task_label"] == label].iloc[0]
    wav, sr = load_wav(row["file_path"])
    display(d.Audio(wav.numpy(), rate=sr))
    print(label, row["sample_id"])
"""),
        ("md", "### Waveform + log-mel of one clip"),
        ("code", """
import matplotlib.pyplot as plt
from cardia.data.transforms import MelSpec, preprocess
from cardia.wandb_utils import viz

row = m[m["task_label"] == "heart"].iloc[0]
raw, sr = load_wav(row["file_path"]); raw = peak_normalize(raw)
filt = preprocess(row["file_path"], TYPE_CHECK := None) if False else None
import torch
from cardia.config import Config
cfg = Config()
filt = preprocess(row["file_path"], cfg)
mel = MelSpec(cfg.sample_rate, cfg.n_mels, cfg.n_fft, cfg.hop_length)
viz.waveform_fig(raw.numpy(), sr, f"raw {row['sample_id']}")
plt.show()
viz.spec_fig(mel(filt).numpy(), f"log-mel {row['sample_id']}")
plt.show()
"""),
        ("md", "### Signal quality indicators (sample)"),
        ("code", """
from cardia.data.stats import sqi_stats
df = sqi_stats(m, n=50)
print(df[["sample_id","duration_s","rms","snr_estimate","clip_ratio"]].describe().T)
"""),
    ]
    paths.append(_write(out_dir, "01_dataset_exploration", notebook("Dataset exploration", "counts, classes, audio playback, spectrograms, signal quality", cells)))

    # ---------------------------------------------------------------- 02
    cells = [
        ("code", PREAMBLE),
        ("md", "### Band-pass processing (heart vs lung bands)"),
        ("code", """
import numpy as np
from cardia.config import Config
from cardia.data.transforms import load_wav, peak_normalize, preprocess

cfg = Config()
row = __import__("cardia.data.hls_cmds", fromlist=["build_task_manifest"]).build_task_manifest(DATA, "lung", "binary").iloc[0]
raw, sr = load_wav(row["file_path"]); raw = peak_normalize(raw)
filt = preprocess(row["file_path"], cfg)   # lung band 60-1500 Hz
from cardia.wandb_utils import viz
viz.overlay_fig(raw.numpy(), filt.numpy(), sr, f"band-pass overlay {row['sample_id']}")
plt = __import__("matplotlib.pyplot", fromlist=["show"]); plt.show()
"""),
        ("md", "### Augmentation (train-only, seeded)"),
        ("code", """
from cardia.data.transforms import Augment, MelSpec
aug = Augment(cfg, cfg.seed); aug.set_epoch(0)
w = aug.waveform(filt); spec = mel_spec = MelSpec(cfg.sample_rate, cfg.n_mels, cfg.n_fft, cfg.hop_length)
viz.aug_fig(mel_spec(filt).numpy(), aug.spec(mel_spec(w)).numpy(), "before / after augmentation")
plt.show()
"""),
        ("md", "### Leakage-safe grouped splits"),
        ("code", """
from cardia.data.splits import make_splits
import pandas as pd
m = __import__("cardia.data.hls_cmds", fromlist=["build_task_manifest"]).build_task_manifest(DATA, "sound", "binary")
splits = make_splits(m, n_folds=5, seed=0)   # asserts train/val/test group disjointness
rows = [{"fold": s.fold, "train": len(s.train), "val": len(s.val), "test": len(s.test)} for s in splits]
print(pd.DataFrame(rows).to_string(index=False))
"""),
    ]
    paths.append(_write(out_dir, "02_preprocessing_splits", notebook("Preprocessing & leakage-safe splits", "DSP, augmentation, grouped cross-validation splits", cells)))

    # ---------------------------------------------------------------- 03
    cells = [
        ("code", PREAMBLE),
        ("md", "### Classical benchmark (fast smoke: heart, 5 folds)"),
        ("code", """
from cardia.config import Config
from cardia.train import classical_train
import wandb

cfg = Config(task="heart", stage=1, out_dir=ROOT / "ml" / "runs")
m = __import__("cardia.data.hls_cmds", fromlist=["build_task_manifest"]).build_task_manifest(DATA, "heart", "binary")
splits = __import__("cardia.data.splits", fromlist=["make_splits"]).make_splits(m, n_folds=5, seed=0)
run = wandb.init(mode="disabled")
metrics = classical_train.run_classical(cfg, m, splits, ["normal","abnormal"], run, "nb-smoke")
run.finish()
import pandas as pd
per = metrics.get("_per_classifier", [])
print(pd.DataFrame(per)[["classifier","balanced_accuracy_mean","macro_f1_mean"]].to_string(index=False))
"""),
        ("md", "### Deep tier (smoke mode) via the CLI"),
        ("code", """
import subprocess
rc = subprocess.run([sys.executable, "-m", "cardia.cli", "--task", "heart", "--stage", "2",
                     "--model", "resnet18", "--fold", "0", "--smoke", "--out-dir", "/tmp/cardiasense_nb_runs"],
                    cwd=str(ROOT / "ml"))
print("exit", rc.returncode)
"""),
        ("md", "### Full campaign + benchmark tables"),
        ("code", """
import json
p = ROOT / "ml" / "runs" / "benchmark.json"
if p.exists():
    bench = json.loads(p.read_text())["benchmark"]
    print(pd.DataFrame(bench).to_string(index=False))
else:
    print("No benchmark.json yet — run:  cd ml && SMOKE=1 ./scripts/run_sequential.sh")
"""),
    ]
    paths.append(_write(out_dir, "03_benchmark_training", notebook("Benchmark & training", "classical baseline, deep smoke training, campaign tables", cells)))

    # ---------------------------------------------------------------- 04
    cells = [
        ("code", PREAMBLE),
        ("md", "### Audio-token / CLS embeddings from the encoder"),
        ("code", """
from cardia import features  # noqa
from cardia.features import embeddings as emb
MC = "/media/tnzr/AuxVolume/cardiasense-runs/mc"
try:
    data = emb.corpus_embeddings(DATA, MC)
    M = emb.class_mean_matrix(data)
    print("corpus", data["rows"]["sample_id"][:3], "...", len(data["rows"]["sample_id"]), "clips,", "classes", len(M))
    import matplotlib.pyplot as plt
    from cardia.config import HEART_TYPES
    fig, ax = plt.subplots(figsize=(8,7))
    ax.imshow(M, cmap="magma", vmin=0, vmax=1); ax.set_xticks(range(len(HEART_TYPES))); ax.set_yticks(range(len(HEART_TYPES)))
    ax.set_xticklabels([c[:10] for c in HEART_TYPES], rotation=45, ha="right")
    ax.set_yticklabels([c[:10] for c in HEART_TYPES])
    ax.set_title("Class-mean embedding cosine similarity"); plt.show()
except FileNotFoundError as e:
    print("checkpoints not available:", e)
"""),
        ("md", "### Generate one app-style report in-notebook"),
        ("code", """
import sys
sys.path.insert(0, str(ROOT / "webapp"))
from webapp.app import inference, report
reg = inference.get_registry()     # warm-loads the head ensembles
opts = report.ReportOptions(heads=["source","heart_types"], figures="all", temporal=True,
                            temporal_mode="multiscale", explanation="standard")
span = __import__("soundfile", fromlist=["read"]).read if False else None
import soundfile as sf, torch
path = __import__("webapp.app.game", fromlist=["resolve_audio_path"]).resolve_audio_path("M0001", "sound", "binary")
wav, sr = sf.read(path, dtype="float32", always_2d=True)
rep = report.analyze_waveform(torch.from_numpy(wav[:,0]).squeeze(), int(sr), "M0001.wav", opts)
print("verdict:", rep["verdict"])
for k in ("timeline_source", "probs_heart_types"):
    print(k, "present:", k in rep["figures"])
"""),
        ("md", "### Embedded audio + screenshots in the README"),
        ("code", """
print("Audio assets:  docs/assets/audio/*.wav   (played inline in the GitHub README)")
print("Screenshots:   docs/walkthrough/*.png    (instructional walkthrough)")
"""),
    ]
    paths.append(_write(out_dir, "04_report_embeddings_webapp", notebook("Report, embeddings & web app", "encoder embeddings, app report, README audio/screenshots", cells)))

    # ---------------------------------------------------------------- 05
    cells = [
        ("code", PREAMBLE),
        ("md", "### Personalized AI narrative (LLM, with offline fallback)"),
        ("code", """
from webapp.app import llm as llm_mod
findings = [
    {"key":"heart_binary","label":"Heart screening","kind":"binary","pred":"abnormal","confidence":0.82,
     "classes":["normal","abnormal"],"probs":[0.18,0.82]},
    {"key":"lung_types","label":"Lung typing","kind":"multiclass","pred":"Wheezing","confidence":0.71,
     "classes":["Normal","Wheezing","Fine Crackles","Coarse Crackles","Rhonchi","Pleural Rub"]},
]
out = llm_mod.generate_narrative(findings, patient_context="58y, asthma, mild palpitations")
import json
print("provider:", out["provider"], "| model:", out["model"], "| personalized:", out["personalized"])
print(out["summary"])
for area, recs in out["recommendations"].items():
    print(f"  {area}: {recs}")
"""),
        ("md", "### Follow-up conversation (chat)")
        if False else ("md", "### Optional: live LLM via an OpenAI-compatible endpoint"),
        ("code", """
if os.environ.get("CARDIASENSE_LLM_API_KEY"):
    narr = llm_mod.generate_narrative(findings, "asthma", [{"role":"user","content":"should I worry about the wheeze?"}])
    print("provider:", narr["provider"], narr.get("summary", "")[:200])
else:
    print("No CARDIASENSE_LLM_API_KEY — using the offline synthesizer (already shown above).")
"""),
    ]
    paths.append(_write(out_dir, "05_llm_integration", notebook("LLM integration", "personalized narrative, recommendations, optional live LLM", cells)))

    return paths


def _write(out_dir: str, name: str, nb: nbf.NotebookNode) -> str:
    path = os.path.join(out_dir, f"{name}.ipynb")
    with open(path, "w") as f:
        json.dump(nb, f, indent=1)
    return path


if __name__ == "__main__":
    import sys

    out = os.path.join(ROOT, "notebooks")
    for p in build_all(out):
        print("wrote", p)
    print("notebooks ->", out)