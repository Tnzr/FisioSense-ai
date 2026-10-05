"""Figure builders for WandB input/processing/output visualizations (Agg backend)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["figure.max_open_warning"] = 100
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402


def _close(fig) -> None:
    plt.close(fig)


def waveform_fig(y, sr: int, title: str = "raw waveform"):
    t = np.arange(len(y)) / sr
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(t, y, lw=0.5)
    ax.set_title(title)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("amplitude")
    return fig


def spec_fig(spec, title: str = "log-mel spectrogram"):
    fig, ax = plt.subplots(figsize=(10, 4))
    img = ax.imshow(spec, aspect="auto", origin="lower", cmap="magma")
    ax.set_title(title)
    ax.set_xlabel("frame")
    ax.set_ylabel("mel bin")
    fig.colorbar(img, ax=ax)
    return fig


def overlay_fig(original, filtered, sr: int, title: str = "original vs filtered"):
    t = np.arange(len(original)) / sr
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(t, original, lw=0.4, alpha=0.6, label="original (peak-normalized)")
    ax.plot(t, filtered, lw=0.6, label="band-passed")
    ax.set_title(title)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("amplitude")
    ax.legend()
    return fig


def aug_fig(spec_before, spec_after, title: str = "spectrogram before/after augmentation"):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].imshow(spec_before, aspect="auto", origin="lower", cmap="magma")
    axes[0].set_title("before")
    axes[0].set_xlabel("frame")
    axes[0].set_ylabel("mel bin")
    axes[1].imshow(spec_after, aspect="auto", origin="lower", cmap="magma")
    axes[1].set_title("after")
    axes[1].set_xlabel("frame")
    axes[1].set_ylabel("mel bin")
    fig.suptitle(title)
    return fig


def class_dist_fig(table_df):
    data = table_df.set_index("task_label")
    fig, ax = plt.subplots(figsize=(8, 4))
    cols = [c for c in data.columns if c != "total"]
    data[cols].plot.bar(ax=ax, stacked=True)
    data["total"].plot.line(ax=ax, marker="o", color="k", label="total")
    ax.set_title("class distribution by source")
    ax.set_xlabel("class")
    ax.set_ylabel("count")
    ax.legend()
    return fig


def duration_hist_fig(durations):
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.hist(durations, bins=30, color="steelblue")
    ax.set_title("recording duration histogram")
    ax.set_xlabel("duration (s)")
    ax.set_ylabel("count")
    return fig


def sqi_fig(sqi_df):
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    specs = [
        (axes[0, 0], "rms", "RMS", "steelblue", "RMS amplitude"),
        (axes[0, 1], "snr_estimate", "SNR estimate (dB)", "darkorange", "SNR estimate (dB)"),
        (axes[1, 0], "flatness", "spectral flatness", "seagreen", "spectral flatness"),
        (axes[1, 1], "clip_ratio", "clip ratio", "crimson", "clip ratio"),
    ]
    for ax, col, title, color, xlabel in specs:
        ax.hist(sqi_df[col], bins=30, color=color)
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("count")
    fig.suptitle("signal quality indicators")
    fig.tight_layout()
    return fig


def curves_fig(history: dict):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(history["epoch"], history.get("train_loss", []), label="train")
    axes[0].plot(history["epoch"], history.get("val_loss", []), label="val")
    axes[0].set_title("loss")
    axes[0].set_xlabel("epoch")
    axes[0].set_ylabel("loss")
    axes[0].legend()
    axes[1].plot(history["epoch"], history.get("val_balanced_accuracy", []), label="val bal-acc")
    axes[1].plot(history["epoch"], history.get("val_macro_f1", []), label="val macro-F1")
    axes[1].set_title("validation metrics")
    axes[1].set_xlabel("epoch")
    axes[1].set_ylabel("score")
    axes[1].legend()
    fig.tight_layout()
    return fig


def calibration_fig(ece_result: dict):
    bins = ece_result.get("bins", [])
    if not bins:
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.text(0.5, 0.5, "no bins", ha="center")
        return fig
    fig, ax = plt.subplots(figsize=(6, 5))
    accs = [b["accuracy"] for b in bins]
    confs = [b["confidence"] for b in bins]
    ns = [b["n"] for b in bins]
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfect")
    ax.scatter(confs, accs, s=[max(n, 1) for n in ns], c="steelblue", alpha=0.7)
    ax.plot(confs, accs, color="steelblue", alpha=0.5)
    ax.set_xlabel("confidence")
    ax.set_ylabel("accuracy")
    ax.set_title(f"reliability diagram (ECE={ece_result.get('ece', float('nan')):.4f})")
    ax.legend()
    return fig


def gradcam_fig(spec, heatmap, title: str = "Grad-CAM overlay"):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].imshow(spec, aspect="auto", origin="lower", cmap="magma")
    axes[0].set_title("spectrogram")
    axes[0].set_xlabel("frame")
    axes[0].set_ylabel("mel bin")
    axes[1].imshow(spec, aspect="auto", origin="lower", cmap="gray", alpha=0.6)
    axes[1].imshow(heatmap, aspect="auto", origin="lower", cmap="jet", alpha=0.5)
    axes[1].set_title(title)
    axes[1].set_xlabel("frame")
    axes[1].set_ylabel("mel bin")
    fig.tight_layout()
    return fig


def confusion_matrix_fig(cm, class_names: list, title: str = "confusion matrix", normalize: bool = True):
    """Annotated confusion-matrix heatmap.

    ``normalize=True`` colors each row relative to its ACTUAL (true) class
    counts (row-normalized -> per-class recall), so the heatmap is true to
    the inference distribution; annotations show counts and % of the actual
    class.
    """
    cm = np.asarray(cm, dtype=float)
    if normalize:
        row_sums = cm.sum(axis=1, keepdims=True)
        norm = np.divide(cm, row_sums, out=np.zeros_like(cm), where=row_sums > 0)
    else:
        norm = cm
    n = cm.shape[0]
    fig, ax = plt.subplots(figsize=(max(7, n * 0.9), max(6, n * 0.8)))
    im = ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    labels = [c if len(c) <= 14 else c[:12] + ".." for c in class_names]
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("predicted")
    ax.set_ylabel("actual (true)")
    ax.set_title(f"{title}" + (" · heatmap = % of actual class" if normalize else " · raw counts"))
    for i in range(n):
        for j in range(n):
            count = int(cm[i, j])
            pct = norm[i, j]
            if pct >= 0.03:
                ax.text(j, i, f"{count} ({pct * 100:.0f}%)", ha="center", va="center",
                        fontsize=7, color="white" if pct > 0.5 else "black")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("proportion of actual class" if normalize else "count")
    fig.tight_layout()
    return fig


def prob_dist_fig(probs, class_names: list, sample_id: str, true_label, pred_label):
    """Per-sample post-softmax probability distribution (pre-decision head view)."""
    probs = np.asarray(probs, dtype=float)
    n = len(class_names)
    colors = ["#4C72B0"] * n
    if true_label in class_names:
        colors[class_names.index(true_label)] = "#55A868"  # actual class (green)
    if pred_label in class_names and pred_label != true_label:
        colors[class_names.index(pred_label)] = "#C44E52"  # predicted class (red)
    fig, ax = plt.subplots(figsize=(max(8, n * 0.75), 4))
    ax.bar(range(n), probs, color=colors, edgecolor="black", linewidth=0.4)
    ax.set_xticks(range(n))
    labels = [c if len(c) <= 14 else c[:12] + ".." for c in class_names]
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylim(0, 1.0)
    ax.set_xlabel("class")
    ax.set_ylabel("post-softmax probability")
    ax.set_title(f"{sample_id} · actual={true_label} · predicted={pred_label} · conf={probs.max():.2f}")
    for i, v in enumerate(probs):
        if v >= 0.02:
            ax.text(i, v + 0.01, f"{v:.2f}", ha="center", fontsize=7)
    fig.tight_layout()
    return fig


def mean_probs_fig(mean_prob, class_names: list, title: str = "mean post-softmax distribution per actual class"):
    """Heatmap: row = actual class, col = predicted class; cell = MEAN
    post-softmax probability over samples of that actual class. Each row is
    the model's average pre-decision head distribution, true to inference."""
    m = np.asarray(mean_prob, dtype=float)
    n = m.shape[0]
    fig, ax = plt.subplots(figsize=(max(7, n * 0.9), max(6, n * 0.8)))
    im = ax.imshow(m, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    labels = [c if len(c) <= 14 else c[:12] + ".." for c in class_names]
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("predicted class")
    ax.set_ylabel("actual (true) class")
    ax.set_title(title)
    for i in range(n):
        for j in range(n):
            if m[i, j] >= 0.03:
                ax.text(j, i, f"{m[i, j] * 100:.0f}%", ha="center", va="center",
                        fontsize=7, color="white" if m[i, j] > 0.5 else "black")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04).set_label("mean probability")
    fig.tight_layout()
    return fig


