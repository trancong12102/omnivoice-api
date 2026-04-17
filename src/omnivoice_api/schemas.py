from pydantic import BaseModel, Field


class PresignUploadRequest(BaseModel):
    filename: str = Field("ref.wav", description="Original filename; used only to pick key suffix.")
    content_type: str | None = Field("audio/wav", description="Set Content-Type the client will PUT.")


class PresignUploadResponse(BaseModel):
    key: str
    upload_url: str
    expires_in: int
    content_type: str | None = None


class CloneRequest(BaseModel):
    text: str = Field(..., min_length=1)
    ref_audio_key: str = Field(..., description="S3 key returned by /v1/uploads/presign after client PUT.")
    ref_text: str | None = None
    num_step: int = Field(32, ge=1, le=64)
    speed: float = Field(1.0, gt=0.1, le=3.0)
    duration: float | None = Field(None, gt=0)


class DesignRequest(BaseModel):
    text: str = Field(..., min_length=1)
    instruct: str = Field(..., description="e.g. 'female, british accent, calm'")
    num_step: int = Field(32, ge=1, le=64)
    speed: float = Field(1.0, gt=0.1, le=3.0)
    duration: float | None = Field(None, gt=0)


class TTSResponse(BaseModel):
    output_key: str
    download_url: str
    expires_in: int


class HealthResponse(BaseModel):
    status: str
    device: str
    dtype: str
    model_loaded: bool
