"""Timeline rules. The proposed deadline reuses the home page due date math and never reads the system clock."""

import uuid
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases import home, service
from app.cases.communications import Communication
from app.core import audit
from app.core.audit import AuditEntry
from app.core.contracts import ActorRole, AuditAction, AuditOutcome
from app.core.security import Actor
from app.db.session import SessionLocal
from app.main import app
from tests.conftest import make_case

client = TestClient(app)


def _event(event_id: str, day: date, kind: str, source: str, verified: bool) -> dict:
    return {"event_id": event_id, "event_date": day, "event_type": kind, "event_source": source,
            "source_verified": verified, "details": ""}  # fmt: skip


RULE = home.Rule(event_type="REQ", source="MOCK_PORTAL", verified_required=True, offset_days=10)


def test_proposed_deadline_and_wrong_calendar_entry() -> None:
    events = [
        _event("EV-RFE", date(2026, 10, 14), "REQ", "MOCK_PORTAL", True),
        _event("EV-CAL", date(2026, 10, 27), "CALENDAR_DEADLINE", "GOOGLE_CALENDAR_MOCK", False),
    ]
    as_of = date(2026, 10, 23)
    due = home.build_due(events, RULE, False, as_of)
    items = service.build_timeline(events, as_of, due)
    assert [i.kind for i in items] == ["verified", "today", "proposed", "wrong"]
    proposed = items[2]
    assert proposed.date == date(2026, 10, 24) and proposed.lane == "portal"
    assert all(i.why for i in items if i.kind != "today")


def test_unverified_request_proposes_nothing() -> None:
    events = [_event("EV-RFE", date(2026, 10, 14), "REQ", "MOCK_PORTAL", False)]
    due = home.build_due(events, RULE, False, date(2026, 10, 23))
    assert due is None
    assert [i.kind for i in service.build_timeline(events, date(2026, 10, 23), due)] == ["unverified", "today"]


def test_matching_calendar_entry_is_not_marked_wrong() -> None:
    events = [
        _event("EV-RFE", date(2026, 10, 14), "REQ", "MOCK_PORTAL", True),
        _event("EV-CAL", date(2026, 10, 24), "CALENDAR_DEADLINE", "GOOGLE_CALENDAR_MOCK", False),
    ]
    due = home.build_due(events, RULE, False, date(2026, 10, 23))
    kinds = [i.kind for i in service.build_timeline(events, date(2026, 10, 23), due)]
    assert "wrong" not in kinds


def _comm(source_id: str, kind: str, direction: str, at: str, role: str = "UPDATE", **extra: str) -> Communication:
    return Communication(source_id=source_id, kind=kind, direction=direction, sender_role="CLIENT", subject=None,
                         body=extra.get("body", "Can you tell me the status?"), thread_id=None, occurred_at=at,
                         is_draft=direction == "OUTBOUND_DRAFT_ONLY", client_question=False, claims=0, role=role,
                         draft_status=extra.get("draft_status"))  # fmt: skip


def test_calls_and_messages_join_the_timeline_as_claims() -> None:
    comms = [
        _comm("Z-1", "ZOOM", "NOTE", "2026-10-12T14:00:00+00:00", role="INTAKE_CALL"),
        _comm("MSG-1", "EMAIL", "OUTBOUND_DRAFT_ONLY", "2026-10-15T10:10:00+00:00", role="OFFICE_DRAFT"),
        _comm("MSG-2", "WHATSAPP", "INBOUND", "2026-10-25T12:10:00+00:00"),
    ]
    events = [_event("EV-RFE", date(2026, 10, 14), "REQ", "MOCK_PORTAL", True)]
    items = service.build_timeline(events, date(2026, 10, 23), None, service.communication_items(comms))
    assert [i.ref for i in items] == ["Z-1", "EV-RFE", "MSG-1", None, "MSG-2"]
    calls = [i for i in items if i.lane == "communication"]
    assert all(i.kind == "claim" and i.why == service.WHY_COMMUNICATION for i in calls)
    titles = ["Zoom intake call", "Email from the office, not sent", "WhatsApp from the client"]
    assert [i.title for i in calls] == titles


def test_app_drafts_stay_off_the_timeline_and_long_text_is_cut() -> None:
    comms = [
        _comm("DR-1", "EMAIL", "OUTBOUND_DRAFT_ONLY", "2026-10-20T09:00", "OFFICE_DRAFT", draft_status="DRAFT"),
        _comm("MSG-3", "EMAIL", "INBOUND", "2026-10-20T09:00:00+00:00", body="word " * 100),
    ]
    items = service.communication_items(comms)
    assert [i.ref for i in items] == ["MSG-3"]
    assert len(items[0].note) <= service.NOTE_LIMIT + 3 and items[0].note.endswith("...")


def test_timeline_route_lists_the_intake_call_and_messages(db: Session) -> None:
    owner = db.execute(text("SELECT assigned_ops_user FROM cases WHERE case_id = 'CASE-0009'")).scalar_one()
    body = client.get("/api/cases/CASE-0009/timeline", headers={"X-Actor": owner}).json()
    calls = [i for i in body["items"] if i["lane"] == "communication"]
    assert calls[0]["title"] == "Zoom intake call"
    assert {"MSG-0009-2", "MSG-0009-4"} <= {i["ref"] for i in calls}


