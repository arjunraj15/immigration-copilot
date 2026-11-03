"""Imports the starter kit into Postgres. Safe to run again: rows are keyed by their source ids,
unchanged rows are left alone, and a prior human decision is never overwritten."""

import csv
import hashlib
import json
from collections.abc import Callable, Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import audit
from app.core.contracts import AuditAction, AuditOutcome

RULE_FILES = {
    "document_rules": "04_case_document_rules.json",
    "form_field_map": "08_form_field_map.json",
    "deadline_rules": "10_deadline_rules.json",
    "form_template": "13_synthetic_form_template.json",
}
EVENT_CONTENT = ("case_id", "event_date", "event_type", "event_source", "source_reference", "details")


class TableReport(BaseModel):
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0


class LoadReport(BaseModel):
    tables: dict[str, TableReport] = Field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return any(report.inserted or report.updated for report in self.tables.values())


class KitMissingError(Exception):
    pass


# ---------------------------------------------------------------- readers and converters


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _flag(value: str | bool) -> bool:
    return value if isinstance(value, bool) else value.strip().upper() == "TRUE"


def _refs(value: str) -> list[str]:
    return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]


# ---------------------------------------------------------------- upsert


def _upsert(db: Session, table: str, key: str, rows: Iterable[dict[str, Any]], keep: str = "") -> TableReport:
    """Insert new rows and update changed ones. A row identical to the stored one is not touched.
    keep is a condition on the stored row. A stored row that meets it is never overwritten."""
    report = TableReport()
    for row in rows:
        columns = list(row)
        changing = [column for column in columns if column != key]
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(':' + c for c in columns)}) "
            f"ON CONFLICT ({key}) DO UPDATE SET "
            + ", ".join(f"{c} = EXCLUDED.{c}" for c in changing)
            + ", updated_at = now() "
            f"WHERE ({', '.join(f'{table}.{c}' for c in changing)}) IS DISTINCT FROM "
            f"({', '.join(f'EXCLUDED.{c}' for c in changing)})" + (f" AND NOT ({keep})" if keep else "") + " RETURNING (xmax = 0) AS inserted"
        )
        result = db.execute(text(sql), row).first()
        if result is None:
            report.unchanged += 1
        elif result.inserted:
            report.inserted += 1
        else:
            report.updated += 1
    return report


# ---------------------------------------------------------------- tables


# The demo cases all open for the two demo users, OPS-01 and LEGAL-01. The other cases keep the starter kit owners.
DEMO_OPS_USER = "OPS-01"
DEMO_LEGAL_REVIEWER = "LEGAL-01"


def _case_rows(kit: Path) -> list[dict[str, Any]]:
    columns = (
        "case_id", "web_record_id", "client_ref", "case_archetype", "operational_stage",
        "assigned_ops_user", "assigned_legal_reviewer", "opened_at", "matter_visibility", "priority",
    )  # fmt: skip
    rows = []
    for row in _read_csv(kit / "01_cases.csv"):
        owner = {"assigned_ops_user": DEMO_OPS_USER, "assigned_legal_reviewer": DEMO_LEGAL_REVIEWER} if row["priority"] == "DEMO" else {}
        rows.append({column: row[column] for column in columns} | {"opened_at": date.fromisoformat(row["opened_at"])} | owner)
    return rows


def _intake_rows(kit: Path) -> list[dict[str, Any]]:
    return [
        {
            "intake_id": row["intake_id"], "case_id": row["case_id"], "recorded_at": _moment(row["recorded_at"]),
            "platform": row["platform"], "speaker": row["speaker"], "summary": row["summary"],
            "raw_note_excerpt": row["raw_note_excerpt"], "ai_generated": _flag(row["ai_generated"]),
            "approved_as_fact": _flag(row["approved_as_fact"]),
        }
        for row in _read_jsonl(kit / "02_zoom_intake_notes.jsonl")
    ]  # fmt: skip


def _message_rows(kit: Path) -> list[dict[str, Any]]:
    return [
        {
            "message_id": row["message_id"], "case_id": row["case_id"], "thread_id": row["thread_id"],
            "created_at_source": _moment(row["created_at"]), "channel": row["channel"],
            "direction": row["direction"], "sender_role": row["sender_role"], "subject": row["subject"],
            "body": row["body"], "attachment_refs": _refs(row["attachment_refs"]),
            "delivery_state": row["delivery_state"],
        }
        for row in _read_jsonl(kit / "03_client_messages.jsonl")
    ]  # fmt: skip


