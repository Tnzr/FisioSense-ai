"""CardiaSense CLI: manifest -> splits -> stage dispatch with WandB logging.

Examples:
  python -m cardia.cli --task sound --stage 1 --all-folds
  python -m cardia.cli --task heart --stage 2 --model resnet18 --fold 0
  python -m cardia.cli --task lung --stage 3 --model gru --all-folds
  python -m cardia.cli --task sound --dry-run
"""
from __future__ import annotations

import json
import os
import random
import sys

import numpy as np
import pandas as pd
import torch

from cardia.config import Config, SCHEMES_BY_TASK, config_from_args
from cardia.data.hls_cmds import build_task_manifest, class_names
from cardia.data.splits import load_splits, make_splits
from cardia.train import classical_train, stages
from cardia.wandb_utils import log as wlog


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    # deterministic (math) attention backend for TransformerEncoder on CUDA
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(True)
    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
    except Exception:
        pass


def task_class_names(cfg: Config) -> list:
    return class_names(cfg.task, cfg.class_scheme)


def get_or_make_splits(cfg: Config, manifest: pd.DataFrame):
    # key includes the class scheme: lung binary vs 6-class stratify differently
    split_dir = os.path.join(cfg.out_dir, "splits", f"{cfg.task}_{cfg.class_scheme}_s{cfg.seed}")
    if os.path.isdir(split_dir):
        return load_splits(split_dir, n_folds=cfg.n_folds)
    return make_splits(manifest, n_folds=cfg.n_folds, seed=cfg.seed, out_dir=cfg.out_dir, split_dir=split_dir)


def run_dry_run(cfg: Config, manifest: pd.DataFrame, run) -> None:
    from cardia.config import Config as _C
    from cardia.data import stats as ds
    from cardia.data.transforms import Augment, MelSpec, load_wav, peak_normalize
    from cardia.wandb_utils import viz

    class_names = task_class_names(cfg)
    mel = MelSpec(cfg.sample_rate, cfg.n_mels, cfg.n_fft, cfg.hop_length)
    aug = Augment(cfg, cfg.seed)
    aug.set_epoch(0)

    wlog.log_table(run, "input/class_distribution", ds.class_distribution(manifest))
    wlog.log_table(run, "input/recordings", ds.recording_table(manifest))
    durs = ds.duration_stats(manifest)
    wlog.log_fig(run, "input/duration_histogram", viz.duration_hist_fig(durs))
    wlog.log_fig(run, "input/class_distribution_fig", viz.class_dist_fig(ds.class_distribution(manifest)))

    # splits summary + leakage table
    splits = get_or_make_splits(cfg, manifest)
    split_rows = []
    for sp in splits:
        for part in ("train", "val", "test"):
            split_rows.append({"fold": sp.fold, "part": part, "n": len(getattr(sp, part))})
    wlog.log_table(run, "splits/summary", pd.DataFrame(split_rows))

    # per-sample input/processing figures on a few examples
    examples = manifest.sample(n=min(3, len(manifest)), random_state=cfg.seed)
    for _, r in examples.iterrows():
        sid = r["sample_id"]
        raw, sr = load_wav(r["file_path"])
        wav = peak_normalize(raw)
        filt = cfg_filtered(r["file_path"], cfg)
        filt = filt.numpy()
        spec = mel(torch.from_numpy(filt)).numpy()
        wav_aug = aug.waveform(torch.from_numpy(wav.numpy()))
        spec_aug = aug.spec(mel(wav_aug)).numpy()
        wlog.log_fig(run, f"input/waveform/{sid}", viz.waveform_fig(wav.numpy(), sr, f"{sid} raw"))
        wlog.log_fig(run, f"input/filtered_overlay/{sid}", viz.overlay_fig(wav.numpy(), filt, sr, f"{sid} band-pass"))
        wlog.log_fig(run, f"input/spectrogram/{sid}", viz.spec_fig(spec, f"{sid} log-mel"))
        wlog.log_fig(run, f"processing/aug_before_after/{sid}", viz.aug_fig(spec, spec_aug, f"{sid}"))
        wlog.log_audio(run, f"processing/audio_clips/{sid}", {"raw": wav.numpy(), "filtered": filt}, sr)

    # SQI distribution
    sqi = ds.sqi_stats(manifest, n=min(200, len(manifest)))
    wlog.log_table(run, "processing/sqi_table", sqi)
    wlog.log_fig(run, "processing/sqi_distribution", viz.sqi_fig(sqi))


def cfg_filtered(path: str, cfg: Config):
    from cardia.data.transforms import preprocess

    return preprocess(path, cfg)


def _run_stage(cfg: Config, manifest: pd.DataFrame, run) -> dict:
    splits = get_or_make_splits(cfg, manifest)
    class_names = task_class_names(cfg)
    if cfg.stage == 1:
        return classical_train.run_classical(cfg, manifest, splits, class_names, run, run_name(cfg))
    run_name_full = run_name(cfg)
    all_folds = bool(getattr(cfg, "all_folds", False)) or getattr(cfg, "smoke", False)
    return stages.run_deep_stage(cfg, manifest, splits, class_names, run, run_name_full, all_folds)


def run_name(cfg: Config) -> str:
    prefix = "dryrun-" if cfg.dry_run else ""
    scheme = f"-{cfg.class_scheme}" if cfg.class_scheme != "binary" else ""
    if cfg.stage == 1:
        return f"{prefix}stage1-classical-{cfg.task}{scheme}-s{cfg.seed}"
    if cfg.all_folds or cfg.smoke:
        return f"{prefix}stage{cfg.stage}-{cfg.task}-{cfg.model}{scheme}-allfolds-s{cfg.seed}"
    return f"{prefix}stage{cfg.stage}-{cfg.task}-{cfg.model}{scheme}-fold{cfg.fold}-s{cfg.seed}"


def main(argv=None) -> int:
    cfg = config_from_args(argv)
    set_seed(cfg.seed)

    allowed_schemes = SCHEMES_BY_TASK.get(cfg.task, ("binary",))
    if cfg.class_scheme not in allowed_schemes:
        sys.exit(f"task {cfg.task} supports class schemes {allowed_schemes}, got {cfg.class_scheme}")

    if cfg.stage != 1:
        allowed = {2: stages.STAGE_2_MODELS, 3: stages.STAGE_3_MODELS, 4: stages.STAGE_4_MODELS}[cfg.stage]
        if cfg.model not in allowed:
            sys.exit(f"stage {cfg.stage} requires --model one of {allowed}, got {cfg.model}")

    manifest = build_task_manifest(cfg.data_dir, cfg.task, cfg.class_scheme, os.path.join(cfg.out_dir, "manifests"))
    print(f"[cardia] task={cfg.task} manifest={len(manifest)} samples")

    run = wlog.init_run(cfg, run_name(cfg))
    try:
        if cfg.dry_run:
            run_dry_run(cfg, manifest, run)
        else:
            metrics = _run_stage(cfg, manifest, run)
            stages._save_metrics(cfg.out_dir, metrics)
            print(json.dumps({k: v for k, v in metrics.items() if not isinstance(v, list)}, indent=2))
    finally:
        wlog.finish_run(run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
