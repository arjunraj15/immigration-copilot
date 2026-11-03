import json
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.contracts import ActorRole, AuditAction, AuditOutcome
from app.core.security import Actor
from app.db.session import SessionLocal
from app.main import app
from tests.conftest import make_case

client = TestClient(app)

OPS = Actor(label="OPS-01", role=ActorRole.OPS)
LEGAL = Actor(label="LEGAL-01", role=ActorRole.LEGAL)
APP_DIR = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture
def stream(db: Session) -> str:
    """A throwaway case owned by OPS-01 and LEGAL-01, so the audit routes' case access check passes."""
    case_id = f"CASE-T{uuid.uuid4().hex[:8].upper()}"
    make_case(db, case_id, ops="OPS-01", legal="LEGAL-01")
    return case_id


def add(db: Session, stream_id: str, count: int = 1, action: AuditAction = AuditAction.PROPOSE) -> None:
    for number in range(count):
        audit.record(
            db, actor=OPS, action=action, case_id=stream_id, target_type="proposal", target_id=f"ACT-{number}",
            after_state={"status": "PENDING_LEGAL_REVIEW"}, evidence_ids=["EV-1"], details={"n": number},
        )  # fmt: skip
    db.commit()


@contextmanager
def tampering(owner_engine: Engine, stream_id: str) -> Iterator[Engine]:
    """Let a test edit the ledger as the database owner, then remove the stream so other tests stay clean."""
    try:
        yield owner_engine
    finally:
        with owner_engine.begin() as connection:
            connection.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_change"))
            connection.execute(text("DELETE FROM audit_log WHERE stream_id = :s"), {"s": stream_id})
            connection.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_change"))
            connection.execute(text("DELETE FROM audit_heads WHERE stream_id = :s"), {"s": stream_id})
        path = Path(get_settings().audit_checkpoint_file)
        if path.exists():
            data = json.loads(path.read_text())
            data.pop(stream_id, None)
            path.write_text(json.dumps(data))


def edit_as_owner(engine: Engine, sql: str, **params: object) -> None:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_change"))
        connection.execute(text(sql), params)
        connection.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_change"))


# ---------------------------------------------------------------- writing and verifying


def test_record_then_verify_is_valid(db: Session, stream: str) -> None:
    add(db, stream, count=3)
    total, entries = audit.list_entries(db, stream, limit=10)
    assert total == 3
    assert [entry.seq for entry in reversed(entries)] == [1, 2, 3]
    assert entries[-1].prev_hash == audit.GENESIS_HASH
    assert entries[0].prev_hash == entries[1].row_hash
    result = audit.verify_stream(db, stream)
    assert result.valid
    assert result.entries_checked == 3


def test_case_and_system_chains_are_separate(db: Session, stream: str) -> None:
    add(db, stream)
    audit.record(db, actor=audit.SYSTEM_ACTOR, action=AuditAction.PROMPT_VERSION_ACTIVATED, outcome=AuditOutcome.SYSTEM)
    db.commit()
    assert audit.list_entries(db, stream)[0] == 1
    system_total, system_entries = audit.list_entries(db, audit.SYSTEM_STREAM, limit=1)
    assert system_total >= 1
    assert system_entries[0].case_id is None
    assert audit.verify_stream(db, audit.SYSTEM_STREAM).valid


def test_floats_are_refused(db: Session, stream: str) -> None:
    with pytest.raises(ValueError):
        audit.record(db, actor=OPS, action=AuditAction.PROPOSE, case_id=stream, details={"confidence": 0.97})
    db.rollback()


def test_rollback_removes_the_line_and_denied_attempt_is_kept(db: Session, stream: str) -> None:
    add(db, stream)
    audit.record(db, actor=OPS, action=AuditAction.COMMIT, case_id=stream, target_type="proposal", target_id="ACT-9")
    db.rollback()
    assert audit.list_entries(db, stream)[0] == 1

    audit.record_denied(
        reason="Legal reviewer approval required first", actor=OPS, action=AuditAction.COMMIT, case_id=stream,
        target_type="proposal", target_id="ACT-9",
    )  # fmt: skip
    total, entries = audit.list_entries(db, stream)
    assert total == 2
    assert entries[0].outcome == AuditOutcome.DENIED
    assert entries[0].details["reason"] == "Legal reviewer approval required first"
    assert audit.verify_stream(db, stream).valid