# The kit's profile rows are human verified, so they are evidence as the rule file says. A person may still confirm one in
# the app, which records a real who and when, and a re-import never overwrites such a row.
CONFIRMED_NOTE = "Confirmed in app"


def _profile_rows(kit: Path) -> list[dict[str, Any]]:
    return [
        {
            "source_id": row["source_id"], "case_id": row["case_id"], "field_name": row["field_name"],
            "verified_value": row["verified_value"], "verification_state": row["verification_state"],
            "verified_at": _moment(row["verified_at"]), "verified_by": row["verified_by"],
        }
        for row in _read_csv(kit / "07_case_profiles.csv")
    ]  # fmt: skip


def _event_rows(kit: Path) -> list[dict[str, Any]]:
    return [
        {
            "event_id": row["event_id"], "case_id": row["case_id"], "event_date": date.fromisoformat(row["event_date"]),
            "event_type": row["event_type"], "event_source": row["event_source"],
            "source_reference": row["source_reference"], "details": row["details"],
            "source_verified": _flag(row["source_verified"]), "import_batch": row["import_batch"],
        }
        for row in _read_csv(kit / "09_case_events.csv")
    ]  # fmt: skip


def _upload_rows(kit: Path) -> list[dict[str, Any]]:
    return [
        {
            "upload_id": row["upload_id"], "case_id": row["folder_case_id"],
            "storage_object_id": row["storage_object_id"], "storage_root": "STARTER_KIT",
            "storage_path": row["file_path"], "original_filename": row["original_filename"],
            "mime_type": row["mime_type"], "file_size_bytes": int(row["file_size_bytes"]), "sha256": row["sha256"],
            "uploaded_at": _moment(row["upload_timestamp"]), "uploader_role": row["uploader_role"],
            "ingestion_source": row["ingestion_source"], "client_supplied_type": row["client_supplied_type"],
            "version_label": row["version_label"],
        }
        for row in _read_csv(kit / "05_document_manifest.csv")
    ]  # fmt: skip


def _load_events(db: Session, kit: Path) -> TableReport:
    """The same event arriving under a new id is stored once, under the id seen first."""
    seen: dict[tuple, str] = {}
    for row in db.execute(text(f"SELECT event_id, {', '.join(EVENT_CONTENT)} FROM case_events")):
        seen[tuple(row._mapping[column] for column in EVENT_CONTENT)] = row.event_id
    keep, skipped = [], 0
    for row in _event_rows(kit):
        content = tuple(row[column] for column in EVENT_CONTENT)
        if seen.setdefault(content, row["event_id"]) != row["event_id"]:
            skipped += 1
            continue
        keep.append(row)
    report = _upsert(db, "case_events", "event_id", keep)
    report.skipped = skipped
    return report


def _load_rule_sets(db: Session, kit: Path) -> TableReport:
    """A changed rules file becomes a new version. Older versions stay for the audit trail."""
    report = TableReport()
    for key, filename in RULE_FILES.items():
        raw = (kit / filename).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        latest = db.execute(
            text("SELECT version, sha256 FROM rule_sets WHERE key = :key ORDER BY version DESC LIMIT 1"), {"key": key}
        ).first()
        if latest is not None and latest.sha256 == digest:
            report.unchanged += 1
            continue
        db.execute(
            text(
                "INSERT INTO rule_sets (key, version, source_file, body, sha256) "
                "VALUES (:key, :version, :source_file, CAST(:body AS jsonb), :sha256)"
            ),
            {
                "key": key, "version": 1 if latest is None else latest.version + 1, "source_file": filename,
                "body": raw.decode("utf-8"), "sha256": digest,
            },
        )  # fmt: skip
        report.inserted += 1 if latest is None else 0
        report.updated += 0 if latest is None else 1
    return report


