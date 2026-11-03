"""Client message drafts of one case: build from records, save, edit, submit for legal review.

A draft is never sent. There is no send path. OPS edits and submits, the assigned LEGAL reviewer decides through
the proposal review route, and approved only changes the draft status. A draft that went to review is never overwritten."""

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases import communications, proposals, repository
from app.cases.repository import CaseRecord
from app.cases.service import case_number, humanize, portal_status_label
from app.cases.uploads import resolve_path
from app.core import audit
from app.core.contracts import ActorRole, AuditAction, ProposalKind, ProposalStatus
from app.core.dates import us_text
from app.core.errors import AppError
from app.core.security import Actor
from app.facts import sources
from app.facts.engine import CONFLICT, NO_SOURCE, UNVERIFIED, FieldState, label_for
from app.ingest import loader
from app.ingest import service as ingest
from app.replies import templates, triage
from app.replies.templates import Drafted, Gap, Portal
from app.replies.triage import Question, Route, Triage

COLUMNS = (
    "draft_id, case_id, kind, channel, subject, body, reply_to_source_id, source_ids, triage, status, proposal_id, "
    "created_by, send_status, created_at, updated_at"
)
REPLY, MISSING = ("STATUS_REPLY", "REFUSAL"), ("MISSING_FIELDS",)
DRAFT, PENDING, APPROVED, REJECTED = "DRAFT", "PENDING_LEGAL_REVIEW", "APPROVED", "REJECTED"
ASK_STATES = (CONFLICT, UNVERIFIED, NO_SOURCE)
_CASE_REF = re.compile(r"\bCASE-[A-Z0-9]+\b", re.I)
# These reason codes mean the file belongs to someone else, so its id is never cited.
FOREIGN_CODES = ("WRONG_CLIENT", "MIXED_CLIENTS", "OWNER_MISMATCH")


class ProposalNote(BaseModel):
    proposal_id: str
    status: ProposalStatus
    reviewed_by: str | None
    review_reason: str | None


class Draft(BaseModel):
    draft_id: str
    case_id: str
    kind: str
    channel: str
    subject: str | None
    body: str
    reply_to_source_id: str | None
    source_ids: list[str]
    triage: dict[str, Any] | None
    status: str
    proposal_id: str | None
    created_by: str
    send_status: str
    created_at: datetime
    updated_at: datetime
    proposal: ProposalNote | None = None


class Built(BaseModel):
    kind: str
    channel: str
    subject: str | None
    body: str
    source_ids: list[str]
    triage: dict[str, Any] | None = None
    asks: list[str] = []


def _refuse(actor: Actor, action: AuditAction, case_id: str, draft_id: str | None, reason: str) -> AppError:
    audit.record_denied(reason=reason, actor=actor, action=action, case_id=case_id, target_type="message_draft", target_id=draft_id)
    return AppError("ACTION_NOT_ALLOWED", reason, 403)


def require_ops(actor: Actor, case: CaseRecord, action: AuditAction, draft_id: str | None = None) -> None:
    if actor.role != ActorRole.OPS or case.assigned_ops_user != actor.label:
        raise _refuse(actor, action, case.case_id, draft_id, "Only the assigned operations user can change a message draft")


# ---------------------------------------------------------------- reading the records


def _upload_text(db: Session, case_id: str, upload_id: str) -> str:
    """The text of an uploaded chat or email. Empty when the file cannot be read."""
    row = db.execute(
        text("SELECT storage_root, storage_path, original_filename FROM uploads WHERE upload_id = :u AND case_id = :c"),
        {"u": upload_id, "c": case_id},
    ).first()
    if row is None:
        return ""
    try:
        doc = loader.load_bytes(resolve_path(row.storage_root, row.storage_path).read_bytes(), row.original_filename)
    except (AppError, loader.RejectedFile, OSError):
        return ""
    return "\n".join(page.text for page in doc.pages)


def latest_question(db: Session, case_id: str) -> Question | None:
    """The newest inbound client message of this case, from the messages table or a message upload."""
    inbound = [c for c in communications.list_communications(db, case_id) if c.direction == "INBOUND" and not c.is_draft]
    if not inbound:
        return None
    last = inbound[-1]
    body = last.body or (_upload_text(db, case_id, last.source_id) if last.source_id.startswith("UP-") else "")
    if not body.strip():
        return None
    channel = last.kind if last.kind in ("WHATSAPP", "EMAIL") else "EMAIL"
    return Question(source_id=last.source_id, channel=channel, occurred_at=last.occurred_at, text=body.strip())


def portal_of(db: Session, case_id: str) -> Portal | None:
    row = repository.get_portal_status(db, case_id)
    word = portal_status_label(row["details"]) if row else None
    if row is None or not word or len(word) > 40:
        return None
    return Portal(event_id=row["event_id"], status=word, recorded=row["event_date"])


