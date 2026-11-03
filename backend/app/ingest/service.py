"""Read an upload end to end: load pages, apply the document rules, call the reader, store the outcome.

Every upload ends in exactly one outcome with a reason. Reads are claimed with the READING outcome so two
callers never read the same upload at once. A person can send a Human review upload again with force.
"""

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

from fastapi import BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai import reader
from app.ai.reader import ModelUnavailable
from app.cases import repository, stage
from app.cases.documents import _CLIENT_NAME
from app.cases.service import humanize
from app.cases.uploads import resolve_path
from app.core import audit
from app.core.config import get_settings
from app.core.contracts import AuditAction, DocumentRead, ReadStatus, UploadOutcome
from app.core.errors import AppError
from app.core.security import Actor
from app.db.session import SessionLocal
from app.ingest import comm, jobs, loader, rules
from app.ingest.loader import IMAGE, LoadedDoc, RejectedFile
from app.ingest.rules import Facts, Verdict
from app.facts import match_gate
from app.validation import values
from app.validation.context import RuleContext

log = logging.getLogger(__name__)

STALE_READING_MINUTES = 10
AI_DOWN_REASON = "The AI service was not available, so this file has not been read yet"
ANALYSE_WORKERS = 8
# Reads running at once across every job. A job over its share waits here, so 100 cases sent together queue and never exhaust the DB pool.
READ_SLOTS = threading.BoundedSemaphore(8)
# The kit numbers the identifiers of one person alike: SYN-P-00001, SYN-ARR-00001, SYN-PAY-00001-AUG, SYN-RCPT-00001.
REF_SERIAL = re.compile(r"SYN-(?:P|ARR|PAY|RCPT)-(\d+)")
# The starter kit marks an old file with one line: "older version superseded by a later version".
# The rule file has no wording for it, so this comes from the real pages (CASE-0005, UP-000028).
SUPERSEDED_MARK = re.compile(r"\bolder version superseded by a (?:later|newer) version\b", re.IGNORECASE)
PROBLEM_TEXT = {
    "BLANK": "is blank",
    "ROTATED": "is rotated and cannot be read upright",
    "UNREADABLE": "has too little readable content",
}
ROTATED_CORRECTED = (
    "Page {page} was rotated. Code turned it upright for the AI read, so its values are unverified and the file is "
    "held for review"
)
_REVIEW, _PENDING = UploadOutcome.NEEDS_HUMAN_REVIEW.value, UploadOutcome.PENDING.value
_READING = UploadOutcome.READING.value


class PageOut(BaseModel):
    page: int
    text_source: str
    chars: int
    reason: str | None = None


class UploadResult(BaseModel):
    upload_id: str
    case_id: str
    outcome: str
    category: str | None
    reason_code: str | None
    reason: str | None
    pages: list[PageOut]


# ---------------------------------------------------------------- reader wiring


def build_deps(loaded: reader.LoadedUpload, cache: dict) -> reader.ReaderDeps:
    """The real Anthropic call through run_prompt. Tests replace this function with a fake model."""
    deps = reader.default_deps(lambda _id: loaded)
    deps.cache = cache
    deps.as_of = _review_date
    return deps


def _review_date() -> date:
    """The fixed review date the date tools call today. Never the system clock."""
    with SessionLocal() as db:
        return repository.get_as_of(db)


def _shared_cache() -> dict:
    return reader.default_deps().cache  # type: ignore[return-value]


# ---------------------------------------------------------------- claiming


