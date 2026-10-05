"""Recompute post-softmax inference distributions from saved checkpoints.

Enables the demo to show the model heads' probability output for any trained
champion model, even when stored predictions lack the full probability vector.
"""
from __future__ import annotations

import glob
import os
import re
import sys
from typing import List, Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

ML = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ML not in sys.path:
    sys.path.insert(0, ML)

from cardia.config import Config
from cardia.data.dataset import HLSDataset
from cardia.data.hls_cmds import build_task_manifest, class_names
from cardia.data.splits import load_splits
from cardia.models.cnn import build_cnn
from cardia.models.temporal import build_temporal
from cardia.models.transformer import build_transformer


def _collate(batch):
    return {
        "x": torch.stack([b["x"] for b in batch]),
        "y": torch.stack([b["y"] for b in batch]),
        "sample_id": [b["sample_id"] for b in batch],
        "group": [b["group"] for b in batch],
    }


def _builder(cfg: Config):
    return {2: build_cnn, 3: build_temporal, 4: build_transformer}[cfg.stage]


def _checkpoint_files(out_dir: str, cfg: Config) -> List[str]:
    suf = f"-{cfg.class_scheme}" if cfg.class_scheme != "binary" else ""
    pats = [
        os.path.join(out_dir, "checkpoints", f"stage{cfg.stage}-{cfg.task}-{cfg.model}{suf}-allfolds-s{cfg.seed}-fold*_best.pt"),
        os.path.join(out_dir, "checkpoints", f"stage{cfg.stage}-{cfg.task}-{cfg.model}{suf}-fold*-s{cfg.seed}_best.pt"),
    ]
    return sorted({p for pat in pats for p in glob.glob(pat)})


def infer_test_probs(
    data_dir: str,
    out_dir: str,
    task: str,
    scheme: str,
    stage: int,
    model: str,
    seed: int = 0,
    n_folds: int = 5,
    device: str = "auto",
) -> pd.DataFrame:
    cfg = Config(task=task, stage=stage, model=model, class_scheme=scheme, seed=seed,
                 n_folds=n_folds, data_dir=data_dir, out_dir=out_dir, device=device)
    manifest = build_task_manifest(data_dir, task, scheme, os.path.join(out_dir, "manifests"))
    split_dir = os.path.join(out_dir, "splits", f"{task}_{scheme}_s{seed}")
    splits = load_splits(split_dir, n_folds=n_folds)
    names = class_names(task, scheme)
    dev = torch.device(cfg.resolve_device())
    ckpts = _checkpoint_files(out_dir, cfg)
    if not ckpts:
        raise FileNotFoundError(f"no checkpoints for {task}/{scheme}/{stage}/{model} under {out_dir}/checkpoints")

    rows = []
    for ckpt in ckpts:
        m_fold = re.search(r"-fold(\d+)_best\.pt$", os.path.basename(ckpt))
        if not m_fold:
            raise FileNotFoundError(f"cannot parse fold from checkpoint name: {ckpt}")
        fold = int(m_fold.group(1))
        sp = next(s for s in splits if s.fold == fold)
        test_ids = sp.test
        m = manifest.set_index("sample_id").loc[test_ids].reset_index()
        ds = HLSDataset(m, cfg, augment=False)
        loader = torch.utils.data.DataLoader(ds, batch_size=cfg.batch_size, shuffle=False, collate_fn=_collate)
        net = _builder(cfg)(cfg, len(names)).to(dev)
        state = torch.load(ckpt, map_location=dev)
        sd = state["model_state"]
        if "_pos" in sd:  # ASTSmall learned positional embedding
            net._pos = torch.nn.Parameter(sd["_pos"].to(dev))
        net.load_state_dict(sd)
        net.eval()
        with torch.no_grad():
            for batch in loader:
                logits = net(batch["x"].to(dev))
                prob = torch.softmax(logits, dim=1).cpu().numpy()
                for sid, g, y, p in zip(batch["sample_id"], batch["group"],
                                        batch["y"].numpy(), prob):
                    rows.append(
                        {
                            "sample_id": sid, "group": g,
                            "true": names[int(y)], "pred": names[int(p.argmax())],
                            "conf": float(p.max()),
                            "probs": " ".join(f"{v:.4f}" for v in p),
                        }
                    )
    return pd.DataFrame(rows)


def prob_matrix(df: pd.DataFrame, names: List[str]) -> np.ndarray:
    """Mean post-softmax distribution per actual class: (C, C)."""
    mat = np.zeros((len(names), len(names)))
    for _, r in df.iterrows():
        i = names.index(r["true"])
        p = np.asarray([float(v) for v in r["probs"].split()], dtype=float)
        mat[i] += p
    counts = df["true"].map(names.index).value_counts().sort_index().reindex(range(len(names)), fill_value=0)
    denom = np.asarray(counts, dtype=float).clip(min=1)
    return mat / denom[:, None]
