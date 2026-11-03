import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_db_has_pgvector() -> None:
    body = client.get("/api/health/db").json()
    assert body["status"] == "ok"


def test_embeddings_rank_related_text_higher() -> None:
    pytest.importorskip("fastembed")
    body = client.get("/api/health/embeddings").json()
    assert body["status"] == "ok"
    assert body["dimensions"] == 384


def test_ocr_engines_read_sample() -> None:
    body = client.get("/api/health/ocr").json()
    assert body["status"] == "ok"
