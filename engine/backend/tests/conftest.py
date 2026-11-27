from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def tmp_media(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.fixture()
def settings_env(tmp_path, monkeypatch):
    """Isolated dirs + DB per test; worker off (API tests must not need a GPU)."""
    for k, sub in [("UPLOAD_DIR", "u"), ("TEMP_DIR", "t"), ("OUTPUT_DIR", "o"), ("MODEL_DIR", "m")]:
        monkeypatch.setenv(f"CLIPMITRA_{k}", str(tmp_path / sub))
    monkeypatch.setenv("CLIPMITRA_DB_PATH", str(tmp_path / "db" / "t.db"))
    monkeypatch.setenv("CLIPMITRA_MAX_DURATION_SECONDS", "10")
    monkeypatch.setenv("CLIPMITRA_WORKER_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def client(settings_env):
    from app.main import create_app
    with TestClient(create_app()) as c:
        yield c
