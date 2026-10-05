"""Combined multiclass confusion matrices for heart and lung detections.

Reads the heart-10class and lung-6class test predictions (written by the
training stages) and produces three WandB artifacts:
  * heart-type confusion matrix (10 x 10)
  * lung-type confusion matrix (6 x 6)
  * combined 16 x 16 block-diagonal matrix (heart block + lung block)

Usage:
  python -m cardia.report.combined --out-dir runs_mc \
      --heart-stage 2 --heart-model resnet18 \
      --lung-stage 2 --lung-model resnet18 --seed 0
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd

ML = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ML not in sys.path:
    sys.path.insert(0, ML)

from cardia.config import HEART_TYPES, LUNG_TYPES
from cardia.wandb_utils import log as wlog
from cardia.wandb_utils import viz

COMBINED_NAMES = HEART_TYPES + LUNG_TYPES


def _glob_predictions(out_dir: str, task: str, scheme: str, stage: Optional[int], model: Optional[str], seed: int) -> Optional[pd.DataFrame]:
    patterns = []
    if stage is not None and model is not None:
        patterns = [
            os.path.join(out_dir, "checkpoints", f"stage{stage}-{task}-{model}-{scheme}-allfolds-s{seed}-fold*_predictions.csv"),
            os.path.join(out_dir, "checkpoints", f"stage{stage}-{task}-{model}-{scheme}-fold*-s{seed}_predictions.csv"),
            os.path.join(out_dir, "checkpoints", f"stage{stage}-{task}-{model}-{scheme}-allfolds-s{seed}_predictions.csv"),
            os.path.join(out_dir, "checkpoints", f"stage{stage}-{task}-classical-{model}-{scheme}-s{seed}_predictions.csv"),
        ]
    else:
        patterns = [
            os.path.join(out_dir, "checkpoints", f"stage*-{task}-*-{scheme}-allfolds-s{seed}-fold*_predictions.csv"),
            os.path.join(out_dir, "checkpoints", f"stage*-{task}-*-{scheme}-fold*-s{seed}_predictions.csv"),
            os.path.join(out_dir, "checkpoints", f"stage*-{task}-*-{scheme}-allfolds-s{seed}_predictions.csv"),
        ]
    files = sorted({f for p in patterns for f in glob.glob(p)})
    if not files:
        return None
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


def _label_columns(df: pd.DataFrame) -> bool:
    return "true" in df.columns and "pred" in df.columns


def run_report(out_dir: str, heart_spec, lung_spec, seed: int, wandb_mode: str = "auto") -> dict:
    heart_df = _glob_predictions(out_dir, "heart", "10class", heart_spec.get("stage"), heart_spec.get("model"), seed)
    lung_df = _glob_predictions(out_dir, "lung", "6class", lung_spec.get("stage"), lung_spec.get("model"), seed)
    if heart_df is None or not _label_columns(heart_df):
        raise FileNotFoundError(f"no heart 10class predictions under {out_dir}/checkpoints (run the heart 10class campaign first)")
    if lung_df is None or not _label_columns(lung_df):
        raise FileNotFoundError(f"no lung 6class predictions under {out_dir}/checkpoints (run the lung 6class campaign first)")

    from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix

    heart_cm = confusion_matrix(heart_df["true"], heart_df["pred"], labels=HEART_TYPES)
    lung_cm = confusion_matrix(lung_df["true"], lung_df["pred"], labels=LUNG_TYPES)

    combined = np.zeros((len(COMBINED_NAMES), len(COMBINED_NAMES)), dtype=int)
    combined[: len(HEART_TYPES), : len(HEART_TYPES)] = heart_cm
    combined[len(HEART_TYPES):, len(HEART_TYPES):] = lung_cm

    result = {
        "heart_cm": heart_cm, "lung_cm": lung_cm, "combined_cm": combined,
        "n_heart": int(len(heart_df)), "n_lung": int(len(lung_df)),
        "heart_accuracy": float(accuracy_score(heart_df["true"], heart_df["pred"])),
        "heart_balanced_accuracy": float(balanced_accuracy_score(heart_df["true"], heart_df["pred"])),
        "lung_accuracy": float(accuracy_score(lung_df["true"], lung_df["pred"])),
        "lung_balanced_accuracy": float(balanced_accuracy_score(lung_df["true"], lung_df["pred"])),
    }

    run = wlog.init_run(
        _ReportConfig(out_dir=out_dir, wandb_mode=wandb_mode),
        f"report-combined-confusion-heart{heart_spec.get('stage')}{heart_spec.get('model')}-lung{lung_spec.get('stage')}{lung_spec.get('model')}-s{seed}",
    )
    try:
        wlog.log_fig(run, "heart/confusion_matrix_fig",
                     viz.confusion_matrix_fig(heart_cm, HEART_TYPES, "heart sound type confusion (10-class)"))
        wlog.log_fig(run, "lung/confusion_matrix_fig",
                     viz.confusion_matrix_fig(lung_cm, LUNG_TYPES, "lung sound type confusion (6-class)"))
        wlog.log_fig(run, "combined/confusion_matrix_fig",
                     viz.confusion_matrix_fig(combined, COMBINED_NAMES,
                                              "combined heart + lung confusion (block-diagonal 16x16)", normalize=False))
        wlog.log_table(run, "heart/confusion_matrix", pd.DataFrame(heart_cm, index=HEART_TYPES, columns=HEART_TYPES))
        wlog.log_table(run, "lung/confusion_matrix", pd.DataFrame(lung_cm, index=LUNG_TYPES, columns=LUNG_TYPES))
        wlog.log_table(run, "combined/confusion_matrix", pd.DataFrame(combined, index=COMBINED_NAMES, columns=COMBINED_NAMES))
        wlog.log_table(run, "summary", pd.DataFrame(
            [{"block": "heart", "classes": 10, "n": result["n_heart"],
              "accuracy": result["heart_accuracy"], "balanced_accuracy": result["heart_balanced_accuracy"]},
             {"block": "lung", "classes": 6, "n": result["n_lung"],
              "accuracy": result["lung_accuracy"], "balanced_accuracy": result["lung_balanced_accuracy"]},
             {"block": "combined", "classes": 16, "n": result["n_heart"] + result["n_lung"],
              "accuracy": (result["heart_accuracy"] * result["n_heart"] + result["lung_accuracy"] * result["n_lung"]) / (result["n_heart"] + result["n_lung"]),
              "balanced_accuracy": (result["heart_balanced_accuracy"] + result["lung_balanced_accuracy"]) / 2.0}]
        ))
        run.summary.update({k: v for k, v in result.items() if not isinstance(v, np.ndarray)})
    finally:
        wlog.finish_run(run)
    return result


class _ReportConfig:
    def __init__(self, out_dir: str, wandb_mode: str = "auto") -> None:
        self.out_dir = out_dir
        self.wandb_mode = wandb_mode

    def to_dict(self) -> dict:
        return {"report": "combined_confusion", "out_dir": self.out_dir}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Combined heart + lung multiclass confusion matrices")
    p.add_argument("--out-dir", default="runs", help="campaign output dir containing checkpoints/")
    p.add_argument("--heart-stage", type=int, default=2, help="stage whose heart-10class predictions to use")
    p.add_argument("--heart-model", default="resnet18", help="heart model whose predictions to use")
    p.add_argument("--lung-stage", type=int, default=2, help="stage whose lung-6class predictions to use")
    p.add_argument("--lung-model", default="resnet18", help="lung model whose predictions to use")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--wandb-mode", choices=("auto", "online", "offline", "disabled"), default="auto")
    args = p.parse_args(argv)

    result = run_report(
        args.out_dir,
        {"stage": args.heart_stage, "model": args.heart_model},
        {"stage": args.lung_stage, "model": args.lung_model},
        args.seed, args.wandb_mode,
    )
    print("heart cm (10x10):")
    print(result["heart_cm"])
    print("lung cm (6x6):")
    print(result["lung_cm"])
    print("combined cm (16x16):")
    print(result["combined_cm"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
