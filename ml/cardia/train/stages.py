"""Stage registry + sequential gate logic (adopt stage N only if it improves
balanced-accuracy OR macro-F1 by >= 1 point over the best prior stage)."""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from cardia.config import Config
from cardia.data.splits import FoldSplit
from cardia.models.cnn import build_cnn
from cardia.models.temporal import build_temporal
from cardia.models.transformer import build_transformer
from cardia.train import classical_train
from cardia.train import train as deep_train
from cardia.wandb_utils import log as wlog

MIN_IMPROVEMENT = 0.01  # 1 balanced-accuracy / macro-F1 point

STAGE_2_MODELS = ["mobilenetv3", "resnet18"]
STAGE_3_MODELS = ["gru", "lstm"]
STAGE_4_MODELS = ["transformer"]


def run_deep_stage(
    cfg: Config,
    manifest,
    splits: List[FoldSplit],
    class_names: List[str],
    run,
    run_name: str,
    all_folds: bool,
) -> dict:
    builder = _model_builder(cfg)
    if all_folds:
        per_fold = []
        for sp in splits:
            sub_run_name = f"{run_name}-fold{sp.fold}"
            m = deep_train.run_deep_training(
                cfg, manifest, sp, len(class_names), class_names, builder, run, sub_run_name
            )
            per_fold.append(m)
        return _aggregate_deep(per_fold, cfg, run, run_name)
    sp = splits[cfg.fold]
    m = deep_train.run_deep_training(
        cfg, manifest, sp, len(class_names), class_names, builder, run, run_name
    )
    return m


def _model_builder(cfg: Config):
    if cfg.stage == 2:
        return build_cnn
    if cfg.stage == 3:
        return build_temporal
    if cfg.stage == 4:
        return build_transformer
    raise ValueError(f"stage {cfg.stage} has no deep model builder")


def _aggregate_deep(per_fold: List[dict], cfg: Config, run, run_name: str) -> dict:
    cols = [
        "test_accuracy", "test_balanced_accuracy", "test_macro_f1",
        "test_macro_precision", "test_macro_recall", "test_auroc", "test_ece",
        "val_balanced_accuracy", "latency_ms_per_sample", "best_epoch",
    ]
    rows = []
    cms = []
    for m in per_fold:
        rows.append({c: m.get(c) for c in cols})
        if "confusion_matrix" in m:
            cms.append(np.asarray(m["confusion_matrix"]))
    df = pd.DataFrame(rows)
    wlog.log_table(run, "fold_results", df)
    if cms:
        from cardia.wandb_utils import viz
        from cardia.data.hls_cmds import class_names

        total_cm = sum(cms)
        total_cm = total_cm.astype(int)
        names = class_names(cfg.task, cfg.class_scheme)
        wlog.log_fig(run, "cv/confusion_matrix_fig", viz.confusion_matrix_fig(total_cm, names, f"{run_name} aggregated confusion"))
        wlog.log_table(run, "cv/confusion_matrix", pd.DataFrame(total_cm, index=names, columns=names))
    agg = {
        "task": cfg.task, "stage": cfg.stage, "model": cfg.model, "fold": None, "seed": cfg.seed,
    }
    for c in cols:
        if c in ("test_auroc", "latency_ms_per_sample"):
            agg[c] = float(df[c].dropna().mean())
        elif c == "best_epoch":
            agg[c] = int(df[c].mean())
        else:
            agg[f"{c}_mean"] = float(df[c].mean())
            agg[f"{c}_std"] = float(df[c].std())
    run.summary.update({f"cv/{c}": agg.get(f"{c}_mean", agg.get(c)) for c in cols})
    agg["fold_results"] = df.to_dict(orient="records")
    return agg


def _load_metrics(out_dir: str) -> dict:
    path = os.path.join(out_dir, "metrics.json")
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _save_metrics(out_dir: str, metrics: dict) -> None:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "metrics.json")
    existing = _load_metrics(out_dir)
    key = f"{metrics.get('task')}|stage{metrics.get('stage')}|{metrics.get('model')}|fold{metrics.get('fold')}"
    existing[key] = metrics
    with open(path, "w") as f:
        json.dump(existing, f, indent=2, sort_keys=True, default=str)


def gate_decision(new_metrics: dict, best_prior_bal: Optional[float], best_prior_f1: Optional[float]) -> dict:
    """Adopt stage N if balanced-accuracy OR macro-F1 improves by >= 1 point
    over the best prior stage on the same task (plan gate rule)."""
    new_bal = _metric_or_mean(new_metrics, "test_balanced_accuracy")
    new_f1 = _metric_or_mean(new_metrics, "test_macro_f1")
    improved_bal = best_prior_bal is None or (new_bal is not None and new_bal >= best_prior_bal + MIN_IMPROVEMENT)
    improved_f1 = best_prior_f1 is not None and new_f1 is not None and new_f1 >= best_prior_f1 + MIN_IMPROVEMENT
    improved = bool(improved_bal or improved_f1)
    return {
        "improved": improved,
        "new_balanced_accuracy": new_bal,
        "new_macro_f1": new_f1,
        "best_prior_balanced_accuracy": float(best_prior_bal) if best_prior_bal is not None else None,
        "best_prior_macro_f1": float(best_prior_f1) if best_prior_f1 is not None else None,
        "min_improvement": MIN_IMPROVEMENT,
        "decision": "adopt" if improved else "skip",
    }


def _metric_or_mean(metrics: dict, key: str) -> Optional[float]:
    val = metrics.get(f"{key}_mean")
    if val is None:
        val = metrics.get(key)
    return float(val) if isinstance(val, (int, float)) else None


def record_gate(out_dir: str, task: str, stage: int, model: str, decision: dict) -> None:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "metrics.json")
    data = _load_metrics(out_dir)
    key = f"gates|{task}|stage{stage}|{model}"
    data[key] = {"task": task, "stage": stage, "model": model, **decision}
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True, default=str)
