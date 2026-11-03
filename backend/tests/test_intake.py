"""Create a case and add documents. The model is a fake and files go to a temporary folder."""

import io

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import audit
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from tests.test_ingest import OPS, actions, new_case, passport_model, passport_pdf, storage, text_pdf, use_model  # noqa: F401

client = TestClient(app)


def post_case(name: str, files=(), actor: str = OPS, **form):
    parts = [("files", (fname, io.BytesIO(data), "application/octet-stream")) for fname, data in files]
    return client.post("/api/cases", data={"client_name": name, **form}, files=parts or None, headers={"X-Actor": actor})


def post_docs(case_id: str, files, actor: str = OPS):
    parts = [("files", (fname, io.BytesIO(data), "application/octet-stream")) for fname, data in files]
    return client.post(f"/api/cases/{case_id}/documents", files=parts, headers={"X-Actor": actor})


def test_create_case_assigns_ops_and_legal_and_stores_pending_files(storage):  # noqa: F811
    pdf = text_pdf(["Hello"])
    body = post_case("Marisol Tanaka", [("a.pdf", pdf)]).json()
    case_id = body["case_id"]
    assert case_id.startswith("CASE-") and len(case_id) == 9
    assert body["results"][0]["status"] == "accepted" and body["results"][0]["outcome"] == "PENDING"
    with SessionLocal() as db:
        ops, legal = db.execute(text("SELECT assigned_ops_user, assigned_legal_reviewer FROM cases WHERE case_id = :c"), {"c": case_id}).one()
        expected = db.scalar(text("SELECT assigned_legal_reviewer FROM cases WHERE case_id <> :c GROUP BY 1 ORDER BY count(*), 1 LIMIT 1"), {"c": case_id})
        assert (ops, legal) == (OPS, expected)
        assert audit.verify_stream(db, case_id).valid
    assert workflow_status(case_id) == "NEW" and "CASE_CREATED" in actions(case_id) and "UPLOAD_RECEIVED" in actions(case_id)
    assert client.get(f"/api/cases/{case_id}", headers={"X-Actor": OPS}).json()["name"] == "Marisol Tanaka"
    upload_id = body["results"][0]["upload_id"]
    assert client.get(f"/api/uploads/{upload_id}/file", headers={"X-Actor": OPS}).content == pdf


def workflow_status(case_id: str) -> str:
    with SessionLocal() as db:
        return db.scalar(text("SELECT status FROM case_workflows WHERE case_id = :c"), {"c": case_id})


def test_create_case_without_files_and_next_number_grows(storage):  # noqa: F811
    first = post_case("Quentin Okafor").json()["case_id"]
    second = post_case("Ingrid Valdez").json()["case_id"]
    assert int(second[5:]) == int(first[5:]) + 1


def test_similar_name_returns_409_then_confirm_new_creates(storage):  # noqa: F811
    first = post_case("Zed Quillfeather").json()["case_id"]
    again = post_case("quillfeather  ZED")
    assert again.status_code == 409
    error = again.json()["error"]
    assert error["code"] == "POSSIBLE_DUPLICATE_CLIENT" and error["matches"] == [{"case_id": first, "name": "Zed Quillfeather"}]
    assert post_case("Zed Quillfeather", confirm_new="true").status_code == 200


def test_matches_only_show_cases_the_actor_may_see(storage):  # noqa: F811
    post_case("Hollis Brandt")
    assert post_case("Hollis Brandt", actor="OPS-92").status_code == 200


def test_only_ops_can_create_a_case(storage):  # noqa: F811
    assert post_case("Nadia Petrov", actor="LEGAL-91").status_code == 403
    assert post_case("Nadia Petrov").status_code == 200
    with SessionLocal() as db:
        denied = db.scalar(text("SELECT count(*) FROM audit_log WHERE action = 'CASE_CREATED' AND outcome = 'DENIED' AND actor = 'LEGAL-91'"))
    assert denied >= 1


