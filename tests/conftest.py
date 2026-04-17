from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
import pytest

BASE_URL = os.getenv("OMNIVOICE_API_URL", "http://localhost:8000")
API_KEY = os.getenv("OMNIVOICE_API_KEY")


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def api(base_url: str) -> Iterator[httpx.Client]:
    try:
        probe = httpx.get(f"{base_url}/health", timeout=5.0)
        probe.raise_for_status()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"API not reachable at {base_url}: {e}")
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    with httpx.Client(
        base_url=base_url, timeout=httpx.Timeout(600.0, connect=10.0), headers=headers
    ) as c:
        yield c