def _claim(db: Session, upload_id: str, claimable: tuple[str, ...], force: bool) -> str | None:
    """Mark the upload READING and return the outcome it had. None when it is not ours to read."""
    row = db.execute(
        text(
            "SELECT outcome, updated_at < now() - make_interval(mins => :m) AS stale "
            "FROM uploads WHERE upload_id = :u AND deleted_at IS NULL FOR UPDATE"
        ),
        {"u": upload_id, "m": STALE_READING_MINUTES},
    ).first()
    if row is None:
        raise AppError("UPLOAD_NOT_FOUND", f"No upload {upload_id}", 404)
    ours = row.outcome in claimable or (row.outcome == _READING and row.stale) or (force and row.outcome != _READING)
    if not ours:
        db.rollback()
        return None
    db.execute(text("UPDATE uploads SET outcome = 'READING', updated_at = now() WHERE upload_id = :u"), {"u": upload_id})
    db.commit()
    return _PENDING if row.outcome == _READING else row.outcome


def _release(db: Session, upload_id: str, outcome: str) -> None:
    db.rollback()
    db.execute(text("UPDATE uploads SET outcome = :o, updated_at = now() WHERE upload_id = :u"), {"o": outcome, "u": upload_id})
    db.commit()


# ---------------------------------------------------------------- facts for the rules


def load_rules(db: Session) -> RuleContext:
    return repository.load_context(db)


def _references(db: Session, case_id: str, upload_id: str) -> tuple[frozenset[str], frozenset[str]]:
    """Document references in this case and the references its certified translations point to."""
    rows = db.execute(
        text(
            "SELECT storage_root, storage_path, original_filename FROM uploads WHERE case_id = :c AND deleted_at IS NULL AND upload_id <> :u "
            "AND outcome NOT IN ('QUARANTINED', 'INVALID')"
        ),
        {"c": case_id, "u": upload_id},
    ).all()
    refs: set[str] = set()
    targets: set[str] = set()
    for row in rows:
        try:
            data = resolve_path(row.storage_root, row.storage_path).read_bytes()
        except AppError:
            continue
        found = loader.first_page_labels(data, row.original_filename)
        refs.update(v for k, v in found.items() if k == "reference")
        targets.update(v for k, v in found.items() if k == "certified translation of")
    return frozenset(refs), frozenset(targets)


def _duplicate_of(db: Session, row: Any, sha: str) -> str | None:
    return db.execute(
        text(
            "SELECT upload_id FROM uploads WHERE case_id = :c AND sha256 = :h AND deleted_at IS NULL AND upload_id <> :u "
            "AND (uploaded_at, upload_id) < (:at, :u) ORDER BY uploaded_at, upload_id LIMIT 1"
        ),
        {"c": row.case_id, "h": sha, "u": row.upload_id, "at": row.uploaded_at},
    ).scalar()


def _problem(doc: LoadedDoc) -> Verdict | None:
    for page in doc.pages:
        if page.corrected:
            return Verdict(UploadOutcome.NEEDS_HUMAN_REVIEW, page.problem, ROTATED_CORRECTED.format(page=page.number))
        if page.problem:
            return Verdict(UploadOutcome.NEEDS_HUMAN_REVIEW, page.problem, f"Page {page.number} {PROBLEM_TEXT[page.problem]}")
    return None


def _blocks_read(doc: LoadedDoc) -> bool:
    """A page problem stops the read, except a rotated page that code turned upright."""
    return any(page.problem and not page.corrected for page in doc.pages)


def _unverify(reads: list[DocumentRead], pages: set[int]) -> None:
    """Values from a page that code turned upright are never verified, even when the quote is found."""
    for read in reads:
        for item in read.fields.values():
            for row in item.items or []:
                row.verified = row.verified and row.page not in pages
            item.verified = item.verified and item.page not in pages and all(r.verified for r in item.items or [])


def _model_input(doc: LoadedDoc, foreign: list[int]) -> reader.LoadedUpload:
    """Only pages of this case. Scanned pages go only when the rest of the document is owned by this case."""
    pages, images = [], {}
    for page in doc.pages:
        if page.number in foreign or (page.problem and not page.corrected):
            continue
        if page.image is not None:
            if foreign:
                continue
            images[page.number] = page.image
            pages.append((page.number, reader.IMAGE_PAGE_TEXT))
        else:
            pages.append((page.number, page.text))
    # A call or message file is known by its own fields, so only its values go to the AI, not its type.
    return reader.LoadedUpload(doc.sha256, pages, images, category=doc.note_category if doc.note_text else None)


