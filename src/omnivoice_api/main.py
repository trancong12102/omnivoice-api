from __future__ import annotations

import asyncio
import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException

from .config import settings
from .schemas import (
    CloneRequest,
    DesignRequest,
    HealthResponse,
    PresignUploadRequest,
    PresignUploadResponse,
    TTSResponse,
)
from .security import require_api_key
from .service import service
from .storage import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("omnivoice_api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await asyncio.to_thread(storage.ensure_bucket)
    except Exception as e:
        log.warning("bucket ensure failed (continuing): %s", e)
    if settings.warmup_on_startup:
        service.load()
    yield


app = FastAPI(title="OmniVoice API", version="0.2.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        device=service.device,
        dtype=str(service.dtype),
        model_loaded=service.loaded,
    )


@app.post(
    "/v1/uploads/presign",
    response_model=PresignUploadResponse,
    dependencies=[Depends(require_api_key)],
)
async def presign_upload(req: PresignUploadRequest) -> PresignUploadResponse:
    suffix = Path(req.filename or "ref.wav").suffix or ".wav"
    key = storage.new_key(settings.s3_ref_prefix, suffix)
    url = await asyncio.to_thread(storage.presign_put, key, req.content_type)
    return PresignUploadResponse(
        key=key,
        upload_url=url,
        expires_in=settings.s3_presign_expires,
        content_type=req.content_type,
    )


@app.post(
    "/v1/tts/clone",
    response_model=TTSResponse,
    dependencies=[Depends(require_api_key)],
)
async def tts_clone(req: CloneRequest) -> TTSResponse:
    _validate_text(req.text)
    service.load()
    suffix = Path(req.ref_audio_key).suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        try:
            await asyncio.to_thread(storage.download_to_file, req.ref_audio_key, tmp)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"ref_audio_key not found: {e}") from e
        tmp.flush()
        wav = await asyncio.to_thread(
            service.clone,
            text=req.text,
            ref_audio_path=tmp.name,
            ref_text=req.ref_text,
            num_step=req.num_step,
            speed=req.speed,
            duration=req.duration,
        )
    return await _put_and_presign(wav)


@app.post(
    "/v1/tts/design",
    response_model=TTSResponse,
    dependencies=[Depends(require_api_key)],
)
async def tts_design(req: DesignRequest) -> TTSResponse:
    _validate_text(req.text)
    service.load()
    wav = await asyncio.to_thread(
        service.design,
        text=req.text,
        instruct=req.instruct,
        num_step=req.num_step,
        speed=req.speed,
        duration=req.duration,
    )
    return await _put_and_presign(wav)


async def _put_and_presign(wav: bytes) -> TTSResponse:
    key = storage.new_key(settings.s3_out_prefix, ".wav")
    await asyncio.to_thread(storage.upload_bytes, key, wav, "audio/wav")
    url = await asyncio.to_thread(storage.presign_get, key)
    return TTSResponse(
        output_key=key, download_url=url, expires_in=settings.s3_presign_expires
    )


def _validate_text(text: str) -> None:
    if len(text) > settings.max_text_chars:
        raise HTTPException(status_code=413, detail=f"text exceeds {settings.max_text_chars} chars")
