"""Offline Growth Engine tests: never load local credentials or write real logs."""
import importlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest

_ENV = {
    "ARCHAI_MCP_TOKEN": "test-token-at-least-24-chars-long",
    "ARCHAI_TOKEN": "test-core-api-token",
    "ARCHAI_URL": "http://127.0.0.1:8000",
    "ARCHAI_PUBLIC_URL": "http://127.0.0.1:8765",
}
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
_exists = Path.exists


def _without_local_env(path):
    return False if path == _ENV_FILE else _exists(path)


# Scope environment changes to this import, and prevent _load_env from reading secrets.
with patch.dict(os.environ, _ENV), patch.object(Path, "exists", _without_local_env):
    server = importlib.import_module("growth_engine.server")


@pytest.fixture(autouse=True)
def isolate_growth_engine(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "KAYIT", tmp_path / "kampanya.json")
    monkeypatch.setattr(server, "ARCHAI", _ENV["ARCHAI_URL"])
    monkeypatch.setattr(server, "ARCHAI_TOKEN", _ENV["ARCHAI_TOKEN"])