def test_concurrent_writers_leave_no_gaps(stream: str) -> None:
    barrier = threading.Barrier(2)
    failures: list[BaseException] = []

    def work() -> None:
        try:
            barrier.wait()
            for _ in range(10):
                with SessionLocal() as session:
                    add(session, stream)
        except BaseException as error:  # noqa: BLE001
            failures.append(error)

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not failures
    with SessionLocal() as session:
        total, entries = audit.list_entries(session, stream, limit=50)
        assert total == 20
        assert sorted(entry.seq for entry in entries) == list(range(1, 21))
        assert audit.verify_stream(session, stream).valid


# ---------------------------------------------------------------- tamper detection


def test_editing_one_row_is_reported_at_that_seq(db: Session, owner_engine: Engine, stream: str) -> None:
    add(db, stream, count=4)
    original = audit.list_entries(db, stream, limit=10)[1][1]  # seq 3, newest first
    with tampering(owner_engine, stream):
        edit_as_owner(owner_engine, "UPDATE audit_log SET actor = 'L9' WHERE stream_id = :s AND seq = 3", s=stream)
        result = audit.verify_stream(db, stream)
    assert not result.valid
    assert result.first_break is not None
    assert result.first_break.seq == original.seq == 3
    assert result.first_break.found_hash == original.row_hash
    assert result.first_break.expected_hash != original.row_hash


def test_deleting_a_middle_row_is_reported(db: Session, owner_engine: Engine, stream: str) -> None:
    add(db, stream, count=4)
    with tampering(owner_engine, stream):
        edit_as_owner(owner_engine, "DELETE FROM audit_log WHERE stream_id = :s AND seq = 2", s=stream)
        result = audit.verify_stream(db, stream)
    assert not result.valid
    assert result.first_break is not None
    assert result.first_break.seq == 2


def test_deleting_the_last_row_is_reported(db: Session, owner_engine: Engine, stream: str) -> None:
    add(db, stream, count=3)
    with tampering(owner_engine, stream):
        edit_as_owner(owner_engine, "DELETE FROM audit_log WHERE stream_id = :s AND seq = 3", s=stream)
        result = audit.verify_stream(db, stream)
    assert not result.valid
    assert result.first_break is not None
    assert "Head" in result.first_break.reason


def test_rewriting_the_whole_chain_is_caught_by_the_checkpoint(db: Session, owner_engine: Engine, stream: str) -> None:
    add(db, stream, count=3)
    with tampering(owner_engine, stream):
        with owner_engine.begin() as connection:
            connection.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_change"))
            rows = connection.execute(
                text("SELECT * FROM audit_log WHERE stream_id = :s ORDER BY seq"), {"s": stream}
            ).all()
            previous = audit.GENESIS_HASH
            for row in rows:
                fields = {name: row._mapping[name] for name in audit.HASHED_FIELDS}
                fields["actor"] = "LEGAL-09" if row.seq == 1 else fields["actor"]
                new_hash = audit.compute_row_hash(fields, previous)
                connection.execute(
                    text(
                        "UPDATE audit_log SET actor = :actor, prev_hash = :prev, row_hash = :hash "
                        "WHERE stream_id = :s AND seq = :seq"
                    ),
                    {"actor": fields["actor"], "prev": previous, "hash": new_hash, "s": stream, "seq": row.seq},
                )
                previous = new_hash
            connection.execute(
                text("UPDATE audit_heads SET last_hash = :h WHERE stream_id = :s"), {"h": previous, "s": stream}
            )
            connection.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_change"))
        result = audit.verify_stream(db, stream)
    assert not result.valid
    assert result.first_break is not None
    assert "Checkpoint" in result.first_break.reason


# ---------------------------------------------------------------- immutability


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE audit_log SET actor = 'X' WHERE stream_id = 'none'",
        "DELETE FROM audit_log WHERE stream_id = 'none'",
        "TRUNCATE audit_log",
    ],
)
def test_app_role_cannot_change_the_ledger(db: Session, sql: str) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        db.execute(text(sql))
    db.rollback()


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE audit_log SET actor = 'X' WHERE stream_id = :s",
        "DELETE FROM audit_log WHERE stream_id = :s",
        "TRUNCATE audit_log",
    ],
)
def test_trigger_blocks_even_the_owner(db: Session, owner_engine: Engine, stream: str, sql: str) -> None:
    add(db, stream)  # row triggers only fire when a row matches
    with pytest.raises(DBAPIError, match="insert-only"):
        with owner_engine.begin() as connection:
            connection.execute(text(sql), {"s": stream} if ":s" in sql else {})
    assert audit.verify_stream(db, stream).valid


