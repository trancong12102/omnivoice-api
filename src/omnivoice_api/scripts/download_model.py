from __future__ import annotations

import os

from huggingface_hub import snapshot_download

from omnivoice_api.config import settings


def main() -> None:
    if settings.hf_endpoint:
        os.environ["HF_ENDPOINT"] = settings.hf_endpoint
    path = snapshot_download(repo_id=settings.model_id)
    print(f"cached at: {path}")


if __name__ == "__main__":
    main()