# ---------------------------------------------------------------- storing


def _flags(reads: list[DocumentRead], doc: LoadedDoc | None, foreign: list[int]) -> dict[str, Any]:
    flags: dict[str, Any] = {"injection": any(r.injection_flag for r in reads)}
    if foreign:
        flags["foreign_pages"] = foreign
    for read in reads:
        value, state = rules.field_value(read, "PAY_STATEMENT.Pay Period")
        if state == rules.OK:
            flags["pay_period"] = value
    if doc and (images := [p.number for p in doc.pages if p.source == IMAGE]):
        flags["image_pages"] = images
    if doc and (serials := sorted({m for p in doc.pages if p.number not in foreign for m in REF_SERIAL.findall(p.text or "")})):
        flags["ref_serials"] = serials
    return flags


def _store_pages(db: Session, upload_id: str, doc: LoadedDoc) -> None:
    for page in doc.pages:
        reason = page.problem or page.scanned_reason
        db.execute(
            text(
                "INSERT INTO document_pages (upload_id, page_number, text_source, char_count, rotation, owner_case_id, "
                "image_sha256, reason) VALUES (:u, :n, :s, :c, :r, :o, :h, :why) ON CONFLICT (upload_id, page_number) "
                "DO UPDATE SET text_source = :s, char_count = :c, rotation = :r, owner_case_id = :o, image_sha256 = :h, "
                "reason = :why, updated_at = now()"
            ),
            {"u": upload_id, "n": page.number, "s": page.source, "c": page.chars, "r": page.rotation,
             "o": page.owner, "h": page.image_sha, "why": reason},
        )  # fmt: skip
    db.execute(text("DELETE FROM document_pages WHERE upload_id = :u AND page_number > :n"), {"u": upload_id, "n": len(doc.pages)})


def _store_reads(db: Session, upload_id: str, reads: list[DocumentRead], verdict: Verdict, page_count: int | None) -> None:
    ordered = sorted(reads, key=lambda r: r.category in rules.UNKNOWN_CATEGORIES)
    if not ordered and verdict.outcome == UploadOutcome.NEEDS_HUMAN_REVIEW:
        ordered = [DocumentRead(category="REVIEW_REQUIRED", legible=False, status=ReadStatus.REVIEW_REQUIRED)]
    for read in ordered:
        db.execute(
            text(
                "INSERT INTO document_reads (upload_id, category, status, legible, injection_flag, language, page_count, "
                "reason, extracted) VALUES (:u, :c, :s, :l, :i, :lang, :p, :r, CAST(:x AS jsonb))"
            ),
            {"u": upload_id, "c": read.category, "s": read.status.value, "l": read.legible, "i": read.injection_flag,
             "lang": read.language, "p": page_count, "r": verdict.reason, "x": read.model_dump_json(include={"fields", "image_pages"})},
        )  # fmt: skip


def _store_note_meta(db: Session, upload_id: str, doc: LoadedDoc) -> None:
    """A call or message file keeps its own date and text, so the timeline shows the call or message and not the upload."""
    if doc.note_text:
        db.execute(text("UPDATE uploads SET occurred_at = CAST(:t AS timestamptz), note_text = :n WHERE upload_id = :u"),
                   {"t": doc.occurred_at, "n": doc.note_text, "u": upload_id})  # fmt: skip


def _store_outcome(db: Session, row: Any, verdict: Verdict, reads: list[DocumentRead], flags: dict[str, Any],
                   duplicate_of: str | None, owner_case: str | None) -> None:  # fmt: skip
    primary = next((r.category for r in reads if r.category not in rules.UNKNOWN_CATEGORIES), reads[0].category if reads else None)
    db.execute(
        text(
            "UPDATE uploads SET outcome = :o, reason_code = :rc, outcome_reason = :r, category = COALESCE(:cat, category), "
            "duplicate_of_upload_id = :d, owner_case_id = :oc, flags = CAST(:f AS jsonb), updated_at = now() WHERE upload_id = :u"
        ),
        {"o": verdict.outcome.value, "rc": verdict.code, "r": verdict.reason, "cat": primary, "d": duplicate_of,
         "oc": owner_case, "f": json.dumps(flags), "u": row.upload_id},
    )  # fmt: skip