def _load_review_decisions(db: Session, kit: Path) -> TableReport:
    """Prior human decisions are insert-only. A reload adds missing ones and never touches existing ones."""
    report = TableReport()
    for row in _read_jsonl(kit / "17_review_decisions_seed.jsonl"):
        inserted = db.execute(
            text(
                """
                INSERT INTO review_decisions (decision_id, case_id, field_name, rejected_value, corrected_value,
                    decision, reviewer_role, reviewer_id, reason, source_ref, recorded_at)
                VALUES (:decision_id, :case_id, :field_name, :rejected_value, :corrected_value, :decision,
                    :reviewer_role, :reviewer_id, :reason, :source_ref, :recorded_at)
                ON CONFLICT (decision_id) DO NOTHING RETURNING id
                """
            ),
            {
                "decision_id": row["decision_id"], "case_id": row["case_id"], "field_name": row.get("field_name"),
                "rejected_value": row.get("rejected_value"), "corrected_value": row.get("corrected_value"),
                "decision": row["decision"], "reviewer_role": row["reviewer_role"], "reviewer_id": row["reviewer_id"],
                "reason": row.get("comment"), "source_ref": row.get("source_ref"),
                "recorded_at": _moment(row["recorded_at"]),
            },
        ).first()  # fmt: skip
        if inserted is None:
            report.unchanged += 1
            continue
        report.inserted += 1
        audit.record(
            db, actor=audit.SYSTEM_ACTOR, action=AuditAction.SEED_LOADED, outcome=AuditOutcome.SYSTEM,
            case_id=row["case_id"], target_type="review_decision", target_id=row["decision_id"],
            evidence_ids=[row["source_ref"]] if row.get("source_ref") else [],
            details={"note": "Loaded a prior human decision", "field_name": row.get("field_name")},
        )  # fmt: skip
    return report


def _ensure_workflows(db: Session) -> TableReport:
    inserted = db.execute(
        text("INSERT INTO case_workflows (case_id) SELECT case_id FROM cases ON CONFLICT (case_id) DO NOTHING")
    ).rowcount
    total = db.execute(text("SELECT count(*) FROM cases")).scalar_one()
    return TableReport(inserted=inserted, unchanged=total - inserted)


def _ensure_actors(db: Session) -> TableReport:
    """The operations users and legal reviewers the cases name, so each can be chosen under Acting as."""
    inserted = 0
    for column, role in (("assigned_ops_user", "OPS"), ("assigned_legal_reviewer", "LEGAL")):
        inserted += db.execute(
            text(f"INSERT INTO actors (label, role) SELECT DISTINCT {column}, '{role}' FROM cases WHERE {column} IS NOT NULL ON CONFLICT (label) DO NOTHING")
        ).rowcount
    total = db.execute(text("SELECT count(*) FROM actors")).scalar_one()
    return TableReport(inserted=inserted, unchanged=total - inserted)


# ---------------------------------------------------------------- intake files only

INTAKE_FILES = ("02_zoom_intake_notes.jsonl", "03_client_messages.jsonl", "07_case_profiles.csv", "09_case_events.csv")