def temporal_paired_fig(spec, duration, times, probs, classes, title: str):
    """Time-aligned view: log-mel spectrogram (top) and sliding-window
    post-softmax probabilities (bottom), sharing the time axis in seconds."""
    probs = np.asarray(probs, dtype=float)
    n = len(classes)
    fig, axes = plt.subplots(2, 1, figsize=(12, 6.5), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1.25]})
    # top: log-mel over time
    im = axes[0].imshow(spec, aspect="auto", origin="lower", cmap="magma",
                        extent=[0, duration, 0, spec.shape[0]])
    axes[0].set_ylabel("mel bin")
    axes[0].set_title(title)
    fig.colorbar(im, ax=axes[0], fraction=0.046, pad=0.02).set_label("log power")
    # bottom: probabilities vs time
    cmap = plt.get_cmap("tab20")
    for c in range(n):
        axes[1].plot(times, probs[:, c], label=classes[c], color=cmap(c % 20), lw=1.3)
    axes[1].set_ylim(0, 1)
    axes[1].set_xlabel("time (s)")
    axes[1].set_ylabel("post-softmax probability")
    axes[1].set_title("sliding-window head probabilities")
    axes[1].legend(ncol=2, fontsize=7, loc="upper right")
    # argmax ribbon
    ax2 = axes[1].twinx()
    ax2.set_yticks([])
    ax2.set_ylim(0, 1)
    for i in range(len(times)):
        c = int(probs[i].argmax())
        w = (times[1] - times[0]) if len(times) > 1 else 1.0
        ax2.axvspan(times[i] - w / 2, times[i] + w / 2, color=cmap(c % 20), alpha=0.10)
    fig.tight_layout()
    return fig