def gaps_of(db: Session, case_id: str) -> tuple[list[Gap], list[str], bool]:
    """Required documents that are missing or unusable in plain words, the file ids that can be cited, and whether files are still unread.

    While a file is unread nothing can be called missing, so missing items are left out."""
    unread = bool(db.execute(text("SELECT 1 FROM uploads WHERE case_id = :c AND deleted_at IS NULL AND outcome IN ('PENDING', 'READING') LIMIT 1"), {"c": case_id}).first())
    items = [c for c in ingest.checklist(db, case_id) if c.status != "SATISFIED" and not (unread and c.status == "MISSING")]
    ids = [r.upload_id for c in items for r in c.reasons]
    codes = {r.upload_id: r.reason_code for r in db.execute(
        text("SELECT upload_id, reason_code FROM uploads WHERE case_id = :c AND upload_id = ANY(:ids)"), {"c": case_id, "ids": ids})}  # fmt: skip
    gaps, cited = [], []
    for item in items:
        if item.status == "MISSING":
            gaps.append(Gap(item.label, templates.NOT_RECEIVED))
            continue
        used = [codes.get(r.upload_id) for r in item.reasons]
        gaps.append(Gap(item.label, templates.unusable_reason(used)))
        cited += [r.upload_id for r in item.reasons if codes.get(r.upload_id) not in FOREIGN_CODES]
    return gaps, cited, unread


def asks_of(db: Session, states: list[FieldState]) -> tuple[list[str], list[str]]:
    """What the firm needs for each field that is in conflict, unverified or without a source, and the cited source ids."""
    candidates = sources._candidates(db, requestable=True)
    asks, cited = [], []
    # The additional client fields are optional extras, so the firm never asks for them in the missing information email.
    for state in (s for s in states if s.state in ASK_STATES and s.field in sources.FIELDS):
        docs = sorted({humanize(name.split(".")[0]).lower() for name in candidates.get(state.field, []) if sources.DOC_KEY.match(name)})
        asks.append(templates.ask_text(label_for(state.field).lower(), state.state, docs, any(s.source_kind == "PROFILE" for s in state.sources)))
        cited += [s.source_id for s in state.sources]
    return asks, cited


# ---------------------------------------------------------------- building a draft


