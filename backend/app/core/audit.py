"""The audit ledger. This module is the only writer of audit_log (rules.md section 12).

Each stream (one per case, plus SYSTEM) is a hash chain. An entry's row_hash covers its own fields and
the previous entry's hash, so any edit, deletion or reordering shows up when the chain is verified.
"""

import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.contracts import ActorRole, AuditAction, AuditOutcome
from app.core.errors import AppError
from app.core.security import Actor
from app.db.session import SessionLocal

SYSTEM_STREAM = "SYSTEM"
GENESIS_HASH = "0" * 64
SYSTEM_ACTOR = Actor(label="SYSTEM", role=ActorRole.SYSTEM)

HASHED_FIELDS = (
    "stream_id", "seq", "occurred_at", "actor", "actor_role", "action", "outcome", "case_id", "target_type",
    "target_id", "before_state", "after_state", "evidence_ids", "idempotency_key", "request_id",
    "prompt_run_id", "details",
)  # fmt: skip

_PENDING_KEY = "audit_pending_heads"
_checkpoint_lock = threading.Lock()


class AuditEntry(BaseModel):
    id: int
    stream_id: str
    seq: int
    occurred_at: datetime
    actor: str
    actor_role: ActorRole
    action: AuditAction
    outcome: AuditOutcome
    case_id: str | None
    target_type: str | None
    target_id: str | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    evidence_ids: list[str]
    idempotency_key: str | None
    request_id: str | None
    prompt_run_id: int | None
    details: dict[str, Any]
    prev_hash: str
    row_hash: str


class ChainBreak(BaseModel):
    seq: int | None
    reason: str
    expected_hash: str | None = None
    found_hash: str | None = None


class VerifyResult(BaseModel):
    stream_id: str
    valid: bool
    entries_checked: int
    first_break: ChainBreak | None = None


# ---------------------------------------------------------------- hashing


def _check_no_floats(value: Any) -> None:
    """Entries hold ids, hashes and states. Floats do not survive a jsonb round trip unchanged."""
    if isinstance(value, float):
        raise ValueError("Audit entries must not contain floats. Store the value as a string.")
    if isinstance(value, dict):
        for item in value.values():
            _check_no_floats(item)
    if isinstance(value, list):
        for item in value:
            _check_no_floats(item)


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _iso_utc(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def compute_row_hash(fields: dict[str, Any], prev_hash: str) -> str:
    """SHA-256 of the canonical JSON of the hashed fields plus prev_hash."""
    payload = {name: fields[name] for name in HASHED_FIELDS}
    payload["occurred_at"] = _iso_utc(payload["occurred_at"])
    payload["evidence_ids"] = list(payload["evidence_ids"])
    payload["prev_hash"] = prev_hash
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- checkpoint file


def _checkpoint_path() -> Path:
    return Path(get_settings().audit_checkpoint_file)


def read_checkpoint() -> dict[str, dict[str, Any]]:
    path = _checkpoint_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_checkpoint(heads: dict[str, tuple[int, str]]) -> None:
    """Keep the highest seq per stream. The file lives outside the database so a rewritten chain is caught."""
    with _checkpoint_lock:
        current = read_checkpoint()
        for stream_id, (seq, row_hash) in heads.items():
            if seq > current.get(stream_id, {}).get("last_seq", 0):
                current[stream_id] = {"last_seq": seq, "last_hash": row_hash}
        path = _checkpoint_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".audit_checkpoint_")
        with os.fdopen(handle, "w", encoding="utf-8") as temp:
            json.dump(current, temp, sort_keys=True, indent=2)
        os.replace(temp_name, path)


@event.listens_for(Session, "after_commit")
def _flush_checkpoints(session: Session) -> None:
    heads = session.info.pop(_PENDING_KEY, None)
    if heads:
        _write_checkpoint(heads)


@event.listens_for(Session, "after_rollback")
def _drop_checkpoints(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)


# ---------------------------------------------------------------- writing


