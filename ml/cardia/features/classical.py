"""Classical feature extraction: MFCC + spectral descriptors aggregated over frames."""
from __future__ import annotations

import numpy as np
import pandas as pd

from cardia.config import Config
from cardia.data.transforms import preprocess


def extract_audio_features(wav: np.ndarray, sr: int, n_mfcc: int = 13) -> dict:
    import librosa

    feats: dict = {}
    mfcc = librosa.feature.mfcc(y=wav, sr=sr, n_mfcc=n_mfcc)
    mfcc_d = librosa.feature.delta(mfcc)
    mfcc_d2 = librosa.feature.delta(mfcc, order=2)
    for prefix, m in (("mfcc", mfcc), ("mfcc_d", mfcc_d), ("mfcc_d2", mfcc_d2)):
        mean = m.mean(axis=1)
        std = m.std(axis=1)
        for i in range(mean.shape[0]):
            feats[f"{prefix}{i}_mean"] = float(mean[i])
            feats[f"{prefix}{i}_std"] = float(std[i])
    spec = np.abs(librosa.stft(wav, n_fft=400, hop_length=160))
    centroid = librosa.feature.spectral_centroid(S=spec, sr=sr)
    bandwidth = librosa.feature.spectral_bandwidth(S=spec, sr=sr)
    zcr = librosa.feature.zero_crossing_rate(wav)
    rms = librosa.feature.rms(y=wav)
    flatness = librosa.feature.spectral_flatness(S=spec)
    for name, seq in (
        ("centroid", centroid),
        ("bandwidth", bandwidth),
        ("zcr", zcr),
        ("rms", rms),
        ("flatness", flatness),
    ):
        feats[f"{name}_mean"] = float(seq.mean())
        feats[f"{name}_std"] = float(seq.std())
    return feats


def extract_manifest_features(manifest: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    rows = []
    for _, r in manifest.iterrows():
        wav = preprocess(r["file_path"], cfg).numpy()
        f = extract_audio_features(wav, cfg.sample_rate, cfg.mfcc_n)
        f["sample_id"] = r["sample_id"]
        f["target"] = int(r["target"])
        rows.append(f)
    return pd.DataFrame(rows)
