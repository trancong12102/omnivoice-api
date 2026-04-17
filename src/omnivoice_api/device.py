from __future__ import annotations

import torch

from .config import settings


def pick_device() -> str:
    if settings.device != "auto":
        return settings.device
    if torch.cuda.is_available():
        return "cuda:0"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def pick_dtype(device: str) -> torch.dtype:
    if settings.dtype != "auto":
        return {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}[settings.dtype]
    if device.startswith("cuda"):
        return torch.float16
    return torch.float32


def describe() -> None:
    device = pick_device()
    dtype = pick_dtype(device)
    print(f"torch           : {torch.__version__}")
    print(f"cuda available  : {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"cuda device     : {torch.cuda.get_device_name(0)}")
        print(f"cuda version    : {torch.version.cuda}")
    print(f"mps available   : {torch.backends.mps.is_available()}")
    print(f"selected device : {device}")
    print(f"selected dtype  : {dtype}")
