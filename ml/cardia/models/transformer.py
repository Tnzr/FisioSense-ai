"""Stage 4 small AST-style transformer: patchify -> tokens -> encoder -> CLS head."""
from __future__ import annotations

import torch
import torch.nn as nn

from cardia.config import Config


class PatchEmbed(nn.Module):
    def __init__(self, in_channels: int, d_model: int, patch: tuple) -> None:
        super().__init__()
        self.patch = patch
        self.proj = nn.Conv2d(in_channels, d_model, kernel_size=patch, stride=patch)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, 1, F, T) -> (B, n_tokens, d_model)
        x = self.proj(x)
        return x.flatten(2).transpose(1, 2)


class ASTSmall(nn.Module):
    """Small audio-spectrogram transformer (AST-style) with a dynamic
    learned positional embedding sized to the first forward pass."""

    def __init__(
        self,
        n_mels: int = 64,
        patch: tuple = (16, 16),
        d_model: int = 192,
        nhead: int = 6,
        num_layers: int = 4,
        num_classes: int = 2,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.patch = patch
        self.d_model = d_model
        self.patch_embed = PatchEmbed(1, d_model, patch)
        self.cls_token = nn.Parameter(torch.zeros(1, 1, d_model))
        self.pos_drop = nn.Dropout(dropout)
        self.blocks = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(
                d_model=d_model, nhead=nhead, dim_feedforward=d_model * 4,
                dropout=dropout, activation="gelu", batch_first=True, norm_first=True,
            ),
            num_layers=num_layers,
            # norm_first=True disables nested tensors; silence the construction warning
            enable_nested_tensor=False,
        )
        self.norm = nn.LayerNorm(d_model)
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(d_model, num_classes))
        nn.init.trunc_normal_(self.cls_token, std=0.02)
        self._pos: nn.Parameter | None = None

    def _position_embedding(self, seq_len: int, device: torch.device) -> torch.Tensor:
        if self._pos is None or self._pos.shape[1] != seq_len:
            pe = torch.zeros(1, seq_len, self.d_model, device=device)
            nn.init.trunc_normal_(pe, std=0.02)
            self._pos = nn.Parameter(pe)
        return self._pos

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        tokens = self.patch_embed(x)
        b = tokens.shape[0]
        seq = tokens.shape[1] + 1
        pos = self._position_embedding(seq, x.device)
        tokens = torch.cat([self.cls_token.expand(b, -1, -1), tokens], dim=1)
        tokens = self.pos_drop(tokens + pos)
        out = self.blocks(tokens)
        cls = self.norm(out[:, 0])
        return self.head(cls)


def build_transformer(cfg: Config, num_classes: int) -> nn.Module:
    return ASTSmall(
        n_mels=cfg.n_mels, patch=cfg.transformer_patch, d_model=cfg.transformer_d_model,
        nhead=cfg.transformer_nhead, num_layers=cfg.transformer_layers,
        num_classes=num_classes,
    )
