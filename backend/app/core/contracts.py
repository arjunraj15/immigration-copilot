"""Shared models passed between tracks. Values and meanings are documented in docs/schema.md."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ActorRole(StrEnum):
    OPS = "OPS"
    LEGAL = "LEGAL"
    SYSTEM = "SYSTEM"


class AuditOutcome(StrEnum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    SYSTEM = "SYSTEM"


class AuditAction(StrEnum):
    """Every action the ledger accepts. Add a value here when a phase starts auditing a new event."""

    UPLOAD_RECEIVED = "UPLOAD_RECEIVED"
    UPLOAD_DELETED = "UPLOAD_DELETED"
    DUPLICATE_DETECTED = "DUPLICATE_DETECTED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"
    DOCUMENT_READ = "DOCUMENT_READ"
    DOCUMENT_TYPE_SET = "DOCUMENT_TYPE_SET"
    DOCUMENT_TYPE_CREATED = "DOCUMENT_TYPE_CREATED"
    FORM_FIELD_ADDED = "FORM_FIELD_ADDED"
    QUARANTINED = "QUARANTINED"
    INJECTION_FLAGGED = "INJECTION_FLAGGED"
    FACT_WRITTEN = "FACT_WRITTEN"
    CONFLICT_OPENED = "CONFLICT_OPENED"
    CONFLICT_RESOLVED = "CONFLICT_RESOLVED"
    CONFLICT_SUGGESTED = "CONFLICT_SUGGESTED"
    PROFILE_CONFIRMED = "PROFILE_CONFIRMED"
    REVIEW_REQUESTED = "REVIEW_REQUESTED"
    CASE_CREATED = "CASE_CREATED"
    CASE_DRAFT_CREATED = "CASE_DRAFT_CREATED"
    CASE_DRAFT_DISCARDED = "CASE_DRAFT_DISCARDED"
    CASE_DELETED = "CASE_DELETED"
    CASE_ACCESS = "CASE_ACCESS"
    ANALYSIS_RUN = "ANALYSIS_RUN"
    AI_DRAFT = "AI_DRAFT"
    PROPOSE = "PROPOSE"
    REVIEW_APPROVE = "REVIEW_APPROVE"
    REVIEW_REJECT = "REVIEW_REJECT"
    COMMIT = "COMMIT"
    FORM_EXPORTED = "FORM_EXPORTED"
    SUBMITTED_FOR_REVIEW = "SUBMITTED_FOR_REVIEW"
    INFO_REQUESTED = "INFO_REQUESTED"
    RERUN_SKIPPED_PRIOR_REJECTION = "RERUN_SKIPPED_PRIOR_REJECTION"
    PROMPT_VERSION_CREATED = "PROMPT_VERSION_CREATED"
    PROMPT_VERSION_ACTIVATED = "PROMPT_VERSION_ACTIVATED"
    PROPOSAL_SENT_BACK = "PROPOSAL_SENT_BACK"
    STAGE_CHANGED = "STAGE_CHANGED"
    CHAT_QUESTION = "CHAT_QUESTION"
    CHAIN_VERIFIED = "CHAIN_VERIFIED"
    MESSAGE_DRAFT_CREATED = "MESSAGE_DRAFT_CREATED"
    MESSAGE_DRAFT_EDITED = "MESSAGE_DRAFT_EDITED"
    MESSAGE_DRAFT_SUBMITTED = "MESSAGE_DRAFT_SUBMITTED"
    SEED_LOADED = "SEED_LOADED"
    DATA_IMPORTED = "DATA_IMPORTED"


class SourceKind(StrEnum):
    EVIDENCE = "EVIDENCE"
    CLAIM = "CLAIM"


class SourceType(StrEnum):
    DOCUMENT = "DOCUMENT"
    PROFILE = "PROFILE"
    PORTAL_EVENT = "PORTAL_EVENT"
    CALENDAR_EVENT = "CALENDAR_EVENT"
    INTAKE_NOTE = "INTAKE_NOTE"
    MESSAGE = "MESSAGE"
    ASSERTION = "ASSERTION"


class UploadOutcome(StrEnum):
    PENDING = "PENDING"
    READING = "READING"
    DUPLICATE = "DUPLICATE"
    QUARANTINED = "QUARANTINED"
    SUPERSEDED = "SUPERSEDED"
    INVALID = "INVALID"
    USABLE = "USABLE"
    CLAIM_SOURCE = "CLAIM_SOURCE"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class Verification(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"


class ConflictStatus(StrEnum):
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"


class ProposalKind(StrEnum):
    DEADLINE_ACTIVATE = "DEADLINE_ACTIVATE"
    FORM_EXPORT = "FORM_EXPORT"
    PACKET_APPROVE = "PACKET_APPROVE"
    MESSAGE_APPROVE = "MESSAGE_APPROVE"
    STAGE_CHANGE = "STAGE_CHANGE"


class ProposalStatus(StrEnum):
    PENDING_LEGAL_REVIEW = "PENDING_LEGAL_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMMITTED = "COMMITTED"
    SENT_BACK = "SENT_BACK"


class ReviewChoice(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class Citation(BaseModel):
    source_type: SourceType
    source_id: str
    page: int | None = None
    quote: str | None = None


class InjectionFlag(BaseModel):
    quote: str
    page: int | None
    reason: str


class ReadStatus(StrEnum):
    READ = "READ"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ReadItem(BaseModel):
    """One row of an array field. It carries its own quote and page, checked on its own."""

    values: dict[str, str | None] = Field(default_factory=dict)
    quote: str
    page: int
    verified: bool = True
    from_image: bool = False


class ReadField(BaseModel):
    """One extracted value. verified is true only when the quote was found in the page text.

    An array field has value None, its rows in items, and no quote of its own. Its verified is true
    only when every item is verified. An empty array is verified. Scalar fields leave items None.
    """

    value: str | None = None
    quote: str = ""
    page: int = 0
    verified: bool = True
    items: list[ReadItem] | None = None
    from_image: bool = False


class DocumentRead(BaseModel):
    """Output of ai.read_document. Fact creation stays with the Core track."""

    category: str
    language: str | None = None
    legible: bool = True
    injection_flag: bool = False
    fields: dict[str, ReadField] = Field(default_factory=dict)
    prompt_run_id: int | None = None
    status: ReadStatus = ReadStatus.READ
    image_pages: list[int] = Field(default_factory=list)
    image_owner_names: list[str] = Field(default_factory=list)


class Fact(BaseModel):
    case_id: str
    field_name: str
    value: str
    normalized_value: str
    source_kind: SourceKind
    citation: Citation
    verification: Verification
    observed_at: datetime | None = None


class Conflict(BaseModel):
    case_id: str
    field_name: str
    status: ConflictStatus
    facts: list[Fact]
    explanation: str | None = None
    review_request_id: int | None = None


class ProposalCreate(BaseModel):
    case_id: str
    kind: ProposalKind
    idempotency_key: str = Field(min_length=8, max_length=200)
    target_type: str
    target_id: str
    value: dict[str, Any]
    evidence_ids: list[str] = Field(min_length=1)


class ProposalReview(BaseModel):
    choice: ReviewChoice
    reason: str | None = None


class Proposal(BaseModel):
    proposal_id: str
    case_id: str
    kind: ProposalKind
    status: ProposalStatus
    idempotency_key: str
    target_type: str
    target_id: str
    value: dict[str, Any]
    evidence_ids: list[str]
    proposed_by: str
    reviewed_by: str | None = None
    review_reason: str | None = None
    committed_by: str | None = None
    replayed: bool = False


class DeadlineValue(BaseModel):
    """The value of a DEADLINE_ACTIVATE proposal. Code recomputes due_date before accepting it."""

    due_date: date
    rule_version: str
    trigger_event_id: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorBody(BaseModel):
    error: ErrorDetail
