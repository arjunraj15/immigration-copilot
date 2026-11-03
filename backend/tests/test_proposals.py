import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.cases.form_pdf import render_form_pdf
from app.db.session import SessionLocal
from app.main import app
from tests.conftest import make_case

client = TestClient(app)


def call(method: str, path: str, actor: str, **kwargs):
    return client.request(method, path, headers={"X-Actor": actor}, **kwargs)


def new_case() -> str:
    case_id = f"CASE-T{uuid.uuid4().hex[:6].upper()}"
    with SessionLocal() as db:
        make_case(db, case_id)
        db.execute(text("INSERT INTO case_workflows (case_id) VALUES (:c) ON CONFLICT DO NOTHING"), {"c": case_id})
        db.commit()
    return case_id


def propose(case_id: str, key: str | None = None, actor: str = "OPS-91"):
    body = {"kind": "FORM_EXPORT", "idempotency_key": key or uuid.uuid4().hex}
    return call("POST", f"/api/cases/{case_id}/proposals", actor, json=body)


def test_same_key_returns_same_proposal():
    case_id = new_case()
    key = uuid.uuid4().hex
    first, second = propose(case_id, key), propose(case_id, key)
    assert first.status_code == 201
    assert first.json()["proposal_id"] == second.json()["proposal_id"]


def test_only_assigned_legal_reviewer_decides():
    case_id = new_case()
    proposal_id = propose(case_id).json()["proposal_id"]
    denied = call("POST", f"/api/proposals/{proposal_id}/review", "LEGAL-92", json={"decision": "APPROVE"})
    assert denied.status_code == 403
    assert call("POST", f"/api/proposals/{proposal_id}/review", "OPS-91", json={"decision": "APPROVE"}).status_code == 403


def test_reject_needs_a_reason_and_commit_needs_approval():
    case_id = new_case()
    proposal_id = propose(case_id).json()["proposal_id"]
    assert call("POST", f"/api/proposals/{proposal_id}/review", "LEGAL-91", json={"decision": "REJECT"}).status_code == 400
    assert call("POST", f"/api/proposals/{proposal_id}/commit", "OPS-91").status_code == 409


def test_approve_commit_and_pdf_export():
    case_id = new_case()
    proposal_id = propose(case_id).json()["proposal_id"]
    assert call("GET", f"/api/proposals/{proposal_id}/export.pdf", "OPS-91").status_code == 409
    approved = call("POST", f"/api/proposals/{proposal_id}/review", "LEGAL-91", json={"decision": "APPROVE"})
    assert approved.json()["status"] == "APPROVED"
    pdf = call("GET", f"/api/proposals/{proposal_id}/export.pdf", "OPS-91")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert b"DRAFT - NOT FOR FILING" in pdf.content
    first = call("POST", f"/api/proposals/{proposal_id}/commit", "OPS-91").json()
    again = call("POST", f"/api/proposals/{proposal_id}/commit", "OPS-91").json()
    assert first["status"] == again["status"] == "COMMITTED"
    with SessionLocal() as db:
        actions = [r[0] for r in db.execute(text("SELECT action FROM audit_log WHERE case_id = :c ORDER BY seq"), {"c": case_id})]
    assert actions.count("COMMIT") == 1 and "REVIEW_APPROVE" in actions and "FORM_EXPORTED" in actions


def test_rejected_value_is_not_proposed_again():
    case_id = new_case()
    first = propose(case_id).json()["proposal_id"]
    call("POST", f"/api/proposals/{first}/review", "LEGAL-91", json={"decision": "REJECT", "reason": "Wrong spelling"})
    again = propose(case_id)
    assert again.json()["proposal_id"] == first and again.json()["status"] == "REJECTED"


def test_rejection_is_final_recorded_and_blocks_approve_and_commit():
    case_id = new_case()
    proposal_id = propose(case_id).json()["proposal_id"]
    rejected = call("POST", f"/api/proposals/{proposal_id}/review", "LEGAL-91", json={"decision": "REJECT", "reason": "Surname spelling"})
    assert rejected.json()["status"] == "REJECTED" and rejected.json()["review_reason"] == "Surname spelling"
    assert call("POST", f"/api/proposals/{proposal_id}/review", "LEGAL-91", json={"decision": "APPROVE"}).status_code >= 400
    assert call("POST", f"/api/proposals/{proposal_id}/commit", "OPS-91").status_code == 409
    assert propose(case_id, "resend-unchanged").json()["proposal_id"] == proposal_id
    with SessionLocal() as db:
        actions = [r[0] for r in db.execute(text("SELECT action FROM audit_log WHERE case_id = :c ORDER BY seq"), {"c": case_id})]
    assert "REVIEW_REJECT" in actions and "RERUN_SKIPPED_PRIOR_REJECTION" in actions and "COMMIT" not in actions


