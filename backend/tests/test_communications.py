"""Communication list. Records are inserted directly, so no model is called."""

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal
from app.main import app
from tests.test_ingest import OPS, new_case

client = TestClient(app)


def run(query: str, **params) -> None:
    with SessionLocal() as db:
        db.execute(text(query), params)
        db.commit()


def note(case_id: str, intake_id: str, when: str, speaker: str = "Intake Coordinator") -> None:
    run("INSERT INTO intake_notes (intake_id, case_id, recorded_at, platform, speaker, summary, raw_note_excerpt, ai_generated, "
        "approved_as_fact) VALUES (:i, :c, :t, 'ZOOM_AI_SYNTHETIC', :s, 'Call summary', 'x', true, false)",
        i=intake_id, c=case_id, t=when, s=speaker)  # fmt: skip


def message(case_id: str, message_id: str, when: str, channel: str, direction: str, body: str, role: str = "CLIENT") -> None:
    run("INSERT INTO messages (message_id, case_id, thread_id, created_at_source, channel, direction, sender_role, subject, body, "
        "attachment_refs, delivery_state) VALUES (:i, :c, 'THR-1', :t, :ch, :d, :r, 'Subject line', :b, '{}', 'RECORDED_MOCK')",
        i=message_id, c=case_id, t=when, ch=channel, d=direction, r=role, b=body)  # fmt: skip


def claim(case_id: str, source_id: str, field: str) -> None:
    run("INSERT INTO claims (case_id, source_id, field_name, value, quote) VALUES (:c, :s, :f, 'v', 'q')", c=case_id, s=source_id, f=field)


def upload(case_id: str, upload_id: str, category: str, name: str, when: str) -> None:
    run("INSERT INTO uploads (upload_id, case_id, storage_root, storage_path, original_filename, mime_type, file_size_bytes, sha256, "
        "uploaded_at, uploader_role, ingestion_source, client_supplied_type, version_label, outcome, category) VALUES "
        "(:u, :c, 'APP_STORAGE', 'x', :f, 'text/plain', 1, :h, :t, 'OPS', 'TEST', 'U', 'v', 'USABLE', :k)",
        u=upload_id, c=case_id, f=name, h=upload_id.ljust(64, "0")[:64], t=when, k=category)  # fmt: skip


def get(case_id: str, actor: str = OPS):
    return client.get(f"/api/cases/{case_id}/communications", headers={"X-Actor": actor})


def test_list_merges_notes_messages_and_uploads_in_order():
    case_id = new_case()
    n = case_id[5:]
    message(case_id, f"MSG-{n}-2", "2026-10-03 10:00", "WHATSAPP", "INBOUND", "When is my appointment?")
    message(case_id, f"MSG-{n}-1", "2026-10-02 10:00", "EMAIL", "OUTBOUND_DRAFT_ONLY", "Please send the list", "OPERATIONS")
    message(case_id, f"MSG-{n}-3", "2026-10-04 10:00", "EMAIL", "INBOUND", "Tell me the status")
    note(case_id, f"Z-{n}", "2026-10-01 10:00")
    upload(case_id, f"UP-C{n}A", "WHATSAPP_CHAT", "chat.txt", "2026-10-05 09:00")
    upload(case_id, f"UP-C{n}B", "PASSPORT", "p.pdf", "2026-10-05 09:00")
    claim(case_id, f"MSG-{n}-3", "client_question")
    claim(case_id, f"MSG-{n}-3", "full_name")
    items = get(case_id).json()
    assert [i["source_id"] for i in items] == [f"Z-{n}", f"MSG-{n}-1", f"MSG-{n}-2", f"MSG-{n}-3", f"UP-C{n}A"]
    assert [(i["kind"], i["direction"], i["is_draft"], i["client_question"], i["claim"], i["claims"]) for i in items] == [
        ("ZOOM", "NOTE", False, False, True, 0), ("EMAIL", "OUTBOUND_DRAFT_ONLY", True, False, True, 0),
        ("WHATSAPP", "INBOUND", False, True, True, 0), ("EMAIL", "INBOUND", False, True, True, 2),
        ("WHATSAPP", "INBOUND", False, False, True, 0)]  # fmt: skip
    assert items[0]["sender_role"] == "INTAKE_COORDINATOR" and items[0]["subject"] is None and items[0]["body"] == "Call summary"
    assert items[1]["sender_role"] == "OPERATIONS" and items[2]["sender_role"] == "CLIENT"
    assert items[4]["subject"] == "chat.txt" and items[4]["body"] == "" and items[4]["occurred_at"].startswith("2026-10-05")


def test_communications_need_an_assigned_actor():
    case_id = new_case()
    note(case_id, f"Z-{case_id[5:]}", "2026-10-01 10:00")
    assert get(case_id).status_code == 200 and len(get(case_id).json()) == 1
    for actor in ("OPS-92", "LEGAL-77"):
        assert get(case_id, actor).status_code == 403
    with SessionLocal() as db:
        denied = db.execute(text("SELECT count(*) FROM audit_log WHERE case_id = :c AND outcome = 'DENIED'"), {"c": case_id}).scalar_one()
    assert denied >= 2


def test_roles_intake_call_update_and_office_draft():
    case_id = new_case()
    n = case_id[5:]
    note(case_id, f"Z-{n}-2", "2026-10-06 10:00")
    note(case_id, f"Z-{n}", "2026-10-04 10:00")
    message(case_id, f"MSG-{n}-1", "2026-10-07 10:00", "EMAIL", "OUTBOUND_DRAFT_ONLY", "Please send the list", "OPERATIONS")
    message(case_id, f"MSG-{n}-2", "2026-10-08 10:00", "WHATSAPP", "INBOUND", "I uploaded it")
    upload(case_id, f"UP-R{n}", "ZOOM_NOTES", "early.txt", "2026-10-03 09:00")
    roles = {i["source_id"]: i["role"] for i in get(case_id).json()}
    assert roles == {f"UP-R{n}": "INTAKE_CALL", f"Z-{n}": "UPDATE", f"Z-{n}-2": "UPDATE",
                     f"MSG-{n}-1": "OFFICE_DRAFT", f"MSG-{n}-2": "UPDATE"}  # fmt: skip


def test_a_case_without_a_zoom_note_has_no_intake_call():
    case_id = new_case()
    message(case_id, f"MSG-{case_id[5:]}-1", "2026-10-08 10:00", "WHATSAPP", "INBOUND", "Hello")
    assert [i["role"] for i in get(case_id).json()] == ["UPDATE"]