def test_only_audit_module_inserts_into_the_ledger() -> None:
    offenders = [
        str(path.relative_to(APP_DIR))
        for path in APP_DIR.rglob("*.py")
        if path.name != "audit.py" and "audit_log" in path.read_text() and "INSERT" in path.read_text().upper()
    ]
    assert offenders == []


# ---------------------------------------------------------------- routes


def get(path: str, actor: str = "OPS-01"):
    return client.get(path, headers={"X-Actor": actor})


def test_case_audit_is_newest_first_with_display_text(db: Session, stream: str) -> None:
    add(db, stream, count=2)
    audit.record_denied(
        reason="Only a LEGAL reviewer may do this", actor=OPS, action=AuditAction.REVIEW_APPROVE, case_id=stream,
        target_type="proposal", target_id="ACT-1",
    )  # fmt: skip
    body = get(f"/api/cases/{stream}/audit").json()
    assert body["total"] == 3
    assert [line["entry"]["seq"] for line in body["entries"]] == [3, 2, 1]
    refused = body["entries"][0]["display"]
    assert refused["label"] == "Refused"
    assert refused["tone"] == "bad"
    assert "Only a LEGAL reviewer may do this" in refused["note"]
    assert body["entries"][1]["display"]["label"] == "Proposed"


def test_audit_filter_by_action(db: Session, stream: str) -> None:
    add(db, stream, count=2, action=AuditAction.PROPOSE)
    add(db, stream, count=1, action=AuditAction.COMMIT)
    body = get(f"/api/cases/{stream}/audit?action=COMMIT").json()
    assert body["total"] == 1
    assert get(f"/api/cases/{stream}/audit?action=NOPE").status_code == 422


def test_audit_needs_an_actor(stream: str) -> None:
    assert client.get(f"/api/cases/{stream}/audit").status_code == 401


def test_verify_route_reports_valid_and_logs_the_check(db: Session, stream: str) -> None:
    add(db, stream, count=2)
    body = get(f"/api/cases/{stream}/audit/verify").json()
    assert body == {"stream_id": stream, "valid": True, "entries_checked": 2, "first_break": None}
    entries = audit.list_entries(db, stream)[1]
    assert entries[0].action == AuditAction.CHAIN_VERIFIED
    assert entries[0].details["valid"] is True
    assert audit.verify_stream(db, stream).valid


def test_verify_route_reports_the_first_break(db: Session, owner_engine: Engine, stream: str) -> None:
    add(db, stream, count=3)
    with tampering(owner_engine, stream):
        edit_as_owner(owner_engine, "UPDATE audit_log SET target_id = 'X' WHERE stream_id = :s AND seq = 2", s=stream)
        body = get(f"/api/cases/{stream}/audit/verify").json()
    assert body["valid"] is False
    assert body["first_break"]["seq"] == 2


def test_system_chain_and_verify_all_are_legal_only(db: Session) -> None:
    for path in ("/api/audit", "/api/audit/verify"):
        denied = get(path, actor="OPS-01")
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "PERMISSION_DENIED"
        assert get(path, actor="LEGAL-01").status_code == 200
    _, entries = audit.list_entries(db, audit.SYSTEM_STREAM, actions=[AuditAction.CHAIN_VERIFIED], limit=50)
    assert any(entry.outcome == AuditOutcome.DENIED and entry.actor == "OPS-01" for entry in entries)


def test_verify_all_covers_every_chain(db: Session, stream: str) -> None:
    add(db, stream)
    body = get("/api/audit/verify", actor="LEGAL-02").json()
    assert body["valid"] is True
    assert stream in [chain["stream_id"] for chain in body["chains"]]
    assert audit.SYSTEM_STREAM in [chain["stream_id"] for chain in body["chains"]]


def test_every_audit_action_has_wording_so_no_activity_view_can_fail():
    from app.core.audit_display import _DISPLAY
    from app.core.contracts import AuditAction

    assert [a.value for a in AuditAction if a not in _DISPLAY] == []