def _lock_head(db: Session, stream_id: str) -> tuple[int, str]:
    db.execute(
        text("INSERT INTO audit_heads (stream_id) VALUES (:stream_id) ON CONFLICT (stream_id) DO NOTHING"),
        {"stream_id": stream_id},
    )
    row = db.execute(
        text("SELECT last_seq, last_hash FROM audit_heads WHERE stream_id = :stream_id FOR UPDATE"),
        {"stream_id": stream_id},
    ).one()
    return row.last_seq, row.last_hash


def record(
    db: Session,
    *,
    actor: Actor,
    action: AuditAction,
    outcome: AuditOutcome = AuditOutcome.ALLOWED,
    case_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    evidence_ids: Sequence[str] = (),
    idempotency_key: str | None = None,
    request_id: str | None = None,
    prompt_run_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEntry:
    """Append one entry to the case chain, or to SYSTEM when there is no case.

    Runs inside the caller's transaction, so a rollback removes the line with the change it describes.
    The caller commits. Never store document text or message bodies in any field.
    """
    for state in (before_state, after_state, details):
        _check_no_floats(state)
    stream_id = case_id or SYSTEM_STREAM
    last_seq, last_hash = _lock_head(db, stream_id)
    seq = last_seq + 1
    fields: dict[str, Any] = {
        "stream_id": stream_id,
        "seq": seq,
        "occurred_at": db.execute(text("SELECT clock_timestamp()")).scalar_one(),
        "actor": actor.label,
        "actor_role": actor.role.value,
        "action": action.value,
        "outcome": outcome.value,
        "case_id": case_id,
        "target_type": target_type,
        "target_id": target_id,
        "before_state": before_state,
        "after_state": after_state,
        "evidence_ids": list(evidence_ids),
        "idempotency_key": idempotency_key,
        "request_id": request_id,
        "prompt_run_id": prompt_run_id,
        "details": details or {},
    }
    row_hash = compute_row_hash(fields, last_hash)
    stored = {
        **fields,
        "before_state": None if before_state is None else json.dumps(before_state),
        "after_state": None if after_state is None else json.dumps(after_state),
        "details": json.dumps(fields["details"]),
        "prev_hash": last_hash,
        "row_hash": row_hash,
    }
    row = db.execute(
        text(
            """
            INSERT INTO audit_log (stream_id, seq, occurred_at, actor, actor_role, action, outcome, case_id,
                target_type, target_id, before_state, after_state, evidence_ids, idempotency_key, request_id,
                prompt_run_id, details, prev_hash, row_hash)
            VALUES (:stream_id, :seq, :occurred_at, :actor, :actor_role, :action, :outcome, :case_id,
                :target_type, :target_id, CAST(:before_state AS jsonb), CAST(:after_state AS jsonb),
                :evidence_ids, :idempotency_key, :request_id, :prompt_run_id, CAST(:details AS jsonb),
                :prev_hash, :row_hash)
            RETURNING *
            """
        ),
        stored,
    ).one()
    db.execute(
        text("UPDATE audit_heads SET last_seq = :seq, last_hash = :row_hash, updated_at = now() WHERE stream_id = :s"),
        {"seq": seq, "row_hash": row_hash, "s": stream_id},
    )
    db.info.setdefault(_PENDING_KEY, {})[stream_id] = (seq, row_hash)
    return AuditEntry.model_validate(row._mapping)


def record_denied(*, reason: str, actor: Actor, action: AuditAction, **fields: Any) -> AuditEntry:
    """Log a refused attempt. Call it after the failed change has rolled back.

    It uses its own session and transaction so the line survives the rollback.
    """
    details = {**fields.pop("details", {}), "reason": reason}
    with SessionLocal() as session:
        entry = record(session, actor=actor, action=action, outcome=AuditOutcome.DENIED, details=details, **fields)
        session.commit()
    return entry


# ---------------------------------------------------------------- reading and verifying


def list_entries(
    db: Session, stream_id: str, *, actions: Sequence[AuditAction] = (), limit: int = 50, offset: int = 0
) -> tuple[int, list[AuditEntry]]:
    """Newest first. Returns the total for the filter and one page."""
    filters = "WHERE stream_id = :stream_id" + (" AND action = ANY(:actions)" if actions else "")
    params: dict[str, Any] = {"stream_id": stream_id, "actions": [a.value for a in actions]}
    total = db.execute(text(f"SELECT count(*) FROM audit_log {filters}"), params).scalar_one()
    rows = db.execute(
        text(f"SELECT * FROM audit_log {filters} ORDER BY seq DESC LIMIT :limit OFFSET :offset"),
        {**params, "limit": limit, "offset": offset},
    ).all()
    return total, [AuditEntry.model_validate(row._mapping) for row in rows]


def _row_fields(row: Any) -> dict[str, Any]:
    return {name: row._mapping[name] for name in HASHED_FIELDS}


def _check_entries(rows: Sequence[Any]) -> ChainBreak | None:
    previous_hash = GENESIS_HASH
    for index, row in enumerate(rows, start=1):
        if row.seq != index:
            return ChainBreak(seq=index, reason="Sequence gap or reorder", expected_hash=None, found_hash=None)
        if row.prev_hash != previous_hash:
            return ChainBreak(
                seq=row.seq, reason="prev_hash does not match the earlier entry",
                expected_hash=previous_hash, found_hash=row.prev_hash,
            )  # fmt: skip
        expected = compute_row_hash(_row_fields(row), row.prev_hash)
        if row.row_hash != expected:
            return ChainBreak(seq=row.seq, reason="Entry was changed", expected_hash=expected, found_hash=row.row_hash)
        previous_hash = row.row_hash
    return None


def _check_heads(db: Session, stream_id: str, rows: Sequence[Any]) -> ChainBreak | None:
    """The head row and the external checkpoint file must both agree with the chain."""
    head = db.execute(
        text("SELECT last_seq, last_hash FROM audit_heads WHERE stream_id = :s"), {"s": stream_id}
    ).first()
    last = rows[-1] if rows else None
    if head is not None and (last is None or (head.last_seq, head.last_hash) != (last.seq, last.row_hash)):
        return ChainBreak(
            seq=head.last_seq, reason="Head row does not match the last entry",
            expected_hash=head.last_hash, found_hash=last.row_hash if last else None,
        )  # fmt: skip
    anchor = read_checkpoint().get(stream_id)
    if anchor is None:
        return None
    at_anchor = next((row for row in rows if row.seq == anchor["last_seq"]), None)
    if at_anchor is None or at_anchor.row_hash != anchor["last_hash"]:
        return ChainBreak(
            seq=anchor["last_seq"], reason="Checkpoint file does not match the chain",
            expected_hash=anchor["last_hash"], found_hash=at_anchor.row_hash if at_anchor else None,
        )  # fmt: skip
    return None


def verify_stream(db: Session, stream_id: str) -> VerifyResult:
    rows = db.execute(text("SELECT * FROM audit_log WHERE stream_id = :s ORDER BY seq"), {"s": stream_id}).all()
    first_break = _check_entries(rows) or _check_heads(db, stream_id, rows)
    return VerifyResult(
        stream_id=stream_id, valid=first_break is None, entries_checked=len(rows), first_break=first_break
    )


def list_streams(db: Session) -> list[str]:
    names = db.execute(text("SELECT stream_id FROM audit_heads UNION SELECT stream_id FROM audit_log ORDER BY 1"))
    return [row.stream_id for row in names]


def require_legal(actor: Actor, *, action: AuditAction, target_type: str, target_id: str) -> None:
    """Refuse non-LEGAL actors and log the denied attempt."""
    if actor.role == ActorRole.LEGAL:
        return
    reason = "Only a LEGAL reviewer may do this"
    record_denied(reason=reason, actor=actor, action=action, target_type=target_type, target_id=target_id)
    raise AppError("PERMISSION_DENIED", reason, 403)
