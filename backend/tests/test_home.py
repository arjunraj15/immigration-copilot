import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.cases import home
from app.db.session import SessionLocal
from app.main import app
from tests.conftest import make_case

client = TestClient(app)
PORTAL, CALENDAR = "MOCK_PORTAL", "GOOGLE_CALENDAR_MOCK"
REQUEST = "MOCK_EVIDENCE_REQUEST_RECEIVED"


def new_case(ops: str = "OPS-91", status: str = "NEW") -> str:
    case_id = f"CASE-T{uuid.uuid4().hex[:6].upper()}"
    with SessionLocal() as db:
        make_case(db, case_id, ops=ops, status=status)
    return case_id


def complete(case_id: str) -> str:
    """Give the case a usable file for every required document, so no missing document is the reason shown."""
    rows = [("PASSPORT", "{}"), ("ARRIVAL_RECORD", "{}"), ("EMPLOYER_LETTER", "{}"), ("PRIOR_NOTICE", "{}"),
            ("PAY_STATEMENT", '{"pay_period": "2026-08"}'), ("PAY_STATEMENT", '{"pay_period": "2026-09"}')]  # fmt: skip
    with SessionLocal() as db:
        for category, flags in rows:
            upload_id = f"UP-H{uuid.uuid4().hex[:8].upper()}"
            db.execute(
                text("INSERT INTO uploads (upload_id, case_id, storage_root, storage_path, original_filename, mime_type, file_size_bytes, "
                     "sha256, uploaded_at, uploader_role, ingestion_source, client_supplied_type, version_label, outcome, category, flags) "
                     "VALUES (:u, :c, 'APP_STORAGE', :u, 'a.pdf', 'application/pdf', 1, :h, now(), 'CLIENT', 'TEST', 'UNSPECIFIED', 'v1', "
                     "'USABLE', :k, CAST(:f AS jsonb))"),
                {"u": upload_id, "c": case_id, "h": uuid.uuid4().hex + uuid.uuid4().hex, "k": category, "f": flags},
            )  # fmt: skip
        db.commit()
    return case_id


def add_event(case_id: str, event_type: str, when: str, *, source: str = PORTAL, verified: bool = True) -> str:
    event_id = f"EV-T{uuid.uuid4().hex[:8].upper()}"
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO case_events (event_id, case_id, event_date, event_type, event_source, source_reference, "
                "details, source_verified, import_batch) VALUES (:e, :c, :d, :t, :s, 'test', :e, :v, 'test')"
            ),
            {"e": event_id, "c": case_id, "d": when, "t": event_type, "s": source, "v": verified},
        )
        db.commit()
    return event_id


def get_row(case_id: str, actor: str = "OPS-91") -> dict:
    rows = client.get("/api/home", params={"case_id": case_id}, headers={"X-Actor": actor}).json()["rows"]
    return rows[0] if rows else None


def all_rows(actor: str = "OPS-91") -> list[dict]:
    """Every row of the actor's queue, read page by page."""
    rows, page = [], 1
    while True:
        body = client.get("/api/home", params={"page": page}, headers={"X-Actor": actor}).json()
        rows += body["rows"]
        if len(rows) >= body["total"]:
            return rows
        page += 1


def test_only_cases_assigned_to_the_actor_are_listed():
    mine, theirs = new_case("OPS-91"), new_case("OPS-92")
    rows = all_rows()
    ids = {r["case_id"] for r in rows}
    assert mine in ids and theirs not in ids
    assert all(r["ops_user"] == "OPS-91" for r in rows)
    assert client.get("/api/home").status_code == 401


def test_due_date_comes_from_verified_event_and_rule_offset():
    case_id = new_case()
    event_id = add_event(case_id, REQUEST, "2026-10-20")
    with SessionLocal() as db:
        offset = home.load_rule(db).offset_days
    due = get_row(case_id)["due"]
    assert due["date"] == "2026-10-20"[:8] + f"{20 + offset:02d}"
    assert due["request_event_id"] == event_id and due["offset_days"] == offset
    assert due["state"] == "PROPOSED" and due["days_left"] == 7 and due["calendar_date"] is None
    assert any(d["case_id"] == case_id for d in client.get("/api/home", headers={"X-Actor": "OPS-91"}).json()["deadlines"])


def test_calendar_with_another_date_flags_a_conflict():
    case_id = new_case()
    add_event(case_id, REQUEST, "2026-10-20")
    calendar_id = add_event(case_id, "CALENDAR_DEADLINE", "2026-11-05", source=CALENDAR, verified=False)
    row = get_row(case_id)
    assert row["due"]["state"] == "CONFLICT" and row["due"]["calendar_event_id"] == calendar_id
    assert row["due"]["calendar_date"] == "2026-11-05"
    assert row["reason"]["key"] == "deadline_conflict" and row["attention"]


def test_calendar_with_the_same_date_is_no_conflict():
    case_id = new_case()
    add_event(case_id, REQUEST, "2026-10-20")
    add_event(case_id, "CALENDAR_DEADLINE", "2026-10-30", source=CALENDAR, verified=False)
    assert get_row(case_id)["due"]["state"] == "PROPOSED"


def test_unverified_or_calendar_only_event_gives_no_due_date():
    unverified, calendar_only = new_case(), new_case()
    add_event(unverified, REQUEST, "2026-10-20", verified=False)
    add_event(calendar_only, REQUEST, "2026-10-20", source=CALENDAR, verified=False)
    add_event(calendar_only, "CALENDAR_DEADLINE", "2026-10-30", source=CALENDAR, verified=False)
    assert get_row(unverified)["due"] is None
    assert get_row(calendar_only)["due"] is None
    assert get_row(calendar_only)["reason"]["key"] != "deadline_conflict"


