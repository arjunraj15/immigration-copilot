import csv
import json
import shutil
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal

from app.cases import service
from app.cases.loader import INTAKE_FILES, KitMissingError, _derived_case_rows, load_starter_kit
from app.cases.repository import CaseRecord
from app.core import audit
from app.core.config import get_settings
from app.core.contracts import ActorRole, AuditAction, AuditOutcome
from app.main import app
from tests.conftest import make_case

client = TestClient(app)
KIT = Path(get_settings().starter_kit_dir)


def get(path: str, actor: str = "OPS-01"):
    return client.get(path, headers={"X-Actor": actor})


def count(db: Session, table: str) -> int:
    return db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def csv_rows(name: str) -> int:
    with (KIT / name).open(newline="", encoding="utf-8") as handle:
        return len(list(csv.DictReader(handle)))


def jsonl_rows(name: str) -> int:
    return len([line for line in (KIT / name).read_text(encoding="utf-8").splitlines() if line.strip()])


def record(**overrides) -> CaseRecord:
    base = dict(
        case_id="CASE-0001", client_ref="CLIENT-0001", case_archetype="SYNTH_WORK_STATUS_RENEWAL",
        operational_stage="INTAKE_REVIEW", assigned_ops_user="OPS-02", assigned_legal_reviewer="LEGAL-02",
        display_name="Mira Dhawan", status="NEW", wizard_step=0, decided_recently=False, upload_count=7,
        last_upload_at=datetime(2026, 10, 3, 8, 30, tzinfo=timezone.utc),
    )  # fmt: skip
    return CaseRecord(**(base | overrides))


@pytest.fixture
def kit_copy(tmp_path: Path) -> Path:
    """A writable copy of the kit data files, without the PDFs, for tests that change the source files."""
    target = tmp_path / "kit"
    target.mkdir()
    for path in KIT.iterdir():
        if path.is_file() and path.suffix in {".csv", ".json", ".jsonl"}:
            shutil.copy(path, target / path.name)
    return target


# ---------------------------------------------------------------- loader


def test_loader_loads_every_source_row(db: Session) -> None:
    assert count(db, "cases") >= csv_rows("01_cases.csv")
    assert db.execute(text("SELECT count(*) FROM uploads WHERE storage_root = 'STARTER_KIT'")).scalar_one() == csv_rows(
        "05_document_manifest.csv"
    )
    assert count(db, "intake_notes") == jsonl_rows("02_zoom_intake_notes.jsonl")
    assert count(db, "messages") == jsonl_rows("03_client_messages.jsonl")
    assert db.execute(
        text("SELECT count(*) FROM profile_fields WHERE source_id LIKE 'PROFILE-CASE-0%'")
    ).scalar_one() == csv_rows("07_case_profiles.csv")
    assert count(db, "case_events") == csv_rows("09_case_events.csv")
    assert count(db, "rule_sets") == 4


def test_loading_twice_changes_nothing(db: Session) -> None:
    before = {table: count(db, table) for table in ("cases", "uploads", "case_events", "messages", "rule_sets")}
    report = load_starter_kit(db, KIT)
    assert not report.changed
    assert {table: count(db, table) for table in before} == before