def test_pdf_renders_fields_dates_and_other_section():
    fields = [
        {"target": "applicant.date_of_birth", "value": "1986-04-09", "status": "PROPOSED", "evidence_refs": ["UP-000001"],
         "confidence": None, "needs_legal_review": True, "review_notes": ""},
        {"target": "x.extra", "value": None, "status": "HELD_FOR_REVIEW", "evidence_refs": [], "confidence": None,
         "needs_legal_review": True, "review_notes": ""},
    ]
    sections = [{"title": "Applicant details", "fields": [{"target": "applicant.date_of_birth", "label": "Date of birth", "date": True}]}]
    args = dict(case_id="CASE-1", client_name="Test", form_id="F", sections=sections, fields=fields, proposal_id="ACT-000001",
                approved_by="LEGAL-01", approved_at=datetime(2026, 10, 23, tzinfo=timezone.utc))
    pdf = render_form_pdf(**args)
    for needle in (b"04/09/1986", b"Other fields", b"HELD", b"LEGAL-01"):
        assert needle in pdf
    assert pdf == render_form_pdf(**args)


def test_list_and_get_show_the_client_name_and_scope():
    case_id = new_case()
    proposal_id = propose(case_id).json()["proposal_id"]
    listed = call("GET", "/api/proposals", "LEGAL-91").json()
    assert next(p for p in listed if p["proposal_id"] == proposal_id)["client_name"]
    one = call("GET", f"/api/proposals/{proposal_id}", "OPS-91")
    assert one.status_code == 200 and one.json()["client_name"]
    assert call("GET", f"/api/proposals/{proposal_id}", "LEGAL-92").status_code == 403


def test_activity_pages_show_the_form_export_line():
    case_id = new_case()
    proposal_id = propose(case_id).json()["proposal_id"]
    call("POST", f"/api/proposals/{proposal_id}/review", "LEGAL-91", json={"decision": "APPROVE"})
    assert call("GET", f"/api/proposals/{proposal_id}/export.pdf", "OPS-91").status_code == 200
    page = call("GET", f"/api/cases/{case_id}/audit", "OPS-91")
    assert page.status_code == 200
    assert "FORM_EXPORTED" in [line["entry"]["action"] for line in page.json()["entries"]]


def propose_kind(case_id: str, kind: str, value: dict | None = None, actor: str = "OPS-91"):
    body = {"kind": kind, "idempotency_key": uuid.uuid4().hex, "value": value}
    return call("POST", f"/api/cases/{case_id}/proposals", actor, json=body)


def test_packet_index_lists_checklist_and_refuses_an_empty_packet():
    case_id = new_case()
    packet = call("GET", f"/api/cases/{case_id}/packet", "OPS-91").json()
    assert packet["packet_id"] == f"PKT-{case_id}" and packet["usable_count"] == 0
    assert packet["items"] and all(item["status"] == "MISSING" for item in packet["items"])
    assert propose_kind(case_id, "PACKET_APPROVE").json()["error"]["code"] == "PACKET_EMPTY"


def add_upload(case_id: str, category: str, period: str | None = None) -> None:
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO uploads (upload_id, case_id, storage_root, storage_path, original_filename, mime_type, file_size_bytes, sha256, "
                 "uploaded_at, uploader_role, ingestion_source, client_supplied_type, version_label, outcome, reason_code, category, flags) "
                 "VALUES (:u, :c, 'APP_STORAGE', :u, 'a.pdf', 'application/pdf', 1, :h, now(), 'CLIENT', 'TEST', 'UNSPECIFIED', 'v1', "
                 "'USABLE', 'OK', :cat, CAST(:f AS jsonb))"),
            {"u": f"UP-U{uuid.uuid4().hex[:8].upper()}", "c": case_id, "h": uuid.uuid4().hex * 2,
             "cat": "PAY_STATEMENT" if period else category, "f": f'{{"pay_period": "{period}"}}' if period else "{}"},
        )  # fmt: skip
        db.commit()


def complete_case() -> str:
    case_id = new_case()
    for category, period in [("PASSPORT", None), ("ARRIVAL_RECORD", None), ("EMPLOYER_LETTER", None), ("PAY_AUG", "2026-08"),
                             ("PAY_SEP", "2026-09"), ("PRIOR_NOTICE", None)]:  # fmt: skip
        add_upload(case_id, category, period)
    return case_id


