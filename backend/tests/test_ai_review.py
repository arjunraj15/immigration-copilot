import uuid

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal
from app.main import app
from tests.conftest import make_case

client = TestClient(app)


def add_upload(db, case_id: str) -> str:
    upload_id = f"UP-{uuid.uuid4().hex[:8]}"
    db.execute(
        text(
            "INSERT INTO uploads (upload_id, case_id, storage_root, storage_path, original_filename, mime_type, "
            "file_size_bytes, sha256, uploaded_at, uploader_role, ingestion_source, client_supplied_type, version_label) "
            "VALUES (:u, :c, 'APP_STORAGE', 'x/a.pdf', 'scan.pdf', 'application/pdf', 100, :h, now(), 'CLIENT', 'TEST', 'UNSPECIFIED', 'v1')"
        ),
        {"u": upload_id, "c": case_id, "h": uuid.uuid4().hex + "0" * 32},
    )
    return upload_id


def add_read(db, upload_id: str, category: str, reason: str | None = None) -> None:
    db.execute(
        text("INSERT INTO document_reads (upload_id, category, status, legible, page_count, reason) VALUES (:u, :c, 'REVIEW_REQUIRED', false, 2, :r)"),
        {"u": upload_id, "c": category, "r": reason},
    )


def test_review_lists_latest_unknown_reads_only():
    case_id = f"CASE-R{uuid.uuid4().hex[:6].upper()}"
    with SessionLocal() as db:
        make_case(db, case_id)
        unknown, typed, fixed = add_upload(db, case_id), add_upload(db, case_id), add_upload(db, case_id)
        add_read(db, unknown, "UNKNOWN", "Page was blurry")
        add_read(db, typed, "RVTYPE")
        add_read(db, fixed, "UNKNOWN")
        add_read(db, fixed, "RVTYPE")
        db.commit()
    try:
        rows = {r["upload_id"]: r for r in client.get("/api/ai/review", headers={"X-Actor": "OPS-91"}).json()["items"]}
        assert unknown in rows and typed not in rows and fixed not in rows
        row = rows[unknown]
        assert row["case_id"] == case_id and row["category_label"] == "Unknown document"
        assert row["reason"] == "Page was blurry" and row["page_count"] == 2 and row["legible"] is False
    finally:
        with SessionLocal() as db:
            db.execute(text("DELETE FROM document_reads WHERE upload_id IN (:a, :b, :c)"), {"a": unknown, "b": typed, "c": fixed})
            db.execute(text("DELETE FROM uploads WHERE case_id = :c"), {"c": case_id})
            db.commit()


@pytest.fixture(autouse=True)
def read_type():
    """An enabled read type of our own, because other tests may delete the seeded ones."""
    with SessionLocal() as db:
        db.execute(text("INSERT INTO prompts (key, step, category, title) VALUES ('doc.read.rvtype', 'read', 'RVTYPE', 'Rv type') ON CONFLICT DO NOTHING"))
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(text("DELETE FROM prompts WHERE key = 'doc.read.rvtype'"))
        db.commit()


def resolve_setup():
    case_id = f"CASE-V{uuid.uuid4().hex[:6].upper()}"
    ops = f"OPS-{uuid.uuid4().int % 90 + 10}"
    with SessionLocal() as db:
        make_case(db, case_id, ops=ops)
        upload = add_upload(db, case_id)
        add_read(db, upload, "UNKNOWN")
        db.commit()
        row_id = db.execute(text("SELECT id FROM uploads WHERE upload_id = :u"), {"u": upload}).scalar_one()
    return case_id, ops, upload, row_id


def cleanup(case_id: str, upload: str) -> None:
    with SessionLocal() as db:
        db.execute(text("DELETE FROM document_reads WHERE upload_id = :u"), {"u": upload})
        db.execute(text("DELETE FROM uploads WHERE case_id = :c"), {"c": case_id})
        db.commit()


