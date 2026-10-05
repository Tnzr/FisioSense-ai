"""Stage 2 CNN models: ResNet-18 and MobileNetV3-Small (pretrained=False)."""
from __future__ import annotations

import torch
import torch.nn as nn

from cardia.config import Config


def build_resnet18(num_classes: int, in_channels: int = 1) -> nn.Module:
    from torchvision.models import resnet18

    model = resnet18(weights=None, num_classes=num_classes)
    model.conv1 = nn.Conv2d(
        in_channels, 64, kernel_size=7, stride=2, padding=3, bias=False
    )
    return model


def build_mobilenetv3_small(num_classes: int, in_channels: int = 1) -> nn.Module:
    from torchvision.models import mobilenet_v3_small

    model = mobilenet_v3_small(weights=None, num_classes=num_classes)
    first = model.features[0][0]
    model.features[0][0] = nn.Conv2d(
        in_channels, first.out_channels, kernel_size=first.kernel_size,
        stride=first.stride, padding=first.padding, bias=False,
    )
    return model


def build_cnn(cfg: Config, num_classes: int) -> nn.Module:
    if cfg.model == "resnet18":
        return build_resnet18(num_classes)
    if cfg.model == "mobilenetv3":
        return build_mobilenetv3_small(num_classes)
    raise ValueError(f"unknown CNN model {cfg.model}")
