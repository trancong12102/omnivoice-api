from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OMNIVOICE_", env_file=".env", extra="ignore")

    model_id: str = "k2-fsa/OmniVoice"
    device: Literal["auto", "cuda", "mps", "cpu"] = "auto"
    dtype: Literal["auto", "float16", "bfloat16", "float32"] = "auto"
    sample_rate: int = 24000
    max_text_chars: int = 2000
    default_num_step: int = 32
    warmup_on_startup: bool = False
    hf_endpoint: str | None = None

    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str | None = None
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin"
    s3_region: str = "us-east-1"
    s3_bucket: str = "omnivoice"
    s3_force_path_style: bool = True
    s3_presign_expires: int = 3600
    s3_ref_prefix: str = "ref/"
    s3_out_prefix: str = "out/"
    s3_ensure_bucket: bool = True


settings = Settings()
