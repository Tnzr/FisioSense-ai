"""Stage 1 classical ML: Logistic Regression, Random Forest, SVM with 5-fold CV.

Models are fit on the training split only (mirroring the deep-stage protocol,
where val is used for checkpoint selection, not training) and evaluated on the
held-out test fold per split; fold mean±std and a feature summary are logged.
"""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

from cardia.config import Config
from cardia.data.splits import FoldSplit
from cardia.features.classical import extract_manifest_features
from cardia.wandb_utils import log as wlog

CLASSIFIERS = {
    "logistic": ("LogisticRegression", {}),
    "random_forest": ("RandomForestClassifier", {"n_estimators": 300, "random_state": 0}),
    "svm": ("SVC", {"random_state": 0}),
}


def run_classical(cfg: Config, manifest, splits: List[FoldSplit], class_names: List[str], run, run_name: str) -> dict:
    feats = extract_manifest_features(manifest, cfg)
    feat_cols = [c for c in feats.columns if c not in ("sample_id", "target")]
    from sklearn.preprocessing import StandardScaler

    results = {name: [] for name in CLASSIFIERS}
    cms = {name: [] for name in CLASSIFIERS}
    preds = {name: [] for name in CLASSIFIERS}
    feature_summaries = {}

    for clf_name, (clf_cls_name, extra) in CLASSIFIERS.items():
        for sp in splits:
            train_ids = set(sp.train)
            tr = feats[feats["sample_id"].isin(train_ids)]
            te = feats[feats["sample_id"].isin(sp.test)]
            Xtr, ytr = tr[feat_cols].to_numpy(dtype=np.float32), tr["target"].to_numpy()
            Xte, yte = te[feat_cols].to_numpy(dtype=np.float32), te["target"].to_numpy()
            scaler = StandardScaler().fit(Xtr)
            Xtr_s, Xte_s = scaler.transform(Xtr), scaler.transform(Xte)
            from sklearn.linear_model import LogisticRegression
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.svm import SVC
            from sklearn.calibration import CalibratedClassifierCV

            clf_map = {
                "LogisticRegression": lambda: LogisticRegression(max_iter=2000, class_weight="balanced"),
                "RandomForestClassifier": lambda: RandomForestClassifier(n_estimators=extra["n_estimators"], random_state=extra["random_state"], class_weight="balanced", n_jobs=-1),
                # SVC(probability=True) is deprecated in sklearn >= 1.9; calibration is the supported path.
                "SVC": lambda: CalibratedClassifierCV(
                    SVC(random_state=extra["random_state"], class_weight="balanced"),
                    ensemble=False, method="sigmoid",
                ),
            }
            clf = clf_map[clf_cls_name]()
            clf.fit(Xtr_s, ytr)
            prob = clf.predict_proba(Xte_s)
            pred = clf.predict(Xte_s)
            from cardia.train.evaluate import _metrics_from_preds

            m = _metrics_from_preds(yte, pred, prob, len(class_names))
            fold_res = {
                "fold": sp.fold,
                "accuracy": m["accuracy"],
                "balanced_accuracy": m["balanced_accuracy"],
                "macro_f1": m["macro_f1"],
                "macro_precision": m["macro_precision"],
                "macro_recall": m["macro_recall"],
                "auroc": m.get("auroc"),
                "n_test": m["n"],
            }
            results[clf_name].append(fold_res)
            cms[clf_name].append(m["confusion_matrix"])
            preds[clf_name].append(
                pd.DataFrame(
                    {
                        "sample_id": te["sample_id"].tolist(),
                        "true": [class_names[int(t)] for t in yte],
                        "pred": [class_names[int(p)] for p in pred],
                        "conf": [float(np.max(r)) for r in prob],
                        "probs": [" ".join(f"{v:.4f}" for v in r) for r in prob],
                    }
                )
            )
            if clf_name == "random_forest":
                feature_summaries["rf_importances"] = getattr(clf, "feature_importances_", None)
            elif clf_name == "logistic":
                feature_summaries["lr_coef_abs"] = np.abs(clf.coef_).mean(axis=0)

    summary_rows = []
    for clf_name, rows in results.items():
        df = pd.DataFrame(rows)
        mean_ba = float(df["balanced_accuracy"].mean())
        std_ba = float(df["balanced_accuracy"].std())
        mean_f1 = float(df["macro_f1"].mean())
        std_f1 = float(df["macro_f1"].std())
        mean_acc = float(df["accuracy"].mean())
        mean_auc = float(df["auroc"].dropna().mean())
        summary_rows.append(
            {
                "classifier": clf_name, "accuracy_mean": mean_acc,
                "balanced_accuracy_mean": mean_ba, "balanced_accuracy_std": std_ba,
                "macro_f1_mean": mean_f1, "macro_f1_std": std_f1,
                "auroc_mean": mean_auc,
            }
        )
        wlog.log_table(run, f"cv_folds/{clf_name}", df)

    summary = pd.DataFrame(summary_rows)
    wlog.log_table(run, "cv_summary", summary)
    run.summary.update({f"cv/{r['classifier']}_balanced_accuracy": r["balanced_accuracy_mean"] for r in summary_rows})

    # aggregated multiclass confusion matrix + predictions CSV per classifier
    import os

    from cardia.wandb_utils import viz

    os.makedirs(os.path.join(cfg.out_dir, "checkpoints"), exist_ok=True)
    for clf_name in CLASSIFIERS:
        if not cms[clf_name]:
            continue
        total_cm = np.asarray(cms[clf_name]).sum(axis=0).astype(int)
        wlog.log_fig(
            run, f"cv/{clf_name}_confusion_matrix_fig",
            viz.confusion_matrix_fig(total_cm, class_names, f"stage1 {clf_name} aggregated confusion"),
        )
        wlog.log_table(
            run, f"cv/{clf_name}_confusion_matrix",
            pd.DataFrame(total_cm, index=class_names, columns=class_names),
        )
        all_preds = pd.concat(preds[clf_name], ignore_index=True)
        scheme = f"-{cfg.class_scheme}" if cfg.class_scheme != "binary" else ""
        path = os.path.join(
            cfg.out_dir, "checkpoints",
            f"stage1-{cfg.task}-classical-{clf_name}{scheme}-s{cfg.seed}_predictions.csv",
        )
        all_preds.to_csv(path, index=False)

    # feature summary
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for key, arr in feature_summaries.items():
        if arr is None:
            continue
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.bar(range(len(arr)), arr)
        ax.set_title(key)
        ax.set_xticks([])
        wlog.log_fig(run, f"features/{key}", fig)

    metrics = {"task": cfg.task, "stage": 1, "model": "classical", "fold": None, "seed": cfg.seed}
    for r in summary_rows:
        metrics[f"{r['classifier']}_balanced_accuracy"] = r["balanced_accuracy_mean"]
        metrics[f"{r['classifier']}_macro_f1"] = r["macro_f1_mean"]
    metrics["_per_classifier"] = summary_rows
    return metrics
