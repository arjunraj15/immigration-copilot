import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.cases.uploads import resolve_path
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.main import app
from tests.conftest import make_case

client = TestClient(app)
OPS = "OPS-91"


def add_upload(root: str, path: str, case_id: str | None = None) -> str:
    case_id = case_id or f"CASE-U{uuid.uuid4().hex[:6].upper()}"
    upload_id = f"UP-T{uuid.uuid4().hex[:7]}"
    with SessionLocal() as db:
        make_case(db, case_id, ops=OPS)
        db.execute(
            text(
                "INSERT INTO uploads (upload_id, case_id, storage_root, storage_path, original_filename, mime_type, "
                "file_size_bytes, sha256, uploaded_at, uploader_role, ingestion_source, client_supplied_type, version_label) "
                "VALUES (:u, :c, :r, :p, 'note.txt', 'text/plain', 5, :h, now(), 'CLIENT', 'TEST', 'UNSPECIFIED', 'v1')"
            ),
            {"u": upload_id, "c": case_id, "r": root, "p": path, "h": uuid.uuid4().hex + "0" * 32},
        )
        db.commit()
    return upload_id


def fetch(upload_id: str, actor: str = OPS):
    return client.get(f"/api/uploads/{upload_id}/file", headers={"X-Actor": actor})


def stored_file(tmp_path, monkeypatch, name: str = "note.txt") -> None:
    (tmp_path / name).write_bytes(b"hello")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()


def test_assigned_ops_gets_bytes(tmp_path, monkeypatch):
    stored_file(tmp_path, monkeypatch)
    response = fetch(add_upload("APP_STORAGE", "note.txt"))
    assert response.status_code == 200 and response.content == b"hello"
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["content-disposition"].startswith("inline")
    get_settings.cache_clear()


def test_other_user_is_denied(tmp_path, monkeypatch):
    stored_file(tmp_path, monkeypatch)
    upload_id = add_upload("APP_STORAGE", "note.txt")
    assert fetch(upload_id, "OPS-92").status_code == 403
    get_settings.cache_clear()


def test_path_traversal_and_unknown_root_are_refused(tmp_path, monkeypatch):
    stored_file(tmp_path, monkeypatch)
    assert fetch(add_upload("APP_STORAGE", "../note.txt")).status_code == 404
    assert fetch(add_upload("APP_STORAGE", "/etc/passwd")).status_code == 404
    with pytest.raises(AppError):
        resolve_path("ELSEWHERE", "note.txt")  # the table only allows known roots, so check the helper
    get_settings.cache_clear()


def test_missing_file_and_unknown_upload(tmp_path, monkeypatch):
    stored_file(tmp_path, monkeypatch)
    response = fetch(add_upload("APP_STORAGE", "gone.txt"))
    assert response.status_code == 404 and response.json()["error"]["code"] == "UPLOAD_FILE_MISSING"
    assert fetch("UP-NOPE").status_code == 404
    get_settings.cache_clear()


def test_starter_kit_file(monkeypatch):
    monkeypatch.setenv("STARTER_KIT_DIR", "/data/starter-kit")
    get_settings.cache_clear()
    response = fetch(add_upload("STARTER_KIT", "06_synthetic_documents/CASE-0001/UP-000001_scan_1_upload.pdf"))
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
