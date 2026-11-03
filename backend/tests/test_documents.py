import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal
from app.main import app
from tests.conftest import make_case

client = TestClient(app)


def get(path: str, actor: str):
    return client.get(path, headers={"X-Actor": actor})


def case_with_uploads(count: int, ops: str) -> str:
    case_id = f"CASE-D{uuid.uuid4().hex[:6].upper()}"
    with SessionLocal() as db:
        make_case(db, case_id, ops=ops, name="Doc Person")
        for i in range(count):
            db.execute(
                text(
                    "INSERT INTO uploads (upload_id, case_id, storage_root, storage_path, original_filename, mime_type, "
                    "file_size_bytes, sha256, uploaded_at, uploader_role, ingestion_source, client_supplied_type, version_label) "
                    "VALUES (:u, :c, 'APP_STORAGE', :p, :f, 'application/pdf', 100, :h, now(), 'CLIENT', 'TEST', 'UNSPECIFIED', 'v1')"
                ),
                {"u": f"UP-{uuid.uuid4().hex[:8]}", "c": case_id, "p": f"x/{i}.pdf", "f": f"file_{i}.pdf", "h": uuid.uuid4().hex + "0" * 32},
            )
        db.commit()
    return case_id


def test_pages_and_total():
    ops = f"OPS-{uuid.uuid4().int % 90 + 10}"
    case_id = case_with_uploads(5, ops)
    first = get(f"/api/documents?case={case_id}&page_size=2&page=1", ops).json()
    third = get(f"/api/documents?case={case_id}&page_size=2&page=3", ops).json()
    assert first["total"] == 5 and len(first["items"]) == 2 and len(third["items"]) == 1


def test_only_own_cases_and_filters():
    ops = f"OPS-{uuid.uuid4().int % 90 + 10}"
    case_id = case_with_uploads(2, ops)
    other = f"OPS-{(uuid.uuid4().int % 90 + 10)}"
    assert get(f"/api/documents?case={case_id}", other).json()["total"] == 0 if other != ops else True
    assert get(f"/api/documents?case={case_id}&client=doc person", ops).json()["total"] == 2
    assert get(f"/api/documents?case={case_id}&client=nobody", ops).json()["total"] == 0
    assert get(f"/api/documents?case={case_id}&outcome=USABLE", ops).json()["total"] == 0
    assert get("/api/documents?page_size=500", ops).status_code == 422


def test_case_documents_page_filter_and_counts():
    ops = f"OPS-{uuid.uuid4().int % 90 + 10}"
    case_id = case_with_uploads(5, ops)
    first = get(f"/api/cases/{case_id}/documents?page_size=2", ops).json()
    last = get(f"/api/cases/{case_id}/documents?page_size=2&page=3", ops).json()
    assert first["total"] == 5 and len(first["items"]) == 2 and len(last["items"]) == 1
    none = get(f"/api/cases/{case_id}/documents?outcome=USABLE,DUPLICATE", ops).json()
    assert none["total"] == 0 and none["items"] == []
    assert none["counts"] == first["counts"] and sum(first["counts"].values()) == 5
    assert get(f"/api/cases/{case_id}/documents?page_size=500", ops).status_code == 422