def test_refused_files_get_a_reason_and_no_upload_row(storage):  # noqa: F811
    case_id = new_case()
    files = [("a.exe", b"MZ"), ("b.pdf", b"not a pdf"), ("c.pdf", b""), ("d.pdf", text_pdf(["ok"]))]
    results = post_docs(case_id, files).json()["results"]
    assert [r["status"] for r in results] == ["refused", "refused", "refused", "accepted"]
    assert all(r["reason"] for r in results[:3]) and results[0]["upload_id"] is None
    with SessionLocal() as db:
        assert db.scalar(text("SELECT count(*) FROM uploads WHERE case_id = :c"), {"c": case_id}) == 1


def test_too_many_files_is_refused(storage):  # noqa: F811
    case_id = new_case()
    assert post_docs(case_id, [("a.pdf", b"%PDF")] * 201).status_code == 400


def test_exact_duplicate_in_the_same_case_is_marked_duplicate(storage):  # noqa: F811
    case_id = new_case()
    pdf = text_pdf(["same"])
    first, second = post_docs(case_id, [("a.pdf", pdf), ("b.pdf", pdf)]).json()["results"]
    assert second["outcome"] == "DUPLICATE" and first["upload_id"] in second["reason"]
    with SessionLocal() as db:
        row = db.execute(text("SELECT outcome, duplicate_of_upload_id FROM uploads WHERE upload_id = :u"), {"u": second["upload_id"]}).one()
    assert tuple(row) == ("DUPLICATE", first["upload_id"]) and "DUPLICATE_DETECTED" in actions(case_id)


def test_documents_route_is_case_scoped(storage):  # noqa: F811
    case_id = new_case()
    assert post_docs(case_id, [("a.pdf", text_pdf(["x"]))], actor="OPS-92").status_code == 403
    assert post_docs(case_id, [("a.pdf", text_pdf(["x"]))], actor="LEGAL-92").status_code == 403
    with SessionLocal() as db:
        assert db.scalar(text("SELECT count(*) FROM uploads WHERE case_id = :c"), {"c": case_id}) == 0
        assert db.scalar(text("SELECT count(*) FROM audit_log WHERE case_id = :c AND outcome = 'DENIED'"), {"c": case_id}) == 2


def test_adding_documents_starts_the_automatic_read(storage, use_model, monkeypatch):  # noqa: F811
    model = use_model(passport_model())
    case_id = new_case()
    monkeypatch.setenv("AUTO_READ", "true")
    get_settings.cache_clear()
    result = post_docs(case_id, [("p.pdf", passport_pdf(case_id))]).json()["results"][0]
    assert model.calls
    with SessionLocal() as db:
        assert db.scalar(text("SELECT outcome FROM uploads WHERE upload_id = :u"), {"u": result["upload_id"]}) == "USABLE"
        assert db.scalar(text("SELECT count(*) FROM jobs WHERE case_id = :c AND kind = 'AUTO_READ'"), {"c": case_id}) == 1
        assert audit.verify_stream(db, case_id).valid
    assert actions(case_id).count("UPLOAD_RECEIVED") == 1


def test_creating_a_case_starts_the_read_and_the_upload_leaves_pending(storage, use_model, monkeypatch):  # noqa: F811
    model = use_model(passport_model())
    monkeypatch.setenv("AUTO_READ", "true")
    get_settings.cache_clear()
    lines = ["Identity / travel document", "Applicant: Read Test", "Reference: DOCREF-9", "Expires: 2031-03-04"]
    body = post_case("Rosalind Achterberg", [("p.pdf", text_pdf(lines))]).json()
    upload_id = body["results"][0]["upload_id"]
    assert model.calls
    with SessionLocal() as db:
        assert db.scalar(text("SELECT outcome FROM uploads WHERE upload_id = :u"), {"u": upload_id}) != "PENDING"
        assert db.scalar(text("SELECT count(*) FROM document_reads WHERE upload_id = :u"), {"u": upload_id}) >= 1
        assert db.scalar(text("SELECT count(*) FROM jobs WHERE case_id = :c AND kind = 'AUTO_READ'"), {"c": body["case_id"]}) == 1
