"""Deleting an uploaded file: it leaves every view, the facts forget it and the audit trail keeps who, when and why."""

import uuid

from sqlalchemy import text

from app.db.session import SessionLocal
from tests.test_facts import LEGAL, OPS, add_doc, audit_actions, call, facts, new_case


def remove(case_id: str, upload_id: str, reason: str | None = "Wrong file", actor: str = OPS):
    query = f"?reason={reason}" if reason is not None else ""
    return call("DELETE", f"/api/cases/{case_id}/documents/{upload_id}{query}", actor)


def listed(case_id: str) -> list[str]:
    return [d["upload_id"] for d in call("GET", f"/api/cases/{case_id}/documents").json()["items"]]


def test_a_deleted_file_leaves_the_views_and_the_facts_and_the_ledger_keeps_it():
    case_id = new_case("Delete Doc")
    upload_id = add_doc(case_id, "PASSPORT.Applicant", "Mira Dhawan")
    assert upload_id in listed(case_id)
    assert upload_id in str(facts(case_id)["full_name"]["sources"])
    done = remove(case_id, upload_id, "Uploaded by mistake")
    assert done.status_code == 200 and done.json() == {"upload_id": upload_id, "case_id": case_id, "status": "DELETED"}
    assert upload_id not in listed(case_id)
    assert upload_id not in str(facts(case_id)["full_name"]["sources"])
    assert call("GET", f"/api/uploads/{upload_id}/file").status_code == 404
    assert remove(case_id, upload_id).status_code == 404  # already gone
    assert ("UPLOAD_DELETED", "ALLOWED") in audit_actions(case_id)
    with SessionLocal() as db:
        row = db.execute(text("SELECT actor, details, evidence_ids FROM audit_log WHERE case_id = :c AND action = 'UPLOAD_DELETED'"), {"c": case_id}).one()
        stored = db.execute(text("SELECT deleted_by, delete_reason FROM uploads WHERE upload_id = :u"), {"u": upload_id}).one()
    assert row.actor == OPS and row.details["reason"] == "Uploaded by mistake" and row.evidence_ids == [upload_id]
    assert (stored.deleted_by, stored.delete_reason) == (OPS, "Uploaded by mistake")


def test_a_reason_is_required_and_only_the_assigned_users_may_delete():
    case_id = new_case("Delete Guard")
    upload_id = add_doc(case_id, "PASSPORT.Applicant", "Mira Dhawan")
    assert remove(case_id, upload_id, None).status_code == 422
    assert remove(case_id, upload_id, "  ").status_code == 422
    assert remove(case_id, upload_id, "Wrong file", "OPS-92").status_code == 403
    assert upload_id in listed(case_id)
    assert remove(case_id, upload_id, "Wrong file", LEGAL).status_code == 200  # the assigned legal reviewer may too


def test_a_file_cited_by_a_live_proposal_cannot_be_deleted_until_it_is_rejected():
    case_id = new_case("Delete Cited")
    upload_id = add_doc(case_id, "PASSPORT.Applicant", "Mira Dhawan")
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO proposals (case_id, kind, idempotency_key, value, evidence_ids, proposed_by) "
                 "VALUES (:c, 'PACKET_APPROVE', :k, '{}', ARRAY[:u], 'OPS-91')"),
            {"c": case_id, "k": uuid.uuid4().hex, "u": upload_id},
        )  # fmt: skip
        db.commit()
    blocked = remove(case_id, upload_id)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "UPLOAD_IN_USE"
    with SessionLocal() as db:
        db.execute(text("UPDATE proposals SET status = 'REJECTED' WHERE case_id = :c"), {"c": case_id})
        db.commit()
    assert remove(case_id, upload_id).status_code == 200


def test_deleting_the_original_of_a_duplicate_sends_the_duplicate_back_to_be_read():
    case_id = new_case("Delete Original")
    original = add_doc(case_id, "PASSPORT.Applicant", "Mira Dhawan")
    copy = add_doc(case_id, "PASSPORT.Applicant", "Mira Dhawan", outcome="DUPLICATE")
    with SessionLocal() as db:
        db.execute(text("UPDATE uploads SET duplicate_of_upload_id = :o, reason_code = 'DUPLICATE' WHERE upload_id = :u"), {"o": original, "u": copy})
        db.commit()
    assert remove(case_id, original).status_code == 200
    with SessionLocal() as db:
        row = db.execute(text("SELECT duplicate_of_upload_id, reason_code, outcome FROM uploads WHERE upload_id = :u"), {"u": copy}).one()
    assert row.duplicate_of_upload_id is None and row.reason_code is None and row.outcome in ("PENDING", "READING", "USABLE", "NEEDS_HUMAN_REVIEW")