def _audit(db: Session, actor: Actor, row: Any, verdict: Verdict, reads: list[DocumentRead], doc: LoadedDoc | None,
           first_read: bool, foreign: list[int]) -> None:  # fmt: skip
    def record(action: AuditAction, **details: Any) -> None:
        run_id = next((r.prompt_run_id for r in reads if r.prompt_run_id), None)
        audit.record(db, actor=actor, action=action, case_id=row.case_id, target_type="upload", target_id=row.upload_id,
                     prompt_run_id=run_id, details=details)  # fmt: skip

    if first_read:
        record(AuditAction.UPLOAD_RECEIVED, sha256=doc.sha256 if doc else None)
    if verdict.code == "DUPLICATE":
        record(AuditAction.DUPLICATE_DETECTED, reason_code="DUPLICATE")
    if verdict.outcome == UploadOutcome.QUARANTINED:
        record(AuditAction.QUARANTINED, reason_code=verdict.code, foreign_pages=foreign)
    if reads or verdict.code not in ("DUPLICATE", "WRONG_CLIENT", "MIXED_CLIENTS"):
        sources = {p.source: sum(1 for q in doc.pages if q.source == p.source) for p in doc.pages} if doc else {}
        record(AuditAction.DOCUMENT_READ, outcome=verdict.outcome.value, reason_code=verdict.code, page_sources=sources)
    if any(r.injection_flag for r in reads):
        record(AuditAction.INJECTION_FLAGGED, categories=[r.category for r in reads])


# ---------------------------------------------------------------- the read


def _load(row: Any) -> tuple[LoadedDoc | None, Verdict | None]:
    try:
        data = resolve_path(row.storage_root, row.storage_path).read_bytes()
        return loader.load_bytes(data, row.original_filename), None
    except AppError as exc:
        return None, Verdict(UploadOutcome.NEEDS_HUMAN_REVIEW, "FILE_MISSING", exc.message)
    except RejectedFile as exc:
        outcome = UploadOutcome.NEEDS_HUMAN_REVIEW if exc.code == "UNREADABLE" else UploadOutcome.INVALID
        return None, Verdict(outcome, exc.code, exc.message)


def _run_reader(doc: LoadedDoc, foreign: list[int], force: bool) -> list[DocumentRead]:
    loaded = _model_input(doc, foreign)
    if not loaded.pages:
        return []
    shared = _shared_cache()
    cache: dict = {} if force else shared
    reads = reader.read_document(0, build_deps(loaded, cache))
    if force:
        shared.update(cache)
    _unverify(reads, {page.number for page in doc.pages if page.corrected})
    return reads


def _doc_facts(db: Session, row: Any, doc: LoadedDoc, facts: Facts) -> tuple[list[int], str | None]:
    """Fill the facts that come from the file itself. Returns the foreign page numbers and the foreign owner."""
    facts.problem = _problem(doc)
    facts.duplicate_of = _duplicate_of(db, row, doc.sha256)
    owners = [(p.number, p.owner) for p in doc.pages if p.owner and p.owner != row.case_id]
    foreign = [n for n, _ in owners]
    facts.foreign_pages, facts.all_foreign = foreign, bool(foreign) and len(foreign) == len(doc.pages)
    facts.superseded = any(SUPERSEDED_MARK.search(p.text) for p in doc.pages if p.image is None)
    facts.page_labels = {p.number: loader.labels(p.text) for p in doc.pages if p.image is None and p.text}
    facts.docref = next((labels.get("reference") for labels in facts.page_labels.values()), None)
    return foreign, (owners[0][1] if owners else None)