def multiscale_fig(spec, duration, scale_series, macro_probs, classes, title: str):
    """Multi-resolution temporal view: log-mel plus one probability panel per
    window scale, all time-aligned; dashed horizontal lines are the whole-clip
    (macro) distribution. Short windows localise micro events; long windows /
    the whole clip provide macro context."""
    scale_series = list(scale_series)
    n = len(scale_series)
    fig, axes = plt.subplots(1 + n, 1, figsize=(12, 2.0 + 2.0 * n), sharex=True,
                             gridspec_kw={"height_ratios": [1] + [1.15] * n})
    im = axes[0].imshow(spec, aspect="auto", origin="lower", cmap="magma",
                        extent=[0, duration, 0, spec.shape[0]])
    axes[0].set_ylabel("mel bin")
    axes[0].set_title(title)
    fig.colorbar(im, ax=axes[0], fraction=0.046, pad=0.02).set_label("log power")
    cmap = plt.get_cmap("tab20")
    for i, s in enumerate(scale_series):
        ax = axes[1 + i]
        probs = np.asarray(s["probs"], dtype=float)
        for c in range(len(classes)):
            ax.plot(s["times"], probs[:, c], color=cmap(c % 20), lw=1.2,
                    label=classes[c] if i == 0 else None)
            ax.axhline(macro_probs[c], color=cmap(c % 20), ls="--", lw=0.8, alpha=0.55)
        ax.set_ylim(0, 1)
        ax.set_ylabel(f"{s['scale_s']:g}s\nprob")
        if i == 0:
            ax.legend(ncol=2, fontsize=7, loc="upper right")
    axes[-1].set_xlabel("time (s)")
    fig.tight_layout()
    return fig
