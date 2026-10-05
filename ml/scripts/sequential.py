#!/usr/bin/env python3
"""Sequential campaign orchestrator with stage gates.

Runs every stage for every task (sequential training), then applies the gate:
a stage is ADOPTED only if its best test balanced-accuracy (or macro-F1)
improves by >= 1 point over the best prior stage on the same task; otherwise
the decision is recorded as SKIP. Final champion = best adopted stage.

All decisions land in runs/metrics.json and a WandB benchmark-summary run.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Optional

ML = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ML not in sys.path:
    sys.path.insert(0, ML)

from cardia.train import stages
from cardia.wandb_utils import log as wlog

ROOT = os.path.dirname(ML)
PY = os.path.join(ROOT, ".venv", "bin", "python")

TASKS = ("sound", "heart", "lung")
STAGE_MODELS = {
    1: ["classical"],
    2: stages.STAGE_2_MODELS,
    3: stages.STAGE_3_MODELS,
    4: stages.STAGE_4_MODELS,
}
BAL_ACC = "test_balanced_accuracy"
MACRO_F1 = "test_macro_f1"
OUT = "runs"


def cli_args(extra: list, smoke: bool, class_scheme: str = "binary", epochs: Optional[int] = None, patience: Optional[int] = None) -> list:
    cmd = [PY, "-m", "cardia.cli"] + extra
    cmd += ["--class-scheme", class_scheme]
    if epochs is not None:
        cmd += ["--epochs", str(epochs)]
    if patience is not None:
        cmd += ["--patience", str(patience)]
    if smoke:
        cmd.append("--smoke")
    return cmd


def stage_best_metric(data: dict, task: str, stage: int, metric: str = BAL_ACC) -> Optional[float]:
    vals = []
    for k, v in data.items():
        if not k.startswith(f"{task}|stage{stage}"):
            continue
        if v.get("fold") is not None:
            continue
        val = v.get(f"{metric}_mean")
        if val is None:
            val = v.get(metric)
        if val is None and stage == 1 and metric == BAL_ACC:
            val = max(
                (v.get(f"{c}_balanced_accuracy") for c in ("logistic", "random_forest", "svm")),
                default=None,
            )
        if val is None and stage == 1 and metric == MACRO_F1:
            val = max(
                (v.get(f"{c}_macro_f1") for c in ("logistic", "random_forest", "svm")),
                default=None,
            )
        if isinstance(val, (int, float)):
            vals.append(val)
    return max(vals) if vals else None


def run_task(task: str, smoke: bool, out_dir: str, class_scheme: str = "binary",
             epochs: Optional[int] = None, patience: Optional[int] = None) -> None:
    print(f"\n===== TASK {task} ({class_scheme}) =====", flush=True)
    best_prior_bal: Optional[float] = None
    best_prior_f1: Optional[float] = None
    for stage in (1, 2, 3, 4):
        models = STAGE_MODELS[stage]
        for model in models:
            extra = ["--task", task, "--stage", str(stage), "--model", model, "--out-dir", out_dir]
            if stage != 1:
                extra.append("--all-folds")
            print(f"[orchestrator] stage {stage} model {model}", flush=True)
            subprocess.check_call(cli_args(extra, smoke, class_scheme, epochs, patience), cwd=ML)
        best_bal = stage_best_metric(stages._load_metrics(out_dir), task, stage, BAL_ACC)
        best_f1 = stage_best_metric(stages._load_metrics(out_dir), task, stage, MACRO_F1)
        decision = stages.gate_decision(
            {"test_balanced_accuracy": best_bal, "test_macro_f1": best_f1},
            best_prior_bal, best_prior_f1,
        )
        stages.record_gate(out_dir, task, stage, "best", decision)
        print(f"[orchestrator] task={task} stage={stage} best_bal_acc={best_bal} "
              f"best_f1={best_f1} best_prior_bal={best_prior_bal} "
              f"best_prior_f1={best_prior_f1} -> {decision['decision']}", flush=True)
        if decision["improved"]:
            best_prior_bal = best_bal if best_bal is not None else best_prior_bal
            best_prior_f1 = best_f1 if best_f1 is not None else best_prior_f1
        # gate rule: if a stage did not improve, later stages still run (compute
        # budget allows) but are compared against the best prior adopted stage.


def benchmark_summary(out_dir: str) -> dict:
    data = stages._load_metrics(out_dir)
    rows = []
    for task in TASKS:
        for stage in (1, 2, 3, 4):
            best_bal = stage_best_metric(data, task, stage, BAL_ACC)
            best_f1 = stage_best_metric(data, task, stage, MACRO_F1)
            gate = data.get(f"gates|{task}|stage{stage}|best", {})
            rows.append(
                {
                    "task": task, "stage": stage,
                    "best_test_balanced_accuracy": best_bal,
                    "best_test_macro_f1": best_f1,
                    "gate_decision": gate.get("decision", ""),
                    "best_prior_balanced_accuracy": gate.get("best_prior_balanced_accuracy"),
                    "best_prior_macro_f1": gate.get("best_prior_macro_f1"),
                }
            )
    return {"benchmark": rows}


def main(argv=None) -> int:
    from cardia.config import CLASS_SCHEMES

    p = argparse.ArgumentParser(description="Sequential HLS-CMDS benchmark campaign")
    p.add_argument("--tasks", nargs="+", choices=TASKS, default=list(TASKS))
    p.add_argument("--class-scheme", choices=list(CLASS_SCHEMES), default="binary",
                   help="binary (normal/abnormal), 6class (lung types), 10class (heart types); sound is always binary")
    p.add_argument("--epochs", type=int, default=None, help="override max training epochs")
    p.add_argument("--patience", type=int, default=None, help="override early-stop patience")
    p.add_argument("--smoke", action="store_true", help="2 folds / 2 epochs smoke run")
    p.add_argument("--out-dir", default=OUT)
    p.add_argument("--no-wandb-summary", action="store_true")
    args = p.parse_args(argv)

    if args.class_scheme != "binary" and "sound" in args.tasks:
        sys.exit("sound task is always 3-class (binary scheme); run --tasks heart and --tasks lung separately for multiclass schemes")

    for task in args.tasks:
        run_task(task, args.smoke, args.out_dir, args.class_scheme, args.epochs, args.patience)

    summary = benchmark_summary(args.out_dir)
    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "benchmark.json"), "w") as f:
        json.dump(summary, f, indent=2)

    if not args.no_wandb_summary:
        from cardia.config import Config

        run = wlog.init_run(Config(out_dir=args.out_dir), "benchmark-summary")
        wlog.log_table(run, "benchmark", _summary_df(summary))
        run.summary.update({"tasks": args.tasks, "smoke": args.smoke})
        wlog.finish_run(run)
    print(json.dumps(summary, indent=2))
    return 0


def _summary_df(summary: dict):
    import pandas as pd

    return pd.DataFrame(summary["benchmark"])


if __name__ == "__main__":
    sys.exit(main())
