"""Draft cases: intake text as claims, name candidates, submit and discard. The model is a fake."""

import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import audit
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from tests.ai.fakes import FakeModel, field, page_entry, read_data
from tests.test_ingest import OPS, actions, storage, text_pdf, use_model  # noqa: F401

client = TestClient(app)


@pytest.fixture(autouse=True)
def _files_in_a_temp_folder(storage):  # noqa: F811
    """Every draft test stores its files in a temporary folder."""


def head(actor: str = OPS) -> dict:
    return {"X-Actor": actor}


ZOOM_TEXT = "Caller: my name is Rosa Linden and she works at Acme."


def make_draft(files=None, actor: str = OPS):
    files = files if files is not None else [("zoom-notes.txt", ZOOM_TEXT.encode())]
    parts = [("files", (name, io.BytesIO(data), "application/octet-stream")) for name, data in files]
    return client.post("/api/cases/draft", files=parts or None, headers=head(actor))


def sql(query: str, **params):
    with SessionLocal() as db:
        return db.execute(text(query), params).all()


def status(case_id: str) -> str:
    return sql("SELECT status FROM case_workflows WHERE case_id = :c", c=case_id)[0][0]


def submit(case_id: str, name: str, source: str = "MANUAL", source_id=None, actor: str = OPS, **extra):
    body = {"client_name": name, "name_source": source, "source_id": source_id, **extra}
    return client.post(f"/api/cases/{case_id}/submit", json=body, headers=head(actor))


def add_claim(case_id: str, source_id: str, value: str, quote: str) -> None:
    with SessionLocal() as db:
        db.execute(text("INSERT INTO claims (case_id, source_id, field_name, value, quote) VALUES (:c, :s, 'full_name', :v, :q)"),
                   {"c": case_id, "s": source_id, "v": value, "q": quote})  # fmt: skip
        db.commit()


def test_draft_from_a_pasted_note_is_a_draft_and_the_file_is_pending():
    body = make_draft().json()
    case_id = body["case_id"]
    assert status(case_id) == "DRAFT" and body["job_id"] is None
    assert body["results"][0]["status"] == "accepted" and body["results"][0]["outcome"] == "PENDING"
    assert "CASE_DRAFT_CREATED" in actions(case_id) and "UPLOAD_RECEIVED" in actions(case_id)
    with SessionLocal() as db:
        assert audit.verify_stream(db, case_id).valid


def test_draft_needs_ops_and_at_least_one_file():
    assert make_draft(actor="LEGAL-91").status_code == 403
    assert client.post("/api/cases/draft", headers=head()).status_code == 422


def test_draft_is_hidden_from_lists_but_open_to_its_creator():
    before = {a["label"]: a["case_count"] for a in client.get("/api/actors").json()}
    case_id = make_draft().json()["case_id"]
    assert case_id not in client.get("/api/cases", headers=head()).text
    assert case_id not in client.get("/api/home", headers=head()).text
    assert client.get(f"/api/documents?case={case_id}", headers=head()).json()["total"] == 0
    assert {a["label"]: a["case_count"] for a in client.get("/api/actors").json()} == before
    assert client.get(f"/api/cases/{case_id}", headers=head()).status_code == 200
    assert client.get(f"/api/cases/{case_id}/documents", headers=head()).json()["total"] == 1
    submit(case_id, "Hidden Then Shown")
    assert case_id in client.get("/api/cases", headers=head()).text


def test_a_call_note_is_read_as_a_claim_source_and_its_claims_are_stored(use_model, monkeypatch):  # noqa: F811
    monkeypatch.setenv("AUTO_READ", "true")
    get_settings.cache_clear()
    fields = {"ZOOM_NOTES.Full Name": field("Rosa Linden", "my name is Rosa Linden", 1),
              "ZOOM_NOTES.Employer": field("Globex", "works at Globex", 1)}  # fmt: skip
    use_model(FakeModel({"pages": [page_entry(1, "ZOOM_NOTES")]}, {"ZOOM_NOTES": read_data(fields, "ZOOM_NOTES")}))
    body = make_draft().json()
    upload_id = body["results"][0]["upload_id"]
    job = client.get(f"/api/jobs/{body['job_id']}", headers=head()).json()
    assert job["status"] == "SUCCEEDED" and job["events"][0]["outcome"] == "CLAIM_SOURCE"
    assert sql("SELECT outcome, category FROM uploads WHERE upload_id = :u", u=upload_id)[0] == ("CLAIM_SOURCE", "ZOOM_NOTES")
    claims = sql("SELECT source_id, field_name, value, verified, page FROM claims WHERE case_id = :c", c=body["case_id"])
    assert [tuple(c) for c in claims] == [(upload_id, "full_name", "Rosa Linden", False, 1)]
    assert sql("SELECT verified_value FROM profile_fields WHERE case_id = :c", c=body["case_id"])[0][0] == "New client (draft)"
    items = {i["category"]: i["status"] for i in client.get(f"/api/cases/{body['case_id']}/checklist", headers=head()).json()}
    assert "ZOOM_NOTES" not in items and set(items.values()) == {"MISSING"}
    names = client.get(f"/api/cases/{body['case_id']}/name-candidates", headers=head()).json()["candidates"]
    assert [(n["value"], n["source_id"], n["source_kind"]) for n in names] == [("Rosa Linden", upload_id, "COMMUNICATION")]