def _received(db: Session, upload_id: str) -> bool:
    """True when the upload route already wrote the UPLOAD_RECEIVED line."""
    return bool(db.scalar(text("SELECT ingestion_source = 'WEB_UPLOAD' FROM uploads WHERE upload_id = :u"), {"u": upload_id}))


def _case_names(db: Session, case_id: str, upload_id: str, facts: Facts) -> list[str]:
    """Every name on file for the case: the client name, the profile name, claims and the applicants of its other files.
    A file set aside as a duplicate, a wrong client or an invalid file does not count. Empty for the first file of a new case."""
    found = [facts.known_name, facts.client_name]
    found += list(db.scalars(text("SELECT verified_value FROM profile_fields WHERE case_id = :c AND field_name = 'full_name' "
                                  "AND verification_state <> 'DRAFT_PLACEHOLDER'"), {"c": case_id}))  # fmt: skip
    found += list(db.scalars(text("SELECT value FROM claims WHERE case_id = :c AND field_name = 'full_name'"), {"c": case_id}))
    rows = db.execute(
        text("SELECT DISTINCT ON (r.upload_id) r.extracted FROM document_reads r JOIN uploads u ON u.upload_id = r.upload_id "
             "WHERE u.case_id = :c AND u.deleted_at IS NULL AND u.upload_id <> :u AND u.outcome IN ('USABLE', 'NEEDS_HUMAN_REVIEW') AND r.status = 'READ' "
             "AND r.extracted IS NOT NULL ORDER BY r.upload_id, r.read_at DESC, r.id DESC"),
        {"c": case_id, "u": upload_id},
    ).all()  # fmt: skip
    for row in rows:
        for key, item in (row.extracted.get("fields") or {}).items():
            if key.lower().endswith(".applicant") and isinstance(item, dict) and item.get("verified") and not item.get("from_image"):
                found.append(item.get("value") or "")
    return list(dict.fromkeys(" ".join(n.split()) for n in found if n and n.strip()))


def _settle_names(db: Session, case_id: str, upload_id: str, facts: Facts, reads: list[DocumentRead]) -> None:
    """The applicant on a document must be a name the case already has, so the file is for the right case. A name written
    differently, in another order or with an initial, is the same person. A different spelling is not. Which spelling is right
    is the conflict a person decides, not this check. The gate decides once per pair of names and the rules read the answer."""
    names = values.applicant_names(reads) + [n for r in reads for n in r.image_owner_names]
    on_file = _case_names(db, case_id, upload_id, facts)
    facts.known_names = tuple(on_file)
    match_gate.settle_names(db, names + on_file, case_id)
    facts.same_name = match_gate.name_matcher(db, names + on_file)


def _process(db: Session, actor: Actor, row: Any, previous: str, force: bool) -> None:
    doc, verdict = _load(row)
    foreign: list[int] = []
    owner_case = None
    reads: list[DocumentRead] = []
    # A draft has no client name yet, so a name on a scanned page cannot be compared with it.
    client = db.execute(
        text(f"SELECT CASE WHEN w.status = 'DRAFT' THEN '' ELSE {_CLIENT_NAME} END FROM cases c "
             "JOIN case_workflows w ON w.case_id = c.case_id WHERE c.case_id = :c"),
        {"c": row.case_id},
    ).scalar()  # fmt: skip
    facts = Facts(load_rules(db), client or "", reads)
    facts.known_name = "" if client in (None, row.case_id) else client  # a case without a profile name shows its id
    if doc is not None:
        foreign, owner_case = _doc_facts(db, row, doc, facts)
        if not (_blocks_read(doc) or facts.duplicate_of or facts.all_foreign):
            reads.extend(_run_reader(doc, foreign, force))
            if any(r.category in ("EMPLOYER_LETTER", "CERTIFIED_TRANSLATION") for r in reads):
                facts.case_docrefs, facts.translations_of = _references(db, row.case_id, row.upload_id)
    if reads:
        _settle_names(db, row.case_id, row.upload_id, facts, reads)
    verdict = verdict or rules.decide(facts)
    if doc is not None:
        _store_pages(db, row.upload_id, doc)
        _store_note_meta(db, row.upload_id, doc)
    _store_reads(db, row.upload_id, reads, verdict, len(doc.pages) if doc else None)
    claims = reads if verdict.outcome == UploadOutcome.CLAIM_SOURCE else []
    comm.store_claims(db, row.case_id, row.upload_id, claims)
    _store_outcome(db, row, verdict, reads, _flags(reads, doc, foreign), facts.duplicate_of, owner_case)
    _audit(db, actor, row, verdict, reads, doc, previous == _PENDING and not force and not _received(db, row.upload_id), foreign)
    stage.sync_documents(db, actor, row.case_id)
    db.commit()
    from app.facts import engine

    engine.recompute(db, row.case_id)