def test_a_packet_with_a_missing_required_document_is_refused():
    case_id = new_case()
    add_upload(case_id, "PASSPORT")
    refused = propose_kind(case_id, "PACKET_APPROVE")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "OPEN_EXCEPTIONS"
    with SessionLocal() as db:
        denied = db.execute(text("SELECT count(*) FROM audit_log WHERE case_id = :c AND action = 'PROPOSE' AND outcome = 'DENIED'"), {"c": case_id}).scalar()
    assert denied == 1


def test_a_complete_packet_is_sent_until_an_exception_opens_and_a_repeat_returns_the_first():
    case_id = complete_case()
    key = uuid.uuid4().hex
    body = {"kind": "PACKET_APPROVE", "idempotency_key": key}
    first = call("POST", f"/api/cases/{case_id}/proposals", "OPS-91", json=body)
    assert first.status_code == 201
    add_expired_passport(case_id)
    again = call("POST", f"/api/cases/{case_id}/proposals", "OPS-91", json=body)
    assert again.status_code == 201 and again.json()["proposal_id"] == first.json()["proposal_id"]
    other = propose_kind(case_id, "PACKET_APPROVE")
    assert other.status_code == 409 and other.json()["error"]["code"] == "OPEN_EXCEPTIONS"


def test_stage_change_needs_a_new_known_stage_and_applies_on_commit():
    case_id = new_case()
    assert propose_kind(case_id, "STAGE_CHANGE", {"to_stage": "NOT_A_STAGE", "reason": "x"}).json()["error"]["code"] == "STAGE_UNKNOWN"
    assert propose_kind(case_id, "STAGE_CHANGE", {"to_stage": "INTAKE_REVIEW", "reason": "x"}).json()["error"]["code"] == "STAGE_UNCHANGED"
    created = propose_kind(case_id, "STAGE_CHANGE", {"to_stage": "ON_HOLD", "reason": "Waiting on the client", "from_stage": "FAKE"})
    assert created.status_code == 201 and created.json()["value"]["from_stage"] == "INTAKE_REVIEW"
    proposal_id = created.json()["proposal_id"]
    assert call("POST", f"/api/proposals/{proposal_id}/commit", "OPS-91").status_code == 409
    call("POST", f"/api/proposals/{proposal_id}/review", "LEGAL-91", json={"decision": "APPROVE"})
    with SessionLocal() as db:
        assert db.execute(text("SELECT operational_stage FROM cases WHERE case_id = :c"), {"c": case_id}).scalar() == "INTAKE_REVIEW"
    assert call("POST", f"/api/proposals/{proposal_id}/commit", "OPS-91").status_code == 200
    with SessionLocal() as db:
        assert db.execute(text("SELECT operational_stage FROM cases WHERE case_id = :c"), {"c": case_id}).scalar() == "ON_HOLD"


def test_an_approved_stage_change_is_refused_once_the_case_has_moved_on():
    case_id = new_case()
    old = propose_kind(case_id, "STAGE_CHANGE", {"to_stage": "DOCUMENT_COLLECTION", "reason": "x"}).json()["proposal_id"]
    call("POST", f"/api/proposals/{old}/review", "LEGAL-91", json={"decision": "APPROVE"})
    with SessionLocal() as db:
        db.execute(text("UPDATE cases SET operational_stage = 'ON_HOLD' WHERE case_id = :c"), {"c": case_id})
        db.commit()
    stale = call("POST", f"/api/proposals/{old}/commit", "OPS-91")
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "STAGE_STALE"
    with SessionLocal() as db:
        assert db.execute(text("SELECT operational_stage FROM cases WHERE case_id = :c"), {"c": case_id}).scalar() == "ON_HOLD"
        assert db.execute(text("SELECT status FROM proposals WHERE proposal_id = :p"), {"p": old}).scalar() == "APPROVED"


def test_a_case_that_owes_a_document_stays_in_document_collection():
    from app.cases import stage
    from app.core.contracts import ActorRole
    from app.core.security import Actor

    ops = Actor(label="OPS-91", role=ActorRole.OPS)

    def stage_of(db, case_id: str) -> str:
        return db.execute(text("SELECT operational_stage FROM cases WHERE case_id = :c"), {"c": case_id}).scalar()

    waiting, sent = new_case(), new_case()  # no upload yet, so every required document is missing
    with SessionLocal() as db:
        db.execute(text("UPDATE cases SET operational_stage = 'WAITING_FOR_PORTAL_EVENT' WHERE case_id = :c"), {"c": waiting})
        stage.sync_documents(db, ops, waiting)
        stage.submitted(db, ops, sent)
        db.commit()
        assert stage_of(db, waiting) == "DOCUMENT_COLLECTION"  # a missing document pulls it back from the portal wait
        assert stage_of(db, sent) == "DOCUMENT_COLLECTION"  # sending the packet does not make it ready for legal