def _derived_case_rows(kit: Path, stages: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """One case per case id found in the notes, messages, profiles and events. 01_cases.csv is not read. The archetype comes from
    the document rules, the demo users own the case, and it opens on the earliest date any of its records carries.
    A new case has no file, so every required document is owed and it starts in document collection. A case already stored keeps
    its stage, so loading again never undoes the work done in the app."""
    dates: dict[str, list[date]] = {}
    for row in _intake_rows(kit):
        dates.setdefault(row["case_id"], []).append(row["recorded_at"].date())
    for row in _message_rows(kit):
        dates.setdefault(row["case_id"], []).append(row["created_at_source"].date())
    for row in _event_rows(kit):
        dates.setdefault(row["case_id"], []).append(row["event_date"])
    for row in _profile_rows(kit):
        dates.setdefault(row["case_id"], []).append(row["verified_at"].date())
    archetype = json.loads((kit / RULE_FILES["document_rules"]).read_text(encoding="utf-8")).get("archetype", "UNKNOWN")
    rows = []
    for case_id in sorted(dates):
        number = int(case_id.rsplit("-", 1)[-1]) if case_id.rsplit("-", 1)[-1].isdigit() else 0
        rows.append({
            "case_id": case_id, "web_record_id": f"WEB-{number:05d}", "client_ref": f"CLIENT-{number:04d}",
            "case_archetype": archetype, "operational_stage": (stages or {}).get(case_id, "DOCUMENT_COLLECTION"), "assigned_ops_user": DEMO_OPS_USER,
            "assigned_legal_reviewer": DEMO_LEGAL_REVIEWER, "opened_at": min(dates[case_id]),
            "matter_visibility": "RESTRICTED", "priority": "NORMAL",
        })  # fmt: skip
    return rows


def load_intake_files(db: Session, kit_dir: Path) -> LoadReport:
    """Load only the Zoom notes, client messages, profiles and events, plus the rule files the app needs. The cases are derived
    from their ids. No upload manifest and no document is loaded, the user adds files in the app. Safe to run again."""
    missing = [name for name in (*INTAKE_FILES, *RULE_FILES.values()) if not (kit_dir / name).exists()]
    if missing:
        raise KitMissingError(f"Starter kit files not found at {kit_dir}: {', '.join(missing)}")
    loaders: list[tuple[str, Callable[[], TableReport]]] = [
        ("cases", lambda: _upsert(db, "cases", "case_id", _derived_case_rows(kit_dir, dict(db.execute(text("SELECT case_id, operational_stage FROM cases")).all())))),
        ("intake_notes", lambda: _upsert(db, "intake_notes", "intake_id", _intake_rows(kit_dir))),
        ("messages", lambda: _upsert(db, "messages", "message_id", _message_rows(kit_dir))),
        ("profile_fields", lambda: _upsert(db, "profile_fields", "source_id", _profile_rows(kit_dir), keep=f"COALESCE(profile_fields.note, '') LIKE '{CONFIRMED_NOTE}%'")),
        ("case_events", lambda: _load_events(db, kit_dir)),
        ("rule_sets", lambda: _load_rule_sets(db, kit_dir)),
        ("case_workflows", lambda: _ensure_workflows(db)),
        ("actors", lambda: _ensure_actors(db)),
    ]
    report = LoadReport()
    for name, load in loaders:
        report.tables[name] = load()
    if report.changed:
        audit.record(
            db, actor=audit.SYSTEM_ACTOR, action=AuditAction.SEED_LOADED, outcome=AuditOutcome.SYSTEM,
            target_type="starter_kit", target_id=kit_dir.name,
            details={"note": "Loaded the intake files only", **{n: r.inserted + r.updated for n, r in report.tables.items()}},
        )  # fmt: skip
        from app.facts import engine

        engine.invalidate(db)
    db.commit()
    return report


# ---------------------------------------------------------------- entry point


def load_starter_kit(db: Session, kit_dir: Path) -> LoadReport:
    """Load every kit file in one transaction, then commit. Parents come before children."""
    if not (kit_dir / "01_cases.csv").exists():
        raise KitMissingError(f"Starter kit not found at {kit_dir}")
    loaders: list[tuple[str, Callable[[], TableReport]]] = [
        ("cases", lambda: _upsert(db, "cases", "case_id", _case_rows(kit_dir))),
        ("intake_notes", lambda: _upsert(db, "intake_notes", "intake_id", _intake_rows(kit_dir))),
        ("messages", lambda: _upsert(db, "messages", "message_id", _message_rows(kit_dir))),
        ("profile_fields", lambda: _upsert(db, "profile_fields", "source_id", _profile_rows(kit_dir), keep=f"COALESCE(profile_fields.note, '') LIKE '{CONFIRMED_NOTE}%'")),
        ("case_events", lambda: _load_events(db, kit_dir)),
        ("uploads", lambda: _upsert(db, "uploads", "upload_id", _upload_rows(kit_dir))),
        ("rule_sets", lambda: _load_rule_sets(db, kit_dir)),
        ("review_decisions", lambda: _load_review_decisions(db, kit_dir)),
        ("case_workflows", lambda: _ensure_workflows(db)),
        ("actors", lambda: _ensure_actors(db)),
    ]
    report = LoadReport()
    for name, load in loaders:
        report.tables[name] = load()
    if report.changed:
        audit.record(
            db, actor=audit.SYSTEM_ACTOR, action=AuditAction.SEED_LOADED, outcome=AuditOutcome.SYSTEM,
            target_type="starter_kit", target_id=kit_dir.name,
            details={"note": "Loaded the starter kit", **{n: r.inserted + r.updated for n, r in report.tables.items()}},
        )  # fmt: skip
    if report.changed:
        # Notes, messages, profiles or decisions may have changed, so every case builds its field states again on its next read.
        from app.facts import engine

        engine.invalidate(db)
    db.commit()
    return report