_ROW_SQL = (
    "SELECT upload_id, case_id, storage_root, storage_path, original_filename, uploaded_at FROM uploads WHERE upload_id = :u"
)


def read_upload(db: Session, actor: Actor, upload_id: str, *, force: bool = False,
                claimable: tuple[str, ...] = (_PENDING,)) -> UploadResult:  # fmt: skip
    """Read one upload and store its outcome. An upload that is already settled is returned as it is."""
    previous = _claim(db, upload_id, claimable, force)
    if previous is not None:
        row = db.execute(text(_ROW_SQL), {"u": upload_id}).one()
        try:
            _process(db, actor, row, previous, force)
        except ModelUnavailable:
            # The service failed, not the file. It goes back as it was, unread, with a reason that says so.
            _release(db, upload_id, previous)
            db.execute(text("UPDATE uploads SET outcome_reason = :r WHERE upload_id = :u"), {"r": AI_DOWN_REASON, "u": upload_id})
            db.commit()
            raise
        except Exception:
            _release(db, upload_id, previous)
            raise
    return upload_result(db, upload_id)


def load_pages(db: Session, upload_id: str) -> reader.LoadedUpload | None:
    """The pages of an upload as the reader would see them, or None when the file cannot be loaded. Nothing is stored."""
    row = db.execute(text(_ROW_SQL), {"u": upload_id}).first()
    if row is None:
        raise AppError("UPLOAD_NOT_FOUND", f"No upload {upload_id}", 404)
    doc, _ = _load(row)
    if doc is None:
        return None
    foreign = [p.number for p in doc.pages if p.owner and p.owner != row.case_id]
    return _model_input(doc, foreign)


def upload_result(db: Session, upload_id: str) -> UploadResult:
    row = db.execute(
        text("SELECT upload_id, case_id, outcome, category, reason_code, outcome_reason AS reason FROM uploads WHERE upload_id = :u"),
        {"u": upload_id},
    ).mappings().one()  # fmt: skip
    pages = db.execute(
        text("SELECT page_number AS page, text_source, char_count AS chars, reason FROM document_pages WHERE upload_id = :u ORDER BY page_number"),
        {"u": upload_id},
    ).mappings().all()  # fmt: skip
    return UploadResult(**row, pages=[PageOut(**p) for p in pages])


# ---------------------------------------------------------------- case jobs


def _read_event(actor: Actor, job_id: str, upload_id: str, claimable: tuple[str, ...]) -> None:
    event: dict[str, Any] = {"upload_id": upload_id}
    try:
        with READ_SLOTS, SessionLocal() as db:
            result = read_upload(db, actor, upload_id, claimable=claimable)
        event.update(outcome=result.outcome, reason_code=result.reason_code, summary=result.reason)
    except Exception as exc:
        log.exception("Reading %s failed", upload_id)
        event.update(outcome="ERROR", reason_code="READ_FAILED", summary=getattr(exc, "code", type(exc).__name__))
    with SessionLocal() as db:
        jobs.add_event(db, job_id, event)


