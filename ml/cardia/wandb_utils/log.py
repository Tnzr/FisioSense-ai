"""WandB run init + logging helpers.

Mode logic (runtime, from env): WANDB_API_KEY set -> online, else offline
(can be synced later with `wandb sync runs/wandb`).
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
import wandb

from cardia.config import Config

PROJECT = "cardiasense-hls-cmds"


def resolve_mode(cfg: Config) -> str:
    if cfg.wandb_mode in ("online", "offline", "disabled"):
        return cfg.wandb_mode
    if os.environ.get("WANDB_API_KEY"):
        return "online"
    # no env key, but the CLI may be authenticated (netrc / settings) -> online
    try:
        from wandb import Api

        if Api().api_key:
            return "online"
    except Exception:
        pass
    return "offline"


def init_run(cfg: Config, run_name: str, run_id: Optional[str] = None) -> wandb.Run:
    mode = resolve_mode(cfg)
    entity = os.environ.get("WANDB_ENTITY")
    kwargs = dict(
        project=PROJECT,
        name=run_name,
        id=run_id,
        resume=None,
        mode=mode,
        dir=os.path.join(cfg.out_dir, "wandb"),
        config=cfg.to_dict(),
        settings=wandb.Settings(_disable_stats=True),
    )
    if entity:
        kwargs["entity"] = entity
    if mode == "disabled":
        kwargs.pop("entity", None)
    return wandb.init(**kwargs)


def log_fig(run: wandb.Run, key: str, fig, caption: str = "") -> None:
    from cardia.wandb_utils import viz

    run.log({key: wandb.Image(fig, caption=caption)})
    viz._close(fig)


def log_table(run: wandb.Run, key: str, df) -> None:
    run.log({key: wandb.Table(dataframe=df)})


def log_confusion_matrix(run: wandb.Run, key: str, y_true: np.ndarray, y_pred: np.ndarray, class_names: list) -> None:
    run.log(
        {
            key: wandb.plot.confusion_matrix(
                y_true=list(y_true.astype(int)), preds=list(y_pred.astype(int)),
                class_names=class_names, title=key,
            )
        }
    )


def log_pr_curves(run: wandb.Run, key: str, y_true, y_prob, labels: list) -> None:
    run.log({key: wandb.plot.pr_curve(y_true, y_prob, labels=labels)})


def log_audio(run: wandb.Run, key: str, samples: dict, sr: int) -> None:
    run.log({key: [wandb.Audio(np.asarray(w, dtype=np.float32), sample_rate=sr, caption=c) for c, w in samples.items()]})


def log_artifact_file(run: wandb.Run, name: str, path: str, artifact_type: str = "artifact") -> None:
    art = wandb.Artifact(name=name, type=artifact_type)
    art.add_file(path)
    run.log_artifact(art)


def finish_run(run: wandb.Run) -> None:
    run.finish()
