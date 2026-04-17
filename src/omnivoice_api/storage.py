from __future__ import annotations

import logging
import threading
import uuid
from typing import BinaryIO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from .config import settings

log = logging.getLogger(__name__)


class S3Storage:
    def __init__(self) -> None:
        self._client = None
        self._public_client = None
        self._lock = threading.Lock()

    def _build_client(self, endpoint_url: str):
        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if settings.s3_force_path_style else "virtual"},
            ),
        )

    @property
    def client(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = self._build_client(settings.s3_endpoint_url)
        return self._client

    @property
    def public_client(self):
        public = settings.s3_public_endpoint_url or settings.s3_endpoint_url
        if public == settings.s3_endpoint_url:
            return self.client
        if self._public_client is None:
            with self._lock:
                if self._public_client is None:
                    self._public_client = self._build_client(public)
        return self._public_client

    def ensure_bucket(self) -> None:
        if not settings.s3_ensure_bucket:
            return
        bucket = settings.s3_bucket
        try:
            self.client.head_bucket(Bucket=bucket)
            return
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
        log.info("creating bucket %s", bucket)
        try:
            self.client.create_bucket(Bucket=bucket)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "BucketAlreadyOwnedByYou":
                raise

    @staticmethod
    def new_key(prefix: str, suffix: str) -> str:
        if suffix and not suffix.startswith("."):
            suffix = "." + suffix
        return f"{prefix}{uuid.uuid4().hex}{suffix}"

    def presign_put(self, key: str, content_type: str | None = None) -> str:
        params: dict = {"Bucket": settings.s3_bucket, "Key": key}
        if content_type:
            params["ContentType"] = content_type
        return self.public_client.generate_presigned_url(
            "put_object", Params=params, ExpiresIn=settings.s3_presign_expires
        )

    def presign_get(self, key: str) -> str:
        return self.public_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": key},
            ExpiresIn=settings.s3_presign_expires,
        )

    def download_to_file(self, key: str, fh: BinaryIO) -> None:
        self.client.download_fileobj(settings.s3_bucket, key, fh)

    def upload_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.client.put_object(
            Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type
        )


storage = S3Storage()
