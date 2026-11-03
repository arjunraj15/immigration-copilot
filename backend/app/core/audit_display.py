"""One place that turns a ledger entry into the label, tone and sentence the Activity tab shows.

The ledger stores ids and states only. Wording lives here so the UI never builds it.
"""

from typing import Literal

from pydantic import BaseModel

from app.core.audit import AuditEntry
from app.core.contracts import ActorRole, AuditAction, AuditOutcome

Tone = Literal["ok", "bad", "warn", "ai", "muted"]

# action: (label, tone, what the actor did)
_DISPLAY: dict[AuditAction, tuple[str, Tone, str]] = {
    AuditAction.UPLOAD_RECEIVED: ("Upload", "muted", "uploaded a file"),
    AuditAction.UPLOAD_DELETED: ("Upload", "bad", "deleted a file"),
    AuditAction.DATA_IMPORTED: ("Data import", "warn", "imported new case data"),
    AuditAction.DUPLICATE_DETECTED: ("Duplicate", "warn", "uploaded a file that was already received"),
    AuditAction.DUPLICATE_IGNORED: ("Duplicate ignored", "muted", "repeated a change that was already applied"),
    AuditAction.DOCUMENT_READ: ("Analysis", "muted", "read a document"),
    AuditAction.DOCUMENT_TYPE_SET: ("Review", "ok", "set the document type of a file"),
    AuditAction.DOCUMENT_TYPE_CREATED: ("AI draft", "ai", "created a new document type from a file"),
    AuditAction.FORM_FIELD_ADDED: ("AI setup", "ok", "added an additional client field to the form"),
    AuditAction.QUARANTINED: ("Set aside", "warn", "set a file aside"),
    AuditAction.INJECTION_FLAGGED: ("Security", "bad", "flagged instructions hidden in a document"),
    AuditAction.FACT_WRITTEN: ("Analysis", "muted", "recorded a fact"),
    AuditAction.CONFLICT_OPENED: ("Conflict", "warn", "found sources that disagree"),
    AuditAction.CONFLICT_RESOLVED: ("Approved", "ok", "decided a conflict"),
    AuditAction.CONFLICT_SUGGESTED: ("Review", "ai", "suggested a value for a conflict"),
    AuditAction.PROFILE_CONFIRMED: ("Approved", "ok", "confirmed a profile value"),
    AuditAction.REVIEW_REQUESTED: ("Review", "warn", "asked for a human review"),
    AuditAction.CASE_CREATED: ("Data import", "warn", "created the case"),
    AuditAction.CASE_DRAFT_CREATED: ("Intake", "muted", "started a draft case from intake notes and files"),
    AuditAction.CASE_DRAFT_DISCARDED: ("Intake", "warn", "discarded a draft case"),
    AuditAction.CASE_DELETED: ("Case", "bad", "deleted the case"),
    AuditAction.CASE_ACCESS: ("Case access", "muted", "opened a case"),
    AuditAction.ANALYSIS_RUN: ("Analysis", "muted", "finished an analysis run"),
    AuditAction.AI_DRAFT: ("AI draft", "muted", "drafted text"),
    AuditAction.PROPOSE: ("Proposed", "ai", "proposed a change"),
    AuditAction.REVIEW_APPROVE: ("Approved", "ok", "approved a proposal"),
    AuditAction.REVIEW_REJECT: ("Rejected", "bad", "rejected a proposal"),
    AuditAction.COMMIT: ("Applied", "ai", "applied an approved change"),
    AuditAction.FORM_EXPORTED: ("Exported", "ai", "downloaded an approved form as a draft PDF"),
    AuditAction.SUBMITTED_FOR_REVIEW: ("Proposed", "ai", "sent the case for attorney review"),
    AuditAction.INFO_REQUESTED: ("Review", "warn", "asked for more information"),
    AuditAction.RERUN_SKIPPED_PRIOR_REJECTION: ("Review", "warn", "kept an earlier human rejection on a rerun"),
    AuditAction.PROMPT_VERSION_CREATED: ("AI draft", "muted", "created a prompt version"),
    AuditAction.PROMPT_VERSION_ACTIVATED: ("AI draft", "muted", "activated a prompt version"),
    AuditAction.CHAT_QUESTION: ("Chat", "muted", "asked the case assistant a question"),
    AuditAction.CHAIN_VERIFIED: ("Verified", "ok", "verified the audit chain"),
    AuditAction.MESSAGE_DRAFT_CREATED: ("AI draft", "muted", "drafted a client message that is not sent"),
    AuditAction.MESSAGE_DRAFT_EDITED: ("Review", "ok", "edited the text of a client message draft"),
    AuditAction.MESSAGE_DRAFT_SUBMITTED: ("Proposed", "ai", "sent a client message draft for legal review"),
    AuditAction.SEED_LOADED: ("Data import", "warn", "loaded starter data"),
    AuditAction.PROPOSAL_SENT_BACK: ("Review", "warn", "sent a proposal back with a note or a question"),
    AuditAction.STAGE_CHANGED: ("Stage", "ai", "moved the case to another stage"),
}


class AuditDisplay(BaseModel):
    who: str
    label: str
    tone: Tone
    title: str
    note: str


def _initials(actor: str, role: ActorRole) -> str:
    if role == ActorRole.SYSTEM:
        return "SY"
    return f"{role.value[0]}{actor[-1]}"


def describe(entry: AuditEntry) -> AuditDisplay:
    label, tone, phrase = _DISPLAY[entry.action]
    target = " ".join(part for part in (entry.target_type, entry.target_id) if part)
    reason = entry.details.get("reason") or entry.details.get("note")
    if entry.outcome == AuditOutcome.DENIED:
        label, tone = "Refused", "bad"
        title = f"{entry.actor} tried to do this and was refused: {phrase}"
        note = f"{reason or 'Not allowed'}. Nothing changed."
    else:
        title = f"{entry.actor} {phrase}"
        note = str(reason) if reason else target
    return AuditDisplay(who=_initials(entry.actor, entry.actor_role), label=label, tone=tone, title=title, note=note)
