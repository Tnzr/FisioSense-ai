"""Generic deep training loop: loss/acc/AUROC per epoch, cosine schedule,
early stopping, best-checkpoint eval, Grad-CAM, WandB curves + artifacts."""
from __future__ import annotations

import json
import os
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.optim.lr_scheduler import CosineAnnealingLR

from cardia.config import Config
from cardia.data.dataset import HLSDataset
from cardia.data.splits import FoldSplit
from cardia.train import evaluate as ev
from cardia.wandb_utils import log as wlog
from cardia.wandb_utils import viz


def _collate(batch):
    return {
        "x": torch.stack([b["x"] for b in batch]),
        "y": torch.stack([b["y"] for b in batch]),
        "sample_id": [b["sample_id"] for b in batch],
        "group": [b["group"] for b in batch],
    }


def _dataset_from_ids(manifest, ids: List[str], cfg: Config, augment: bool, epoch: int = 0) -> HLSDataset:
    m = manifest.set_index("sample_id").loc[ids].reset_index()
    return HLSDataset(m, cfg, augment=augment, epoch=epoch, cache=cfg.cache_features)


def _find_last_conv(module: nn.Module) -> Optional[nn.Module]:
    out = None
    for child in module.modules():
        if isinstance(child, nn.Conv2d):
            out = child
    return out


def gradcam_heatmap(model: nn.Module, x: torch.Tensor, class_idx: int, device: torch.device) -> Optional[np.ndarray]:
    last = _find_last_conv(model)
    if last is None:
        return None
    act: Dict[str, torch.Tensor] = {}
    grad: Dict[str, torch.Tensor] = {}
    fh = last.register_forward_hook(lambda m, i, o: act.__setitem__("out", o))
    bh = last.register_full_backward_hook(lambda m, gi, go: grad.__setitem__("grad", go[0]))
    model.zero_grad()
    x = x.unsqueeze(0).to(device)
    out = model(x)
    score = out[0, class_idx]
    score.backward()
    fh.remove()
    bh.remove()
    a = act["out"][0]
    g = grad["grad"][0]
    w = g.mean(dim=(1, 2), keepdim=True)
    cam = torch.relu((w * a).sum(dim=0))
    cam = cam / (cam.max() + 1e-9)
    cam = cam.unsqueeze(0).unsqueeze(0)
    target = x.shape[-2:]
    cam = torch.nn.functional.interpolate(cam, size=target, mode="bilinear", align_corners=False)
    return cam[0, 0].detach().cpu().numpy()