def _unique(ids: list[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def build_reply(db: Session, case: CaseRecord, question: Question, call: Any = None) -> Built:
    """Triage the question, then fill the template that the route allows."""
    result = triage.classify(case.case_id, question, call)
    portal, as_of, name = portal_of(db, case.case_id), repository.get_as_of(db), case.display_name
    cited = [question.source_id] + ([portal.event_id] if portal else [])
    kind, route = "REFUSAL", result.route
    if route == Route.ANSWER:
        gaps, files, unread = gaps_of(db, case.case_id)
        kind, drafted = "STATUS_REPLY", templates.status_reply(case.case_id, name, portal, gaps, as_of, unread)
        cited += files
    elif route == Route.REFUSE_OTHER_CLIENT:
        drafted, cited = templates.other_client_reply(case.case_id, name), [question.source_id]
    elif route == Route.REFUSE_ADVICE:
        drafted = templates.refusal_reply(case.case_id, name, portal, as_of)
    else:
        drafted = templates.unsupported_reply(case.case_id, name, portal, as_of)
    subject = f"Your case {case.case_id}" if question.channel == "EMAIL" else None
    return Built(kind=kind, channel=question.channel, subject=subject, body=drafted.body, source_ids=_unique(cited),
                 triage=result.model_dump(mode="json"))  # fmt: skip


def build_missing(db: Session, case: CaseRecord, states: list[FieldState]) -> Built:
    """The email that asks for every field and document the firm still needs. Empty asks mean nothing to send."""
    asks, cited = asks_of(db, states)
    gaps, files, unread = gaps_of(db, case.case_id)
    drafted: Drafted = templates.missing_fields_email(case.case_id, case.display_name, asks, gaps, unread)
    return Built(kind="MISSING_FIELDS", channel="EMAIL", subject=drafted.subject, body=drafted.body,
                 source_ids=_unique(cited + files), asks=asks + [f"{g.label}: {g.reason}" for g in gaps])  # fmt: skip


# ---------------------------------------------------------------- saving


def _note(db: Session, draft: Draft) -> Draft:
    if not draft.proposal_id:
        return draft
    p = proposals.get(db, draft.proposal_id)
    return draft.model_copy(update={"proposal": ProposalNote(proposal_id=p.proposal_id, status=p.status, reviewed_by=p.reviewed_by,
                                                             review_reason=p.review_reason)})  # fmt: skip


def get_draft(db: Session, case_id: str, draft_id: str, *, lock: bool = False) -> Draft:
    suffix = " FOR UPDATE" if lock else ""
    row = db.execute(text(f"SELECT {COLUMNS} FROM message_drafts WHERE draft_id = :d AND case_id = :c{suffix}"), {"d": draft_id, "c": case_id}).first()
    if row is None:
        raise AppError("DRAFT_NOT_FOUND", f"No message draft {draft_id}", 404)
    return Draft.model_validate(row._mapping)


def current_draft(db: Session, case_id: str, kinds: tuple[str, ...], reply_to: str | None) -> Draft | None:
    row = db.execute(
        text(f"SELECT {COLUMNS} FROM message_drafts WHERE case_id = :c AND kind = ANY(:k) "
             "AND reply_to_source_id IS NOT DISTINCT FROM :r ORDER BY id DESC LIMIT 1"),
        {"c": case_id, "k": list(kinds), "r": reply_to},
    ).first()  # fmt: skip
    return _note(db, Draft.model_validate(row._mapping)) if row else None


def _record_created(db: Session, actor: Actor, case_id: str, draft: Draft, regenerated: bool) -> None:
    details = {"kind": draft.kind, "channel": draft.channel, "regenerated": regenerated}
    result = draft.triage or {}
    if result:
        details.update(intent=result["intent"], origin=result["origin"])
    audit.record(db, actor=actor, action=AuditAction.MESSAGE_DRAFT_CREATED, case_id=case_id, target_type="message_draft",
                 target_id=draft.draft_id, evidence_ids=draft.source_ids, details=details)  # fmt: skip
    if result.get("injection_flag") and draft.reply_to_source_id:
        audit.record(db, actor=actor, action=AuditAction.INJECTION_FLAGGED, case_id=case_id, target_type="message",
                     target_id=draft.reply_to_source_id, details={"where": "client question"})  # fmt: skip


def save(db: Session, actor: Actor, case: CaseRecord, built: Built, *, reply_to: str | None, regenerate: bool) -> Draft:
    """Create a draft, or update the open one when asked. A draft in review is locked and a decided one is never touched."""
    require_ops(actor, case, AuditAction.MESSAGE_DRAFT_CREATED)
    kinds = MISSING if built.kind in MISSING else REPLY
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"drafts:{case.case_id}"})
    current = current_draft(db, case.case_id, kinds, reply_to)
    if current and not regenerate:
        return current
    if current and current.status == PENDING:
        raise AppError("DRAFT_LOCKED", f"{current.draft_id} is waiting for legal review", 409)
    params = {"kind": built.kind, "channel": built.channel, "subject": built.subject, "body": built.body,
              "ids": json.dumps(built.source_ids), "triage": json.dumps(built.triage) if built.triage else None}  # fmt: skip
    if current and current.status == DRAFT:
        row = db.execute(
            text("UPDATE message_drafts SET kind = :kind, channel = :channel, subject = :subject, body = :body, source_ids = CAST(:ids AS jsonb), "
                 f"triage = CAST(:triage AS jsonb), updated_at = now() WHERE draft_id = :d RETURNING {COLUMNS}"),
            {**params, "d": current.draft_id},
        ).one()  # fmt: skip
        draft = Draft.model_validate(row._mapping)
        _record_created(db, actor, case.case_id, draft, True)
        return draft
    count = db.execute(text("SELECT count(*) FROM message_drafts WHERE case_id = :c"), {"c": case.case_id}).scalar_one()
    same = db.execute(text("SELECT count(*) FROM message_drafts WHERE case_id = :c AND kind = ANY(:k) AND reply_to_source_id IS NOT DISTINCT FROM :r"),
                      {"c": case.case_id, "k": list(kinds), "r": reply_to}).scalar_one()  # fmt: skip
    row = db.execute(
        text("INSERT INTO message_drafts (draft_id, case_id, kind, channel, subject, body, reply_to_source_id, source_ids, triage, "
             "created_by, idempotency_key) VALUES (:d, :c, :kind, :channel, :subject, :body, :r, CAST(:ids AS jsonb), CAST(:triage AS jsonb), "
             f":by, :key) RETURNING {COLUMNS}"),
        {**params, "d": f"DRAFT-{case_number(case.case_id)}-{count + 1}", "c": case.case_id, "r": reply_to, "by": actor.label,
         "key": f"{case.case_id}:{kinds[0]}:{reply_to or '-'}:{same + 1}"},
    ).one()  # fmt: skip
    draft = Draft.model_validate(row._mapping)
    _record_created(db, actor, case.case_id, draft, False)
    return draft