def test_due_before_the_review_date_is_overdue():
    case_id = new_case()
    add_event(case_id, REQUEST, "2026-10-01")
    with SessionLocal() as db:
        as_of = home.repository.get_as_of(db)
    due = get_row(case_id)["due"]
    assert due["state"] == "OVERDUE" and due["days_left"] == (date.fromisoformat(due["date"]) - as_of).days < 0


def test_reason_follows_workflow_status():
    expected = {
        "WITH_ATTORNEY": "waiting_legal", "INFO_REQUESTED": "info_requested", "REJECTED": "rejected",
        "APPROVED": "approved", "NEW": "working",
    }  # fmt: skip
    for status, key in expected.items():
        assert get_row(complete(new_case(status=status)))["reason"]["key"] == key
    assert get_row(new_case(status="NEW"))["reason"]["key"] == "missing_document"  # no file at all, every required document is owed


def test_pending_and_rejected_proposals_set_the_reason():
    pending, rejected = complete(new_case()), complete(new_case())
    for case_id in (pending, rejected):
        created = client.post(
            f"/api/cases/{case_id}/proposals", headers={"X-Actor": "OPS-91"},
            json={"kind": "STAGE_CHANGE", "idempotency_key": uuid.uuid4().hex, "value": {"to_stage": "ON_HOLD", "reason": "x"}},
        )  # fmt: skip
        assert created.status_code == 201
    assert get_row(pending)["reason"]["key"] == "waiting_legal"
    proposal_id = client.get(f"/api/cases/{rejected}/proposals", headers={"X-Actor": "OPS-91"}).json()[0]["proposal_id"]
    client.post(
        f"/api/proposals/{proposal_id}/review", headers={"X-Actor": "LEGAL-91"},
        json={"decision": "REJECT", "reason": "Wrong spelling"},
    )  # fmt: skip
    row = get_row(rejected)
    assert row["reason"]["key"] == "rejected" and "Wrong spelling" in row["reason"]["text"]
    assert proposal_id in row["refs"]


def test_activity_lists_only_the_actors_cases_newest_first():
    mine = new_case("OPS-91")
    client.post(
        f"/api/cases/{mine}/proposals", headers={"X-Actor": "OPS-91"},
        json={"kind": "STAGE_CHANGE", "idempotency_key": uuid.uuid4().hex, "value": {"to_stage": "ON_HOLD", "reason": "x"}},
    )  # fmt: skip
    body = client.get("/api/home", headers={"X-Actor": "OPS-91"}).json()
    activity = body["activity"]
    assert 0 < len(activity) <= 20
    assert activity[0]["case_id"] == mine and activity[0]["action"] == "PROPOSE"
    mine_ids = {r["case_id"] for r in all_rows()}
    assert all(a["case_id"] in mine_ids for a in activity)
    assert [a["occurred_at"] for a in activity] == sorted((a["occurred_at"] for a in activity), reverse=True)


def test_queue_pages_hold_at_most_ten_rows_and_filters_run_on_the_server():
    for _ in range(11):
        new_case("OPS-93")
    first = client.get("/api/home", headers={"X-Actor": "OPS-93"}).json()
    assert len(first["rows"]) == 10 and first["page"] == 1 and first["total"] >= 11
    second = client.get("/api/home?page=2", headers={"X-Actor": "OPS-93"}).json()
    assert second["rows"] and not {r["case_id"] for r in first["rows"]} & {r["case_id"] for r in second["rows"]}
    assert second["total"] == first["total"]
    past = client.get("/api/home?page=999", headers={"X-Actor": "OPS-93"}).json()
    assert past["page"] == -(-past["total"] // 10)
    one = first["rows"][0]
    found = client.get(f"/api/home?term={one['case_id'].lower()}", headers={"X-Actor": "OPS-93"}).json()
    assert found["total"] == 1 and found["rows"][0]["case_id"] == one["case_id"] and found["assigned"] == first["assigned"]
    assert client.get("/api/home?page_size=11", headers={"X-Actor": "OPS-93"}).status_code == 422


def test_cached_queue_is_cleared_by_a_write_request(monkeypatch):
    monkeypatch.setenv("HOME_CACHE_SECONDS", "30")
    from app.core.config import get_settings

    get_settings.cache_clear()
    home.clear_cache()
    try:
        case_id = new_case("OPS-94")
        head = {"X-Actor": "OPS-94"}
        assert client.get("/api/home", headers=head).json()["assigned"] == 1
        other = new_case("OPS-94")  # direct database write, so the cached queue does not see it yet
        assert client.get("/api/home", headers=head).json()["assigned"] == 1
        client.post(f"/api/cases/{case_id}/calendar-events", headers=head,
                    json={"event_date": "2026-11-01", "event_type": "CALENDAR_NOTE", "details": "x"})  # fmt: skip
        assert {r["case_id"] for r in client.get("/api/home", headers=head).json()["rows"]} == {case_id, other}
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        home.clear_cache()


def test_each_reason_option_carries_the_colour_of_its_tone():
    ops = "OPS-94"
    new_case(ops)
    body = client.get("/api/home?just_me=false", headers={"X-Actor": ops}).json()
    assert body["reasons"] and all(option["tone"] in ("bad", "warn", "ok", "ai", "muted") for option in body["reasons"])