def run_deep_training(
    cfg: Config,
    manifest,
    fold_split: FoldSplit,
    num_classes: int,
    class_names: List[str],
    model_builder: Callable[[Config, int], nn.Module],
    run,
    run_name: str,
) -> dict:
    device = torch.device(cfg.resolve_device())
    # With in-memory waveform caching the dataset is already in RAM, so
    # prefetching in worker processes defeats the cache; use main-process workers.
    data_workers = cfg.num_workers if not cfg.cache_features else 0
    train_ds = _dataset_from_ids(manifest, fold_split.train, cfg, augment=True)
    val_ds = _dataset_from_ids(manifest, fold_split.val, cfg, augment=False)
    test_ds = _dataset_from_ids(manifest, fold_split.test, cfg, augment=False)
    train_loader = torch.utils.data.DataLoader(
        train_ds, batch_size=cfg.batch_size, shuffle=True, num_workers=data_workers,
        collate_fn=_collate, generator=torch.Generator().manual_seed(cfg.seed),
    )
    val_loader = torch.utils.data.DataLoader(
        val_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=data_workers, collate_fn=_collate
    )
    test_loader = torch.utils.data.DataLoader(
        test_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=data_workers, collate_fn=_collate
    )

    counts = np.bincount(train_ds.manifest["target"].to_numpy(), minlength=num_classes)
    weights = ev.class_weights_from_counts(counts, num_classes, device)
    wlog.log_table(run, "train_class_weights", pd.DataFrame(
        {"class": class_names, "weight": weights.tolist(), "count": counts}
    ))

    model = model_builder(cfg, num_classes).to(device)
    wlog.log_table(run, "model_summary", pd.DataFrame(
        {"name": [run_name], "n_params": [sum(p.numel() for p in model.parameters())]}
    ))
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    scheduler = CosineAnnealingLR(optimizer, T_max=cfg.epochs, eta_min=cfg.lr / 100.0)

    best_val = -1.0
    best_state: Optional[Dict] = None
    best_epoch = -1
    patience_counter = 0
    history = {
        "epoch": [], "train_loss": [], "val_loss": [], "val_accuracy": [],
        "val_balanced_accuracy": [], "val_macro_f1": [], "val_auroc": [], "lr": [],
    }

    for epoch in range(cfg.epochs):
        train_ds.set_epoch(epoch)
        model.train()
        running = 0.0
        n = 0
        for batch in train_loader:
            x, y = batch["x"].to(device), batch["y"].to(device)
            optimizer.zero_grad()
            logits = model(x)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()
            running += loss.item() * y.shape[0]
            n += y.shape[0]
        train_loss = running / max(n, 1)
        # single validation forward pass: metrics + loss together
        v = ev.evaluate(model, val_loader, device, num_classes, criterion=criterion)
        val_loss = v["loss"]
        scheduler.step()
        lr_now = scheduler.get_last_lr()[0]

        history["epoch"].append(epoch)
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["val_accuracy"].append(v["accuracy"])
        history["val_balanced_accuracy"].append(v["balanced_accuracy"])
        history["val_macro_f1"].append(v["macro_f1"])
        history["val_auroc"].append(v.get("auroc") or float("nan"))
        history["lr"].append(lr_now)
        run.log({
            "epoch": epoch,
            "train/loss": train_loss,
            "val/loss": val_loss,
            "val/accuracy": v["accuracy"],
            "val/balanced_accuracy": v["balanced_accuracy"],
            "val/macro_f1": v["macro_f1"],
            "val/auroc": v.get("auroc"),
            "lr": lr_now,
        })

        if v["balanced_accuracy"] > best_val:
            best_val = v["balanced_accuracy"]
            best_epoch = epoch
            best_state = {k: p.clone() for k, p in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= cfg.patience:
                wlog.log_table(run, "early_stop", pd.DataFrame(
                    {"stopped_at": [epoch], "best_epoch": [best_epoch], "best_val_bal_acc": [best_val]}
                ))
                break

    assert best_state is not None, "no improvement on validation set"
    model.load_state_dict(best_state)

    os.makedirs(os.path.join(cfg.out_dir, "checkpoints"), exist_ok=True)
    ckpt_path = os.path.join(cfg.out_dir, "checkpoints", f"{run_name}_best.pt")
    torch.save({"model_state": best_state, "best_val_balanced_accuracy": best_val, "epoch": best_epoch}, ckpt_path)
    wlog.log_artifact_file(run, f"{run_name}_best", ckpt_path, artifact_type="checkpoint")

    wlog.log_fig(run, "output/train_val_curves", viz.curves_fig(history))

    test = ev.evaluate(model, test_loader, device, num_classes)
    ece = ev.expected_calibration_error(test["y_true"], test["prob"])
    test["ece"] = ece["ece"]

    # Confusion matrix + PR curves
    wlog.log_confusion_matrix(run, "output/confusion_matrix", test["y_true"], test["y_pred"], class_names)
    wlog.log_fig(
        run, "output/confusion_matrix_fig",
        viz.confusion_matrix_fig(test["confusion_matrix"], class_names, f"{run_name} test confusion"),
    )
    if test["y_true"].size and test["prob"].size:
        wlog.log_pr_curves(run, "output/pr_curves", test["y_true"], test["prob"], class_names)
    wlog.log_fig(run, "output/calibration", viz.calibration_fig(ece))

    # Predictions table
    pred_df = pd.DataFrame(
        {
            "sample_id": test["ids"], "group": test["groups"],
            "true": [class_names[int(t)] for t in test["y_true"]],
            "pred": [class_names[int(p)] for p in test["y_pred"]],
            "conf": [float(np.max(r)) for r in test["prob"]],
            "probs": [" ".join(f"{v:.4f}" for v in r) for r in test["prob"]],
        }
    )
    wlog.log_table(run, "output/predictions", pred_df)
    pred_df.to_csv(os.path.join(cfg.out_dir, "checkpoints", f"{run_name}_predictions.csv"), index=False)

    # Grad-CAM on top misclassified (CNN stages only)
    if cfg.grad_cam and _find_last_conv(model) is not None and test["n"] > 0:
        mis = np.where(test["y_pred"] != test["y_true"])[0]
        top = sorted(mis, key=lambda i: float(test["prob"][i].max()))[:3]
        test_ds.set_epoch(0)
        figs = []
        for i in top:
            item = test_ds[i]
            x = item["x"].to(device)
            true_c, pred_c = int(test["y_true"][i]), int(test["y_pred"][i])
            cam = gradcam_heatmap(model, x, pred_c, device)
            if cam is not None:
                figs.append(
                    viz.gradcam_fig(
                        item["x"][0].numpy(), cam,
                        f"{test['ids'][i]}: true={class_names[true_c]} pred={class_names[pred_c]}",
                    )
                )
        for j, f in enumerate(figs):
            wlog.log_fig(run, f"output/gradcam_{j}", f)

    run.summary.update(
        {
            "test/accuracy": test["accuracy"],
            "test/balanced_accuracy": test["balanced_accuracy"],
            "test/macro_f1": test["macro_f1"],
            "test/macro_precision": test["macro_precision"],
            "test/macro_recall": test["macro_recall"],
            "test/auroc": test.get("auroc"),
            "test/ece": test["ece"],
            "test/latency_ms_per_sample": test["latency_ms_per_sample"],
            "val/best_balanced_accuracy": best_val,
            "best_epoch": best_epoch,
        }
    )

    return {
        "task": cfg.task,
        "stage": cfg.stage,
        "model": cfg.model,
        "fold": fold_split.fold,
        "seed": cfg.seed,
        "val_balanced_accuracy": best_val,
        "test_accuracy": test["accuracy"],
        "test_balanced_accuracy": test["balanced_accuracy"],
        "test_macro_f1": test["macro_f1"],
        "test_macro_precision": test["macro_precision"],
        "test_macro_recall": test["macro_recall"],
        "test_auroc": test.get("auroc"),
        "test_ece": test["ece"],
        "latency_ms_per_sample": test["latency_ms_per_sample"],
        "best_epoch": best_epoch,
        "checkpoint": ckpt_path,
        "confusion_matrix": test["confusion_matrix"],
    }