def test_legal_sends_back_with_a_note_and_nothing_is_approved():
    case_id = new_case()
    proposal_id = propose(case_id).json()["proposal_id"]
    path = f"/api/proposals/{proposal_id}/send-back"
    assert call("POST", path, "OPS-91", json={"kind": "QUESTION", "note": "why?"}).status_code == 403
    assert call("POST", path, "LEGAL-91", json={"kind": "QUESTION", "note": " "}).status_code == 400
    assert call("POST", path, "LEGAL-91", json={"kind": "DIFFERENT_DATE", "note": "Use this"}).status_code == 400
    sent = call("POST", path, "LEGAL-91", json={"kind": "DIFFERENT_DATE", "note": "Use this", "suggested_date": "2026-11-20"})
    assert sent.status_code == 200 and sent.json()["status"] == "SENT_BACK"
    assert call("POST", f"/api/proposals/{proposal_id}/commit", "OPS-91").status_code == 409
    notes = call("GET", f"/api/cases/{case_id}/notes", "OPS-91").json()
    assert notes[0]["suggested_date"] == "2026-11-20" and notes[0]["author"] == "LEGAL-91"
    with SessionLocal() as db:
        status = db.execute(text("SELECT status FROM case_workflows WHERE case_id = :c"), {"c": case_id}).scalar()
    assert status == "INFO_REQUESTED"


# ---------------------------------------------------------------- open exceptions stop the send


def add_expired_passport(case_id: str) -> None:
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO uploads (upload_id, case_id, storage_root, storage_path, original_filename, mime_type, file_size_bytes, sha256, "
                 "uploaded_at, uploader_role, ingestion_source, client_supplied_type, version_label, outcome, reason_code, category) "
                 "VALUES (:u, :c, 'APP_STORAGE', :u, 'a.pdf', 'application/pdf', 1, :h, now(), 'CLIENT', 'TEST', 'UNSPECIFIED', 'v1', "
                 "'INVALID', 'EXPIRED', 'PASSPORT')"),
            {"u": f"UP-X{uuid.uuid4().hex[:8].upper()}", "c": case_id, "h": uuid.uuid4().hex * 2},
        )  # fmt: skip
        db.commit()


def test_a_case_with_an_open_exception_cannot_be_sent_to_legal():
    case_id = new_case()
    add_expired_passport(case_id)  # an expired passport, and every other required document is missing
    refused = propose(case_id)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "OPEN_EXCEPTIONS"
    with SessionLocal() as db:
        denied = db.execute(text("SELECT count(*) FROM audit_log WHERE case_id = :c AND action = 'PROPOSE' AND outcome = 'DENIED'"), {"c": case_id}).scalar()
    assert denied == 1


def test_a_repeated_send_still_returns_the_first_proposal_after_an_exception_appears():
    case_id = new_case()
    key = uuid.uuid4().hex
    first = propose(case_id, key)
    assert first.status_code == 201
    add_expired_passport(case_id)
    again = propose(case_id, key)
    assert again.status_code == 201 and again.json()["proposal_id"] == first.json()["proposal_id"]


def test_only_serious_exceptions_stop_a_send():
    from app.cases.exceptions import ExceptionItem

    def item(kind: str, severity: str) -> ExceptionItem:
        return ExceptionItem(case_id="C", client_name="N", type=kind, severity=severity, title="t", reason="r", source_ids=[],
                             next_action="a", owner_role="OPS")  # fmt: skip

    assert item("FACT_CONFLICT", "MEDIUM").blocks_send and item("WRONG_CLIENT", "HIGH").blocks_send
    assert not item("MISSING_DOCUMENT", "HIGH").blocks_send and not item("NEEDS_TRANSLATION", "MEDIUM").blocks_send  # a client gap
    assert not item("DUPLICATE", "LOW").blocks_send and not item("SUPERSEDED", "LOW").blocks_send
    assert not item("PROPOSAL_PENDING", "MEDIUM").blocks_send and not item("PROPOSAL_REJECTED", "HIGH").blocks_send
