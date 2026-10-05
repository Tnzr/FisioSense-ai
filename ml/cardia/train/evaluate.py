"""Evaluation: accuracy, balanced accuracy, P/R/F1, AUROC, confusion matrix,
calibration (ECE), latency."""
from __future__ import annotations

import time
from typing import Dict, List, Optional

import numpy as np
import torch
import torch.nn as nn


def evaluate(
    model: nn.Module,
    loader: torch.utils.data.DataLoader,
    device: torch.device,
    num_classes: int,
    criterion: Optional[nn.Module] = None,
) -> dict:
    """Run inference over a loader and return full metrics + raw arrays.

    When ``criterion`` is given, the (unweighted-aware) loss is accumulated in
    the SAME forward pass, so validation is a single pass per epoch.
    """
    model.eval()
    all_ids: List[str] = []
    all_groups: List[str] = []
    all_y: List[np.ndarray] = []
    all_probs: List[np.ndarray] = []
    start = time.perf_counter()
    n_examples = 0
    loss_sum = 0.0
    with torch.no_grad():
        for batch in loader:
            x = batch["x"].to(device)
            y = batch["y"].to(device)
            logits = model(x)
            if criterion is not None:
                loss_sum += criterion(logits, y).item() * y.shape[0]
            probs = torch.softmax(logits, dim=1)
            all_ids.extend(batch["sample_id"])
            all_groups.extend(batch["group"])
            all_y.append(y.cpu().numpy())
            all_probs.append(probs.cpu().numpy())
            n_examples += y.shape[0]
    wall = time.perf_counter() - start
    y = np.concatenate(all_y)
    prob = np.concatenate(all_probs)
    pred = prob.argmax(axis=1)

    metrics = _metrics_from_preds(y, pred, prob, num_classes)
    metrics["ids"] = all_ids
    metrics["groups"] = all_groups
    metrics["y_true"] = y
    metrics["y_pred"] = pred
    metrics["prob"] = prob
    metrics["latency_ms_per_sample"] = float(wall * 1000.0 / max(n_examples, 1))
    if criterion is not None:
        metrics["loss"] = loss_sum / max(n_examples, 1)
    return metrics


def _metrics_from_preds(y: np.ndarray, pred: np.ndarray, prob: np.ndarray, num_classes: int) -> dict:
    from sklearn.metrics import (
        accuracy_score,
        balanced_accuracy_score,
        classification_report,
        confusion_matrix,
        roc_auc_score,
    )

    acc = float(accuracy_score(y, pred))
    bal_acc = float(balanced_accuracy_score(y, pred))
    report = classification_report(
        y, pred, labels=list(range(num_classes)), output_dict=True, zero_division=0
    )
    macro_f1 = float(report["macro avg"]["f1-score"])
    macro_prec = float(report["macro avg"]["precision"])
    macro_rec = float(report["macro avg"]["recall"])
    cm = confusion_matrix(y, pred, labels=list(range(num_classes))).astype(int)

    auroc = None
    if num_classes == 2:
        auroc = float(roc_auc_score(y, prob[:, 1]))
    else:
        try:
            auroc = float(roc_auc_score(y, prob, multi_class="ovr", average="macro"))
        except ValueError:
            auroc = None

    per_class = {}
    for c in range(num_classes):
        per_class[c] = {
            "precision": report[str(c)]["precision"],
            "recall": report[str(c)]["recall"],
            "f1": report[str(c)]["f1-score"],
            "support": report[str(c)]["support"],
        }
    return {
        "accuracy": acc,
        "balanced_accuracy": bal_acc,
        "macro_f1": macro_f1,
        "macro_precision": macro_prec,
        "macro_recall": macro_rec,
        "auroc": auroc,
        "confusion_matrix": cm,
        "per_class": per_class,
        "n": int(len(y)),
    }


def expected_calibration_error(y: np.ndarray, prob: np.ndarray, n_bins: int = 15) -> dict:
    """Binned calibration (ECE) on the predicted class confidence."""
    conf = prob.max(axis=1)
    correct = prob.argmax(axis=1) == y
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    bin_stats = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (conf >= lo) & ((conf < hi) | (i == n_bins - 1))
        n = int(mask.sum())
        if n == 0:
            continue
        acc = float(correct[mask].mean())
        conf_m = float(conf[mask].mean())
        bin_stats.append(
            {"bin": i, "lower": float(lo), "upper": float(hi), "n": n, "accuracy": acc, "confidence": conf_m}
        )
        ece += n * abs(acc - conf_m)
    ece /= max(len(y), 1)
    return {"ece": float(ece), "bins": bin_stats}


def class_weights_from_counts(counts: np.ndarray, num_classes: int, device: torch.device) -> torch.Tensor:
    """Square-root-damped inverse-frequency class weights from per-class counts."""
    c = torch.as_tensor(counts, dtype=torch.float32).clamp(min=1.0)
    inv = 1.0 / c
    weights = torch.sqrt(inv / inv.sum()) * num_classes
    return weights.to(device)