def test_resolve_sets_type_and_is_idempotent():
    case_id, ops, upload, _ = resolve_setup()
    url = f"/api/ai/review/{upload}/resolve"
    h = {"X-Actor": ops}
    try:
        assert client.post(url, json={"category": "RVTYPE", "note": "Looks like one"}, headers=h).status_code == 200
        assert client.post(url, json={"category": "rvtype"}, headers=h).status_code == 200
        assert upload not in [r["upload_id"] for r in client.get("/api/ai/review", headers=h).json()["items"]]
        with SessionLocal() as db:
            reads = db.execute(text("SELECT status, reason FROM document_reads WHERE upload_id = :u ORDER BY id"), {"u": upload}).all()
            assert db.execute(text("SELECT category FROM uploads WHERE upload_id = :u"), {"u": upload}).scalar_one() == "RVTYPE"
        assert len(reads) == 2 and reads[1].status == "READ" and reads[1].reason.startswith(f"Set by {ops}")
        assert client.post(url, json={"category": "UNKNOWN"}, headers=h).status_code == 422
        assert client.post(url, json={"category": "NOPE"}, headers=h).status_code == 422
        assert client.post("/api/ai/review/UP-missing/resolve", json={"category": "RVTYPE"}, headers=h).status_code == 404
    finally:
        cleanup(case_id, upload)


def test_review_is_scoped_to_assigned_actor():
    case_id, ops, upload, row_id = resolve_setup()
    other = {"X-Actor": "OPS-98" if ops != "OPS-98" else "OPS-97"}
    mine = {"X-Actor": ops}
    try:
        assert upload in [r["upload_id"] for r in client.get("/api/ai/review", headers=mine).json()["items"]]
        assert upload not in [r["upload_id"] for r in client.get("/api/ai/review", headers=other).json()["items"]]
        assert client.post(f"/api/ai/review/{upload}/resolve", json={"category": "RVTYPE"}, headers=other).status_code == 403
        assert client.post("/api/ai/test", json={"upload_id": row_id}, headers=other).status_code == 403
        assert client.post("/api/ai/test", json={"upload_id": row_id}, headers=mine).status_code != 403
    finally:
        cleanup(case_id, upload)


def quarantine(db, upload_id: str, reason: str = "Belongs to another client") -> None:
    db.execute(text("UPDATE uploads SET outcome = 'QUARANTINED', outcome_reason = :r, reason_code = 'WRONG_CLIENT' WHERE upload_id = :u"),
               {"r": reason, "u": upload_id})


def test_review_pages_on_the_server_and_splits_by_kind():
    case_id = f"CASE-P{uuid.uuid4().hex[:6].upper()}"
    with SessionLocal() as db:
        make_case(db, case_id)
        missed = [add_upload(db, case_id) for _ in range(3)]
        for u in missed:
            add_read(db, u, "UNKNOWN", "Page was blurry")
        held = add_upload(db, case_id)
        quarantine(db, held)
        db.commit()
    h = {"X-Actor": "OPS-91"}
    try:
        first = client.get("/api/ai/review?page=1&page_size=2", headers=h).json()
        second = client.get("/api/ai/review?page=2&page_size=2", headers=h).json()
        assert first["total"] == 4 and len(first["items"]) == 2 and len(second["items"]) == 2
        assert {r["upload_id"] for r in first["items"]}.isdisjoint(r["upload_id"] for r in second["items"])
        assert first["counts"] == {"missed": 3, "quarantined": 1}
        only = client.get("/api/ai/review?kind=quarantined", headers=h).json()
        assert [r["upload_id"] for r in only["items"]] == [held] and only["total"] == 1 and only["counts"]["missed"] == 3
        row = only["items"][0]
        assert (row["kind"], row["reason"], row["reason_code"]) == ("quarantined", "Belongs to another client", "WRONG_CLIENT")
        assert client.get("/api/ai/review?kind=missed", headers=h).json()["total"] == 3
        assert client.get(f"/api/ai/review?q={case_id.lower()}", headers=h).json()["total"] == 4
        assert client.get("/api/ai/review?q=no-such-file", headers=h).json()["total"] == 0
        assert client.get("/api/ai/review?kind=bogus", headers=h).status_code == 422
        assert client.get("/api/ai/review?page_size=500", headers=h).status_code == 422
    finally:
        with SessionLocal() as db:
            db.execute(text("DELETE FROM document_reads WHERE upload_id IN (SELECT upload_id FROM uploads WHERE case_id = :c)"), {"c": case_id})
            db.execute(text("DELETE FROM uploads WHERE case_id = :c"), {"c": case_id})
            db.commit()
