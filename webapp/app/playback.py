"""Browser-playable audio for the course/game clips.

The HLS-CMDS recordings are 4 kHz WAVs: Audacity decodes them, but HTML5
`<audio>` and many native players output silence (verified in this project).
`to_playback` re-encodes a clip at PLAYBACK_SR (22.05 kHz) with the same light
compression used by `scripts/make_audio_assets.py`, so lessons, practice
rounds and quizzes play everywhere.
"""
from __future__ import annotations

import io
import os
from functools import lru_cache

import numpy as np
import soundfile as sf
import torch
import torchaudio

PLAYBACK_SR = 22050


def to_playback(w: np.ndarray, sr: int, target_db: float = -14.0,
                thresh_db: float = -24.0, ratio: float = 3.0) -> np.ndarray:
    """Lift quiet clips and resample to a universally playable rate.

    Compression (3:1 above -24 dBFS) + gain toward -14 dBFS RMS + soft-limit
    make the peak-normalised heart sounds clearly audible; resampling to
    22.05 kHz avoids silent playback of 4 kHz WAVs in strict decoders.
    """
    x = np.asarray(w, dtype=np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    thresh = 10 ** (thresh_db / 20)
    amp = np.abs(x)
    over = amp > thresh
    y = x.copy()
    y[over] = np.sign(x[over]) * (thresh + (amp[over] - thresh) / ratio)
    rms = np.sqrt(np.mean(y ** 2))
    y = y * (10 ** ((target_db - 20 * np.log10(rms + 1e-12)) / 20))
    y = np.tanh(y * 1.3) / np.tanh(1.3)
    peak = np.max(np.abs(y))
    if peak > 0.97:
        y = y * 0.97 / peak
    y = torchaudio.functional.resample(
        torch.from_numpy(y.astype(np.float32)), sr, PLAYBACK_SR).numpy()
    return y


@lru_cache(maxsize=256)
def playback_wav_bytes(path: str, mtime: float = 0.0) -> bytes:
    """Resampled, compressed WAV bytes for `path` (LRU-cached; `mtime` busts the
    cache when the source file changes)."""
    w, sr = sf.read(path, dtype="float32")
    y = to_playback(w, sr)
    buf = io.BytesIO()
    sf.write(buf, y, PLAYBACK_SR, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def playback_bytes_for(path: str) -> bytes:
    return playback_wav_bytes(path, os.path.getmtime(path))
