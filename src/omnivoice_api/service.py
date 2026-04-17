from __future__ import annotations

import io
import logging
import os
import threading
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

from .config import settings
from .device import pick_device, pick_dtype

log = logging.getLogger(__name__)


class OmniVoiceService:
    def __init__(self) -> None:
        self._model = None
        self._device: str = "cpu"
        self._dtype: torch.dtype = torch.float32
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def device(self) -> str:
        return self._device

    @property
    def dtype(self) -> torch.dtype:
        return self._dtype

    def load(self) -> None:
        if self._model is not None:
            return
        if settings.hf_endpoint:
            os.environ["HF_ENDPOINT"] = settings.hf_endpoint

        from omnivoice import OmniVoice

        self._device = pick_device()
        self._dtype = pick_dtype(self._device)
        log.info("loading %s on %s (%s)", settings.model_id, self._device, self._dtype)
        self._model = OmniVoice.from_pretrained(
            settings.model_id, device_map=self._device, dtype=self._dtype
        )
        log.info("model ready")

    def _generate(
        self,
        *,
        text: str,
        ref_audio: str | None = None,
        ref_text: str | None = None,
        instruct: str | None = None,
        num_step: int,
        speed: float,
        duration: float | None,
    ) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("model not loaded")
        with self._lock:
            out = self._model.generate(
                text=text,
                ref_audio=ref_audio,
                ref_text=ref_text,
                instruct=instruct,
                num_step=num_step,
                speed=speed,
                duration=duration,
            )
        audio = out[0] if isinstance(out, list) else out
        return np.asarray(audio, dtype=np.float32)

    def clone(
        self,
        *,
        text: str,
        ref_audio_path: str | Path,
        ref_text: str | None,
        num_step: int,
        speed: float,
        duration: float | None,
    ) -> bytes:
        audio = self._generate(
            text=text,
            ref_audio=str(ref_audio_path),
            ref_text=ref_text,
            num_step=num_step,
            speed=speed,
            duration=duration,
        )
        return _encode_wav(audio, settings.sample_rate)

    def design(
        self,
        *,
        text: str,
        instruct: str,
        num_step: int,
        speed: float,
        duration: float | None,
    ) -> bytes:
        audio = self._generate(
            text=text,
            instruct=instruct,
            num_step=num_step,
            speed=speed,
            duration=duration,
        )
        return _encode_wav(audio, settings.sample_rate)


def _encode_wav(audio: np.ndarray, sr: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


service = OmniVoiceService()