def _ledger(seq: int, actor: str, action: AuditAction, outcome: AuditOutcome = AuditOutcome.ALLOWED,
            target: tuple[str, str] | None = None) -> AuditEntry:  # fmt: skip
    role = ActorRole.SYSTEM if actor == "SYSTEM" else ActorRole(actor.split("-")[0])
    return AuditEntry(id=seq, stream_id="CASE-T", seq=seq, occurred_at=datetime(2026, 10, 20, 9, seq, tzinfo=UTC),
                      actor=actor, actor_role=role, action=action, outcome=outcome, case_id="CASE-T",
                      target_type=target[0] if target else None, target_id=target[1] if target else None,
                      before_state=None, after_state=None, evidence_ids=[], idempotency_key=None, request_id=None,
                      prompt_run_id=None, details={}, prev_hash="0" * 64, row_hash="0" * 64)  # fmt: skip


def test_case_activity_lists_staff_actions_with_who_did_them() -> None:
    entries = [
        _ledger(1, "SYSTEM", AuditAction.SEED_LOADED),
        _ledger(2, "OPS-02", AuditAction.UPLOAD_RECEIVED, target=("upload", "UP-000001")),
        _ledger(3, "OPS-02", AuditAction.DOCUMENT_READ, target=("upload", "UP-000001")),
        _ledger(4, "LEGAL-01", AuditAction.CHAIN_VERIFIED),
        _ledger(5, "OPS-02", AuditAction.PROPOSE, target=("proposal", "P-1")),
        _ledger(6, "OPS-02", AuditAction.REVIEW_APPROVE, AuditOutcome.DENIED, target=("proposal", "P-1")),
        _ledger(7, "LEGAL-01", AuditAction.REVIEW_APPROVE, target=("proposal", "P-1")),
    ]
    items = service.activity_items(entries)
    assert [i.title for i in items] == [
        "OPS-02 uploaded a file", "OPS-02 proposed a change",
        "OPS-02 tried to do this and was refused: approved a proposal", "LEGAL-01 approved a proposal",
    ]  # fmt: skip
    assert all(i.lane == "activity" and i.date == date(2026, 10, 20) for i in items)
    assert [i.kind for i in items] == ["activity", "activity", "refused", "activity"]
    assert [i.ref for i in items] == ["UP-000001", None, None, None]
    assert items[0].why == "Done by OPS-02, operations. Recorded in the audit ledger."
    assert items[3].why == "Done by LEGAL-01, legal. Recorded in the audit ledger."


def test_timeline_route_shows_an_upload_in_case_activity(db: Session) -> None:
    case_id = f"CASE-T{uuid.uuid4().hex[:6].upper()}"
    with SessionLocal() as session:
        make_case(session, case_id, ops="OPS-93")
        audit.record(session, actor=Actor(label="OPS-93", role=ActorRole.OPS), action=AuditAction.UPLOAD_RECEIVED,
                     case_id=case_id, target_type="upload", target_id="UP-T1")  # fmt: skip
        session.commit()
    body = client.get(f"/api/cases/{case_id}/timeline", headers={"X-Actor": "OPS-93"}).json()
    activity = [i for i in body["items"] if i["lane"] == "activity"]
    assert [(i["title"], i["ref"]) for i in activity] == [("OPS-93 uploaded a file", "UP-T1")]


def test_timeline_route_includes_the_proposed_deadline(db: Session) -> None:
    owner = db.execute(text("SELECT assigned_ops_user FROM cases WHERE case_id = 'CASE-0009'")).scalar_one()
    body = client.get("/api/cases/CASE-0009/timeline", headers={"X-Actor": owner}).json()
    proposed = [i for i in body["items"] if i["kind"] == "proposed"]
    assert len(proposed) == 1
    assert proposed[0]["ref"] == "EV-0009-RFE"
    request = next(i for i in body["items"] if i["ref"] == "EV-0009-RFE" and i["kind"] == "verified")
    assert proposed[0]["date"] > request["date"]


def test_approved_calendar_note_is_explained_as_an_unverified_status() -> None:
    note = _event("CAL-NOTE", date(2026, 10, 21), "CALENDAR_NOTE", "GOOGLE_CALENDAR_MOCK", False)
    note["details"] = "Calendar title: APPROVED, placeholder"
    item = service.build_timeline([note], date(2026, 10, 23))[0]
    assert item.kind == "unverified" and item.why == service.WHY_STATUS


def test_deadline_proposal_value_is_recomputed_by_the_server(db: Session) -> None:
    owner = db.execute(text("SELECT assigned_ops_user FROM cases WHERE case_id = 'CASE-0009'")).scalar_one()
    url, headers = "/api/cases/CASE-0009/proposals", {"X-Actor": owner}
    body = {"kind": "DEADLINE_ACTIVATE", "idempotency_key": "ws2b-deadline-bad-1", "evidence_ids": ["EV-0009-RFE"],
            "value": {"due_date": "2026-10-27", "rule_version": "SYN-DEADLINE-V1", "trigger_event_id": "EV-0009-RFE"}}  # fmt: skip
    refused = client.post(url, json=body, headers=headers)
    assert refused.status_code == 400 and refused.json()["error"]["code"] == "DEADLINE_MISMATCH"
