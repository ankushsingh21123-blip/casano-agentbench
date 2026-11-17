import sys
from pathlib import Path

# Ensure `app` package is importable when pytest runs from backend/.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient backed by a throwaway SQLite file, no Bifrost env."""
    monkeypatch.setenv("AGENTBENCH_DB", str(tmp_path / "test.db"))
    monkeypatch.delenv("BIFROST_BASE_URL", raising=False)
    monkeypatch.delenv("BIFROST_API_KEY", raising=False)
    monkeypatch.delenv("BIFROST_MODEL", raising=False)
    with TestClient(app) as c:
        yield c