def test_a_changed_source_row_is_updated_and_a_new_id_with_same_content_is_stored_once(
    db: Session, kit_copy: Path
) -> None:
    profile_file = kit_copy / "07_case_profiles.csv"
    edited = profile_file.read_text(encoding="utf-8").replace("Mira Dhawan", "Mira Dhawan Edited", 1)
    profile_file.write_text(edited, encoding="utf-8")
    with (kit_copy / "09_case_events.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    copy = {**rows[0], "event_id": f"EV-DUP-{uuid.uuid4().hex[:6]}"}
    with (kit_copy / "09_case_events.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows([*rows, copy])
    try:
        report = load_starter_kit(db, kit_copy)
        assert report.tables["profile_fields"].updated == 1
        assert report.tables["case_events"].skipped == 1
        assert report.tables["case_events"].inserted == 0
    finally:
        load_starter_kit(db, KIT)
    name = db.execute(text("SELECT verified_value FROM profile_fields WHERE source_id = 'PROFILE-CASE-0001-full_name'"))
    assert name.scalar_one() == "Mira Dhawan"


def test_changed_rules_become_a_new_version(db: Session, kit_copy: Path) -> None:
    path = kit_copy / "10_deadline_rules.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    body["note_for_test"] = uuid.uuid4().hex
    path.write_text(json.dumps(body), encoding="utf-8")
    report = load_starter_kit(db, kit_copy)
    assert report.tables["rule_sets"].updated == 1
    versions = db.execute(text("SELECT count(*) FROM rule_sets WHERE key = 'deadline_rules'")).scalar_one()
    assert versions >= 2
    load_starter_kit(db, KIT)
    latest = db.execute(
        text(
            "SELECT body ? 'note_for_test' AS changed FROM rule_sets "
            "WHERE key = 'deadline_rules' ORDER BY version DESC LIMIT 1"
        )
    ).scalar_one()
    assert latest is False


def test_missing_kit_is_reported(db: Session, tmp_path: Path) -> None:
    with pytest.raises(KitMissingError):
        load_starter_kit(db, tmp_path)


# ---------------------------------------------------------------- human decisions


def test_seeded_human_decision_is_loaded_and_audited(db: Session) -> None:
    row = db.execute(
        text("SELECT corrected_value, decision FROM review_decisions WHERE decision_id = 'REV-SEED-001'")
    ).one()
    assert (row.corrected_value, row.decision) == ("Meera Batra", "REJECTED_EXTRACTION")
    _, entries = audit.list_entries(db, "CASE-0012", actions=[AuditAction.SEED_LOADED])
    assert any(entry.target_id == "REV-SEED-001" for entry in entries)
    assert get("/api/cases/CASE-0012", actor=_ops_for("CASE-0012", db)).json()["name"] == "Meera Batra"


def _ops_for(case_id: str, db: Session, legal: bool = False) -> str:
    column = "assigned_legal_reviewer" if legal else "assigned_ops_user"
    return db.execute(text(f"SELECT {column} FROM cases WHERE case_id = :c"), {"c": case_id}).scalar_one()


def test_decision_audit_line_is_written_once(db: Session) -> None:
    load_starter_kit(db, KIT)
    _, entries = audit.list_entries(db, "CASE-0012", actions=[AuditAction.SEED_LOADED], limit=50)
    assert len([entry for entry in entries if entry.target_id == "REV-SEED-001"]) == 1


@pytest.mark.parametrize(
    "sql",
    ["UPDATE review_decisions SET corrected_value = 'X'", "DELETE FROM review_decisions", "TRUNCATE review_decisions"],
)
def test_app_role_cannot_change_a_human_decision(db: Session, sql: str) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        db.execute(text(sql))
    db.rollback()


@pytest.mark.parametrize(
    "sql",
    ["UPDATE review_decisions SET corrected_value = 'X'", "DELETE FROM review_decisions", "TRUNCATE review_decisions"],
)
def test_trigger_blocks_even_the_owner_from_changing_a_decision(owner_engine: Engine, sql: str) -> None:
    with pytest.raises(DBAPIError, match="insert-only"):
        with owner_engine.begin() as connection:
            connection.execute(text(sql))


# ---------------------------------------------------------------- claims and evidence


def test_sources_label_claims_and_evidence(db: Session) -> None:
    case_id = "CASE-0009"
    body = get(f"/api/cases/{case_id}/sources", actor=_ops_for(case_id, db)).json()
    assert body["intake_notes"] and all(row["source_kind"] == "CLAIM" for row in body["intake_notes"])
    assert all(row["approved_as_fact"] is False for row in body["intake_notes"])
    assert body["messages"] and all(row["source_kind"] == "CLAIM" for row in body["messages"])
    assert body["profile_fields"] and all(row["source_kind"] == "EVIDENCE" for row in body["profile_fields"])
    for event in body["events"]:
        is_evidence = event["event_source"] == "MOCK_PORTAL" and event["source_verified"]
        assert event["source_kind"] == ("EVIDENCE" if is_evidence else "CLAIM")
    assert {event["source_kind"] for event in body["events"]} == {"EVIDENCE", "CLAIM"}


# ---------------------------------------------------------------- scoping and access


def test_sources_hold_only_the_open_cases_rows(db: Session) -> None:
    case_id = "CASE-0001"
    body = get(f"/api/cases/{case_id}/sources", actor=_ops_for(case_id, db)).json()
    owned = {
        table: {row[0] for row in db.execute(text(f"SELECT {column} FROM {table} WHERE case_id = :c"), {"c": case_id})}
        for table, column in (("messages", "message_id"), ("intake_notes", "intake_id"), ("case_events", "event_id"))
    }
    assert {row["message_id"] for row in body["messages"]} == owned["messages"]
    assert {row["intake_id"] for row in body["intake_notes"]} == owned["intake_notes"]
    assert {row["event_id"] for row in body["events"]} == owned["case_events"]


def test_unassigned_actor_is_refused_and_logged(db: Session) -> None:
    case_id = "CASE-0001"
    other = "OPS-03" if _ops_for(case_id, db) != "OPS-03" else "OPS-04"
    response = get(f"/api/cases/{case_id}", actor=other)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CASE_NOT_ASSIGNED"
    for path in ("sources", "timeline", "audit"):
        assert get(f"/api/cases/{case_id}/{path}", actor=other).status_code == 403
    _, entries = audit.list_entries(db, case_id, actions=[AuditAction.CASE_ACCESS], limit=50)
    assert any(e.outcome == AuditOutcome.DENIED and e.actor == other for e in entries)
    assert audit.verify_stream(db, case_id).valid


def test_a_different_legal_reviewer_is_refused(db: Session) -> None:
    case_id = "CASE-0001"
    assigned = _ops_for(case_id, db, legal=True)
    other = "LEGAL-01" if assigned != "LEGAL-01" else "LEGAL-02"
    assert get(f"/api/cases/{case_id}", actor=other).status_code == 403
    assert get(f"/api/cases/{case_id}", actor=assigned).status_code == 200


def test_unknown_case_is_404(db: Session) -> None:
    response = get("/api/cases/CASE-9999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_requests_need_an_actor() -> None:
    assert client.get("/api/cases").status_code == 401
    assert client.get("/api/cases/CASE-0001").status_code == 401


# ---------------------------------------------------------------- queue and search


def test_queue_holds_only_the_actors_cases(db: Session) -> None:
    body = get("/api/cases", actor="OPS-02").json()
    listed = {item["case_id"] for group in body["groups"] for item in group["items"]}
    expected = {row[0] for row in db.execute(text("SELECT case_id FROM cases WHERE assigned_ops_user = 'OPS-02'"))}
    assert listed == expected
    legal = get("/api/cases", actor="LEGAL-02").json()
    assert legal["groups"] == []  # nothing is with an attorney until a paralegal sends it


def test_queue_groups_follow_the_workflow_status(db: Session) -> None:
    case_id = f"CASE-T{uuid.uuid4().hex[:8].upper()}"
    make_case(db, case_id, ops="OPS-92", legal="LEGAL-92", status="WITH_ATTORNEY", name="Group Check")
    ops = get("/api/cases", actor="OPS-92").json()["groups"]
    assert [g["key"] for g in ops] == ["with_attorney"]
    assert ops[0]["items"][0]["note"] == "Waiting for LEGAL-92"
    legal = get("/api/cases", actor="LEGAL-92").json()["groups"]
    assert [g["key"] for g in legal] == ["waiting"]
    assert legal[0]["items"][0]["name"] == "Group Check"
    assert get("/api/cases?group=waiting", actor="LEGAL-92").json()["groups"][0]["key"] == "waiting"
    assert get("/api/cases?group=decided", actor="LEGAL-92").json()["groups"] == []


@pytest.mark.parametrize(
    "term",
    ["CASE-0001", "case-0001", "client-0001", "mira dhawan", "dhawan"],
)
def test_search_finds_a_case(term: str) -> None:
    listed = {i["case_id"] for g in get(f"/api/cases?q={term}").json()["groups"] for i in g["items"]}
    assert "CASE-0001" in listed


def test_search_by_receipt_number(db: Session) -> None:
    receipt = db.execute(
        text(
            "SELECT verified_value FROM profile_fields "
            "WHERE case_id = 'CASE-0001' AND field_name = 'prior_receipt_number'"
        )
    ).scalar_one()
    listed = {i["case_id"] for g in get(f"/api/cases?q={receipt}").json()["groups"] for i in g["items"]}
    assert listed == {"CASE-0001"}


@pytest.mark.parametrize("term", ["%25", "_", "CASE_0001"])
def test_search_treats_wildcards_as_text(term: str) -> None:
    assert get(f"/api/cases?q={term}").json()["groups"] == []


# ---------------------------------------------------------------- header and timeline


def test_case_header_has_portal_status() -> None:
    body = get("/api/cases/CASE-0001").json()
    assert body["name"] == "Mira Dhawan"
    assert body["number"] == "0001"
    assert body["archetype"] == "Work status renewal"
    assert body["workflow_status"] == "NEW"
    assert body["portal_status"]["label"] == "Processing"
    assert body["portal_status"]["event_id"].startswith("EV-0001")


def test_timeline_uses_the_review_date_and_lanes(db: Session) -> None:
    body = get("/api/cases/CASE-0009/timeline", actor=_ops_for("CASE-0009", db)).json()
    assert body["as_of"] == "2026-10-23"
    items = body["items"]
    assert [i["date"] for i in items] == sorted(i["date"] for i in items)
    today = [i for i in items if i["lane"] == "today"]
    assert len(today) == 1 and today[0]["date"] == "2026-10-23"
    request = next(i for i in items if i["ref"] == "EV-0009-RFE")
    assert (request["lane"], request["kind"]) == ("portal", "verified")
    calendar = [i for i in items if i["lane"] == "calendar"]
    assert calendar and all(i["kind"] in ("unverified", "wrong") for i in calendar)


def test_actors_come_from_the_data(db: Session) -> None:
    listed = client.get("/api/actors").json()
    expected = {row[0] for row in db.execute(text("SELECT assigned_ops_user FROM cases"))}
    expected |= {row[0] for row in db.execute(text("SELECT assigned_legal_reviewer FROM cases"))}
    assert expected <= {actor["label"] for actor in listed}
    assert {actor["role"] for actor in listed} == {"OPS", "LEGAL"}
    me = client.get("/api/me", headers={"X-Actor": "OPS-02"}).json()
    assert me["case_count"] == next(a for a in listed if a["label"] == "OPS-02")["case_count"]


# ---------------------------------------------------------------- pure functions


def test_humanize_and_helpers() -> None:
    assert service.humanize("SYNTH_WORK_STATUS_RENEWAL") == "Work status renewal"
    assert service.humanize("MOCK_EVIDENCE_REQUEST_RECEIVED") == "Evidence request received"
    assert service.case_number("CASE-0012") == "0012"
    assert service.initials("Mira Dhawan") == "MD"
    assert service.initials("Cher") == "C"
    assert service.short_date(date(2026, 10, 5)) == "5 Oct"


def test_portal_status_label() -> None:
    text_in = "Mock portal status: Processing; no adjudication estimate supplied."
    assert service.portal_status_label(text_in) == "Processing"
    assert service.portal_status_label("Fictional receipt recorded.") is None


def test_queue_notes_and_groups() -> None:
    assert service.queue_note(ActorRole.OPS, record()) == ("Uploaded 7 files, 3 Oct", "muted")
    assert service.queue_note(ActorRole.OPS, record(status="IN_PROGRESS", wizard_step=1))[0] == "Step 2 of 6"
    assert service.queue_note(ActorRole.LEGAL, record(status="WITH_ATTORNEY"))[0] == "Prepared by OPS-02"
    assert service.group_key(ActorRole.OPS, record(status="REJECTED")) == "sent_back"
    assert service.group_key(ActorRole.LEGAL, record(status="NEW")) is None
    assert service.group_key(ActorRole.LEGAL, record(status="APPROVED", decided_recently=True)) == "decided"
    assert service.group_key(ActorRole.LEGAL, record(status="APPROVED", decided_recently=False)) is None


def test_empty_groups_are_hidden() -> None:
    groups = service.build_queue(ActorRole.OPS, [record(), record(case_id="CASE-0002")])
    assert [g.key for g in groups] == ["new"]
    assert len(groups[0].items) == 2


def test_timeline_puts_today_after_past_events() -> None:
    events = [
        {"event_date": date(2026, 10, 24), "event_type": "A", "event_source": "MOCK_PORTAL", "source_verified": True,
         "details": "", "event_id": "E2"},
        {"event_date": date(2026, 10, 14), "event_type": "B", "event_source": "GOOGLE_CALENDAR_MOCK",
         "source_verified": False, "details": "", "event_id": "E1"},
    ]  # fmt: skip
    items = service.build_timeline(events, date(2026, 10, 23))
    assert [i.lane for i in items] == ["calendar", "today", "portal"]
    assert items[0].kind == "unverified"
    assert service.build_timeline([], date(2026, 10, 23))[0].lane == "today"


def test_every_user_a_case_names_is_a_known_actor_after_the_seed():
    from app.cases.loader import _ensure_actors

    with SessionLocal() as db:
        _ensure_actors(db)
        db.commit()
        missing = db.execute(text(
            "SELECT DISTINCT u FROM (SELECT assigned_ops_user u FROM cases UNION SELECT assigned_legal_reviewer FROM cases) x "
            "WHERE u IS NOT NULL AND u NOT IN (SELECT label FROM actors)")).all()
    assert missing == []


def test_intake_only_cases_are_derived_from_the_ids_and_need_no_case_or_manifest_file(tmp_path: Path) -> None:
    for name in (*INTAKE_FILES, "04_case_document_rules.json"):
        shutil.copy(KIT / name, tmp_path / name)
    rows = _derived_case_rows(tmp_path)
    ids = {r["case_id"] for r in rows}
    assert ids == {row["case_id"] for row in csv.DictReader((KIT / "07_case_profiles.csv").open(encoding="utf-8"))}
    assert not (tmp_path / "01_cases.csv").exists() and not (tmp_path / "05_document_manifest.csv").exists()
    first = rows[0]
    assert first["operational_stage"] == "DOCUMENT_COLLECTION" and _derived_case_rows(tmp_path, {first["case_id"]: "EVIDENCE_REVIEW"})[0]["operational_stage"] == "EVIDENCE_REVIEW"
    assert first["case_archetype"] == json.loads((KIT / "04_case_document_rules.json").read_text())["archetype"]
    assert first["opened_at"] <= date(2026, 10, 24)
