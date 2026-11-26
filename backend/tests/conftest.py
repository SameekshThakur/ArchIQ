import os
import sys
from pathlib import Path

import tempfile

os.environ.setdefault("AI_LATENCY", "0")
os.environ["PROVIDER"] = "mock"  # tests never call a real model, whatever backend/.env says
os.environ["AZURE_OPENAI_API_KEY"] = ""
os.environ["AZURE_OPENAI_ENDPOINT"] = ""
os.environ["ARCHIQ_DB"] = str(Path(tempfile.mkdtemp(prefix="archiq-test-")) / "test.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def store():
    from app.repositories.store import get_store

    return get_store()


@pytest.fixture(autouse=True)
def _reset_uploaded_documents():
    yield
    from app.mock_ai.generators import documents

    documents.reset_uploads()