def normalize_body(body: str, case_id: str) -> str:
    """Keep the DRAFT line at the top and the not sent line at the bottom. Another case reference is refused."""
    clean = us_text("\n".join(line.rstrip() for line in body.replace("\r", "").strip().split("\n")))
    if any(ref.upper() != case_id.upper() for ref in _CASE_REF.findall(clean)):
        raise AppError("FOREIGN_CASE_REFERENCE", "A draft can only mention its own case", 422)
    if not clean.startswith(templates.DRAFT_LINE):
        clean = f"{templates.DRAFT_LINE}\n\n{clean}"
    if not clean.endswith(templates.NOT_SENT_LINE):
        clean = f"{clean}\n\n{templates.NOT_SENT_LINE}"
    return clean


def body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def edit(db: Session, actor: Actor, case: CaseRecord, draft_id: str, body: str) -> Draft:
    """OPS changes the text only. The cited ids stay and only a draft that is still DRAFT can change."""
    require_ops(actor, case, AuditAction.MESSAGE_DRAFT_EDITED, draft_id)
    draft = get_draft(db, case.case_id, draft_id, lock=True)
    if draft.status != DRAFT:
        raise AppError("DRAFT_LOCKED", f"{draft_id} is {draft.status.lower().replace('_', ' ')} and cannot be edited", 409)
    clean = normalize_body(body, case.case_id)
    row = db.execute(text(f"UPDATE message_drafts SET body = :b, updated_at = now() WHERE draft_id = :d RETURNING {COLUMNS}"),
                     {"b": clean, "d": draft_id}).one()  # fmt: skip
    audit.record(db, actor=actor, action=AuditAction.MESSAGE_DRAFT_EDITED, case_id=case.case_id, target_type="message_draft",
                 target_id=draft_id, evidence_ids=draft.source_ids, before_state={"body_hash": body_hash(draft.body)},
                 after_state={"body_hash": body_hash(clean)})  # fmt: skip
    return _note(db, Draft.model_validate(row._mapping))


def submit(db: Session, actor: Actor, case: CaseRecord, draft_id: str) -> tuple[Draft, proposals.Proposal]:
    """OPS proposes a MESSAGE_APPROVE. The same draft and text give the same proposal. Rejected text is never proposed again."""
    require_ops(actor, case, AuditAction.MESSAGE_DRAFT_SUBMITTED, draft_id)
    draft = get_draft(db, case.case_id, draft_id, lock=True)
    if draft.status != DRAFT:
        if draft.status != REJECTED and draft.proposal_id:
            return _note(db, draft), proposals.get(db, draft.proposal_id)
        raise AppError("DRAFT_REJECTED", f"{draft_id} was rejected. Edit a new draft before sending it for review", 409)
    digest = body_hash(draft.body)
    rejected = db.execute(
        text("SELECT 1 FROM proposals WHERE case_id = :c AND kind = 'MESSAGE_APPROVE' AND status = 'REJECTED' AND value->>'body_hash' = :h LIMIT 1"),
        {"c": case.case_id, "h": digest},
    ).first()  # fmt: skip
    if rejected:
        raise AppError("REJECTED_BODY_UNCHANGED", "A legal reviewer rejected this exact text. Change the text first", 409)
    value = {"draft_id": draft_id, "body_hash": digest, "kind": draft.kind, "channel": draft.channel, "subject": draft.subject, "body": draft.body}
    proposal = proposals.propose(
        db, actor, case, kind=ProposalKind.MESSAGE_APPROVE, idempotency_key=f"{case.case_id}:MESSAGE_APPROVE:{draft_id}:{digest[:16]}",
        value=value, evidence_ids=draft.source_ids, target_type="message_draft", target_id=draft_id,
    )  # fmt: skip
    if proposal.status == ProposalStatus.REJECTED:
        raise AppError("REJECTED_BODY_UNCHANGED", "A legal reviewer rejected this exact text. Change the text first", 409)
    row = db.execute(text(f"UPDATE message_drafts SET status = 'PENDING_LEGAL_REVIEW', proposal_id = :p, updated_at = now() WHERE draft_id = :d RETURNING {COLUMNS}"),
                     {"p": proposal.proposal_id, "d": draft_id}).one()  # fmt: skip
    audit.record(db, actor=actor, action=AuditAction.MESSAGE_DRAFT_SUBMITTED, case_id=case.case_id, target_type="message_draft",
                 target_id=draft_id, evidence_ids=draft.source_ids, after_state={"status": PENDING},
                 details={"proposal_id": proposal.proposal_id, "body_hash": digest}, idempotency_key=proposal.idempotency_key)  # fmt: skip
    return _note(db, Draft.model_validate(row._mapping)), proposal
