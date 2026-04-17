from __future__ import annotations

import io
from pathlib import Path

import httpx
import pytest
import soundfile as sf

REF_AUDIO = Path(__file__).parent / "fixtures" / "domixi.mp3"

REF_TEXT = (
    "gương giản dị nhất, mà luôn hiện diện trong cuộc sống của chúng ta "
    "nếu như mà các bạn hay"
)

TEXT = (
    "Tôi là độ mixi, tôi là thằng tà trư, bán hàng đè tem, "
    "kêu gọi ủng hộ xây cầu xây trường hằng năm. "
    "Đội ngũ npc bợ dái rất đông và hung hãn với hàng triệu thành viên."
)

pytestmark = pytest.mark.skipif(
    not REF_AUDIO.exists(), reason=f"ref audio missing: {REF_AUDIO}"
)


def test_clone_domixi(api: httpx.Client, tmp_path: Path) -> None:
    """End-to-end: presign upload → PUT ref mp3 → clone TTS → GET result → validate WAV."""

    # 1. health
    health = api.get("/health").raise_for_status().json()
    assert health["status"] == "ok"

    # 2. presign PUT url for the mp3
    presign = (
        api.post(
            "/v1/uploads/presign",
            json={"filename": "domixi.mp3", "content_type": "audio/mpeg"},
        )
        .raise_for_status()
        .json()
    )
    assert presign["key"].endswith(".mp3")
    assert presign["upload_url"].startswith("http")
    key = presign["key"]

    # 3. upload ref mp3 directly to S3 via presigned PUT
    ref_bytes = REF_AUDIO.read_bytes()
    put = httpx.put(
        presign["upload_url"],
        content=ref_bytes,
        headers={"content-type": "audio/mpeg"},
        timeout=60.0,
    )
    assert put.status_code in (200, 204), f"PUT failed: {put.status_code} {put.text[:400]}"

    # 4. run voice clone
    clone = (
        api.post(
            "/v1/tts/clone",
            json={
                "text": TEXT,
                "ref_audio_key": key,
                "ref_text": REF_TEXT,
                "num_step": 32,
                "speed": 1.0,
            },
            timeout=httpx.Timeout(600.0, connect=10.0),
        )
        .raise_for_status()
        .json()
    )
    assert clone["output_key"].startswith("out/")
    assert clone["output_key"].endswith(".wav")
    assert clone["download_url"].startswith("http")

    # 5. download generated wav
    dl = httpx.get(clone["download_url"], timeout=120.0)
    dl.raise_for_status()
    wav_bytes = dl.content

    # 6. structural checks
    assert wav_bytes[:4] == b"RIFF", "not a RIFF/WAV container"
    assert wav_bytes[8:12] == b"WAVE"
    assert len(wav_bytes) > 50_000, f"suspicious small wav: {len(wav_bytes)} bytes"

    # 7. decode & sanity-check audio
    data, sr = sf.read(io.BytesIO(wav_bytes))
    assert sr == 24000, f"expected 24k sample rate, got {sr}"
    duration = len(data) / sr
    assert duration >= 5.0, f"output too short: {duration:.2f}s"
    assert duration <= 60.0, f"output too long: {duration:.2f}s"

    # 8. save for manual listening
    out_path = tmp_path / "domixi_clone.wav"
    out_path.write_bytes(wav_bytes)
    print(
        f"\nGenerated: {out_path}\n"
        f"  size     = {len(wav_bytes):,} bytes\n"
        f"  duration = {duration:.2f}s\n"
        f"  s3 key   = {clone['output_key']}\n"
        f"  url      = {clone['download_url']}"
    )