def test_name_candidates_show_a_document_and_an_intake_name_as_a_conflict():
    case_id = make_draft().json()["case_id"]
    add_claim(case_id, "Z-9999", "Mira Dhawan", "my name is Mira Dhawan")
    assert client.get(f"/api/cases/{case_id}/name-candidates", headers=head()).json()["conflict"] is False
    with SessionLocal() as db:
        db.execute(text(
            "INSERT INTO uploads (upload_id, case_id, storage_root, storage_path, original_filename, mime_type, file_size_bytes, "
            "sha256, uploaded_at, uploader_role, ingestion_source, client_supplied_type, version_label, outcome) "
            "VALUES ('UP-NC0001', :c, 'APP_STORAGE', 'x', 'p.pdf', 'application/pdf', 1, :h, now(), 'OPS', 'TEST', 'U', 'v', 'USABLE')"),
            {"c": case_id, "h": "a" * 64})  # fmt: skip
        extracted = {"fields": {"PASSPORT.Applicant": {"value": "Mira Dawan", "quote": "Applicant: Mira Dawan", "page": 1, "from_image": True}}}
        db.execute(text("INSERT INTO document_reads (upload_id, category, status, legible, injection_flag, extracted) "
                        "VALUES ('UP-NC0001', 'PASSPORT', 'READ', true, false, CAST(:x AS jsonb))"), {"x": json.dumps(extracted)})  # fmt: skip
        db.commit()
    body = client.get(f"/api/cases/{case_id}/name-candidates", headers=head()).json()
    assert body["conflict"] is True and body["status"] == "DONE"
    kinds = {c["source_kind"]: c for c in body["candidates"]}
    assert kinds["DOCUMENT"]["value"] == "Mira Dawan" and kinds["DOCUMENT"]["from_image"] is True and kinds["DOCUMENT"]["source_id"] == "UP-NC0001"
    assert kinds["INTAKE"]["value"] == "Mira Dhawan" and kinds["INTAKE"]["quote"] == "my name is Mira Dhawan"


def test_submit_with_an_extracted_name_and_a_manual_name():
    first = make_draft().json()["case_id"]
    add_claim(first, "Z-9998", "Tobias Wren", "name is Tobias Wren")
    assert submit(first, "Someone Else", "EXTRACTED", "Z-9998").status_code == 422
    assert submit(first, "Tobias Wren", "EXTRACTED", "Z-9998").json() == {"case_id": first, "name": "Tobias Wren"}
    row = sql("SELECT verified_value, note FROM profile_fields WHERE case_id = :c", c=first)[0]
    assert tuple(row) == ("Tobias Wren", "EXTRACTED from Z-9998") and status(first) == "NEW"
    second = make_draft().json()["case_id"]
    assert submit(second, "Priya Natarajan").status_code == 200
    assert sql("SELECT note FROM profile_fields WHERE case_id = :c", c=second)[0][0] == f"MANUAL entered by {OPS}"
    with SessionLocal() as db:
        assert audit.verify_stream(db, second).valid
        entry = [e for e in audit.list_entries(db, second, limit=10)[1] if e.action.value == "CASE_CREATED"][0]
        assert entry.details["name_source"] == "MANUAL"


def test_submit_similar_name_is_409_until_confirmed_and_twice_is_idempotent():
    first = make_draft().json()["case_id"]
    submit(first, "Odalys Ferreira")
    second = make_draft().json()["case_id"]
    again = submit(second, "ferreira odalys")
    assert again.status_code == 409 and again.json()["error"]["matches"] == [{"case_id": first, "name": "Odalys Ferreira"}]
    assert status(second) == "DRAFT"
    assert submit(second, "ferreira odalys", confirm_new=True).status_code == 200
    count = len(actions(second))
    assert submit(second, "Another Name").json() == {"case_id": second, "name": "ferreira odalys"}
    assert len(actions(second)) == count


def test_only_the_ops_user_of_the_case_can_submit_or_discard():
    case_id = make_draft().json()["case_id"]
    legal = sql("SELECT assigned_legal_reviewer FROM cases WHERE case_id = :c", c=case_id)[0][0]
    assert submit(case_id, "Nobody", actor=legal).status_code == 403
    assert client.delete(f"/api/cases/{case_id}/draft", headers=head(legal)).status_code == 403
    for actor in ("OPS-92", "LEGAL-77"):
        assert submit(case_id, "Nobody", actor=actor).status_code == 403
        assert client.delete(f"/api/cases/{case_id}/draft", headers=head(actor)).status_code == 403
        assert client.get(f"/api/cases/{case_id}/name-candidates", headers=head(actor)).status_code == 403
    assert status(case_id) == "DRAFT"
    assert sql("SELECT count(*) FROM audit_log WHERE case_id = :c AND outcome = 'DENIED'", c=case_id)[0][0] >= 6


def test_discard_removes_a_draft_and_refuses_a_submitted_case():
    case_id = make_draft().json()["case_id"]
    assert client.delete(f"/api/cases/{case_id}/draft", headers=head()).json()["status"] == "DISCARDED"
    for table in ("cases", "case_workflows", "intake_notes", "profile_fields"):
        assert sql(f"SELECT count(*) FROM {table} WHERE case_id = :c", c=case_id)[0][0] == 0
    assert client.get(f"/api/cases/{case_id}", headers=head()).status_code == 404
    with SessionLocal() as db:
        assert audit.verify_stream(db, case_id).valid
    assert "CASE_DRAFT_DISCARDED" in actions(case_id)
    kept = make_draft().json()["case_id"]
    submit(kept, "Keep Me Please")
    assert client.delete(f"/api/cases/{kept}/draft", headers=head()).status_code == 409
