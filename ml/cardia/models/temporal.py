"""Stage 3 temporal model: 1D-CNN encoder -> GRU/LSTM -> classifier.

Input: log-mel spectrogram (B, F, T). The 1D CNN convolves along the time
axis treating frequency bins as channels; the GRU then models temporal
structure of the frame embeddings.
"""
from __future__ import annotations

import torch
import torch.nn as nn

from cardia.config import Config


class TemporalCNN(nn.Module):
    def __init__(
        self,
        in_channels: int,
        hidden: int = 128,
        num_layers: int = 2,
        num_classes: int = 2,
        rnn_type: str = "gru",
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        conv_layers = [
            nn.Conv1d(in_channels, 64, kernel_size=7, stride=1, padding=3),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(64, 128, kernel_size=5, stride=1, padding=2),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(128, hidden, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm1d(hidden),
            nn.ReLU(),
        ]
        self.conv = nn.Sequential(*conv_layers)
        rnn_cls = nn.GRU if rnn_type == "gru" else nn.LSTM
        self.rnn = rnn_cls(
            input_size=hidden, hidden_size=hidden, num_layers=num_layers,
            batch_first=True, dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.LayerNorm(hidden), nn.Dropout(dropout), nn.Linear(hidden, num_classes)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, 1, F, T) -> (B, F, T) -> conv over T -> (B, hidden, T') -> (B, T', hidden)
        x = x.squeeze(1)
        x = self.conv(x).transpose(1, 2)
        out, _ = self.rnn(x)
        # mean-pool over time
        pooled = out.mean(dim=1)
        return self.head(pooled)


def build_temporal(cfg: Config, num_classes: int) -> nn.Module:
    return TemporalCNN(
        in_channels=cfg.n_mels,
        hidden=cfg.temporal_hidden,
        num_layers=cfg.temporal_layers,
        num_classes=num_classes,
        rnn_type=cfg.model,
    )