def run_job(job_id: str, actor: Actor, upload_ids: list[str], claimable: tuple[str, ...]) -> None:
    with ThreadPoolExecutor(max_workers=ANALYSE_WORKERS) as pool:
        for upload_id in upload_ids:
            pool.submit(_read_event, actor, job_id, upload_id, claimable)
    with SessionLocal() as db:
        failed = any(e["outcome"] == "ERROR" for e in jobs.get(db, job_id)["events"])  # type: ignore[index]
        jobs.finish(db, job_id, "FAILED" if failed else "SUCCEEDED")


def start_case_job(db: Session, tasks: BackgroundTasks, actor: Actor, case_id: str, claimable: tuple[str, ...],
                   kind: str = "ANALYSE") -> str | None:  # fmt: skip
    """Queue a background read of the case uploads in the given outcomes. Returns the job id, None when nothing is to read."""
    ids = list(
        db.scalars(
            text(
                "SELECT upload_id FROM uploads WHERE case_id = :c AND deleted_at IS NULL AND (outcome = ANY(:o) OR (outcome = 'READING' AND "
                "updated_at < now() - make_interval(mins => :m))) ORDER BY uploaded_at, upload_id"
            ),
            {"c": case_id, "o": list(claimable), "m": STALE_READING_MINUTES},
        )
    )
    if not ids:
        return None
    job_id = jobs.create(db, kind, case_id, actor.label, len(ids))
    tasks.add_task(run_job, job_id, actor, ids, claimable)
    return job_id


def start_draft_job(db: Session, tasks: BackgroundTasks, actor: Actor, case_id: str) -> str | None:
    """One background job that reads the files of a new draft. None when auto read is off or nothing is pending."""
    if not get_settings().auto_read:
        return None
    return start_case_job(db, tasks, actor, case_id, (_PENDING,), "INTAKE")


def ensure_case_read(db: Session, tasks: BackgroundTasks, actor: Actor, case_id: str) -> str | None:
    """Automatic read of every PENDING upload of a case. Settled and READING uploads are never queued again."""
    if not get_settings().auto_read:
        return None
    try:
        return start_case_job(db, tasks, actor, case_id, (_PENDING,), "AUTO_READ")
    except Exception:
        log.exception("Could not queue the automatic read for %s", case_id)
        return None


# ---------------------------------------------------------------- checklist


class Reason(BaseModel):
    upload_id: str
    outcome: str
    reason: str | None


class ChecklistItem(BaseModel):
    category: str
    label: str
    status: str
    reasons: list[Reason] = []


def checklist(db: Session, case_id: str) -> list[ChecklistItem]:
    doc_rules = load_rules(db)
    rows = db.execute(
        text(
            "SELECT upload_id, category, outcome, outcome_reason, flags->>'pay_period' AS period FROM uploads "
            "WHERE case_id = :c AND deleted_at IS NULL AND category IS NOT NULL AND outcome NOT IN ('PENDING', 'READING')"
        ),
        {"c": case_id},
    ).all()
    items = []
    for category in doc_rules.required:
        period = doc_rules.pay_periods.get(category)
        label = f"Pay statement for {date.fromisoformat(period + '-01').strftime('%b %Y')}" if period else humanize(category)
        own = [r for r in rows if (r.category == "PAY_STATEMENT" and r.period == period if period else r.category == category)]
        if any(r.outcome == UploadOutcome.USABLE.value for r in own):
            items.append(ChecklistItem(category=category, label=label, status="SATISFIED"))
        elif own:
            items.append(ChecklistItem(category=category, label=label, status="NOT_USABLE",
                                       reasons=[Reason(upload_id=r.upload_id, outcome=r.outcome, reason=r.outcome_reason) for r in own]))  # fmt: skip
        else:
            items.append(ChecklistItem(category=category, label=label, status="MISSING"))
    return items
