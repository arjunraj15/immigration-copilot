"""Client message drafts of one case. Drafts are never sent. Rules live in app.replies."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.cases import proposals
from app.cases.access import AccessibleCase
from app.cases.repository import CaseRecord
from app.core.contracts import ActorRole, AuditAction
from app.core.errors import AppError
from app.core.security import Actor, get_actor
from app.db.session import get_db, transaction
from app.facts import engine
from app.replies import service
from app.replies.service import Draft
from app.replies.triage import Question, Triage

router = APIRouter(prefix="/api/cases", tags=["replies"])

Db = Annotated[Session, Depends(get_db)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


class ReplyDraftOut(BaseModel):
    question: Question | None
    triage: Triage | None
    draft: Draft | None
    refused: bool
    refusal_reason: str | None
    needs_legal_review: bool = True


class MissingFieldsOut(BaseModel):
    items: list[str]
    draft: Draft | None
    needs_legal_review: bool = True


class EditIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class SubmitOut(BaseModel):
    draft: Draft
    proposal: proposals.Proposal


def _reply_out(question: Question | None, draft: Draft | None) -> ReplyDraftOut:
    result = Triage.model_validate(draft.triage) if draft and draft.triage else None
    refused = result is not None and result.route.value != "ANSWER"
    return ReplyDraftOut(question=question, triage=result, draft=draft, refused=refused,
                         refusal_reason=result.refusal_reason if result else None)  # fmt: skip


def _reply(db: Session, case: CaseRecord, actor: Actor, question: Question, regenerate: bool) -> Draft | None:
    """The current draft for this question. OPS builds it when it is missing or when a new one is asked for."""
    current = service.current_draft(db, case.case_id, service.REPLY, question.source_id)
    if (current and not regenerate) or actor.role != ActorRole.OPS:
        return current
    with transaction(db):
        saved = service.save(db, actor, case, service.build_reply(db, case, question), reply_to=question.source_id, regenerate=regenerate)
    return saved


@router.get("/{case_id}/reply-draft")
def get_reply_draft(case: AccessibleCase, db: Db, actor: CurrentActor) -> ReplyDraftOut:
    """The draft for the latest client question. The assigned OPS user builds it on first read, the reviewer only reads it."""
    question = service.latest_question(db, case.case_id)
    if question is None:
        return _reply_out(None, None)
    return _reply_out(question, _reply(db, case, actor, question, False))


@router.post("/{case_id}/reply-draft")
def regenerate_reply_draft(case: AccessibleCase, db: Db, actor: CurrentActor) -> ReplyDraftOut:
    """Only the assigned OPS user. An open draft is rewritten from the records, a draft in review is refused."""
    service.require_ops(actor, case, AuditAction.MESSAGE_DRAFT_CREATED)
    question = service.latest_question(db, case.case_id)
    if question is None:
        raise AppError("NO_CLIENT_QUESTION", "No client question is waiting", 409)
    return _reply_out(question, _reply(db, case, actor, question, True))


@router.patch("/{case_id}/reply-draft/{draft_id}")
def edit_draft(draft_id: str, body: EditIn, case: AccessibleCase, db: Db, actor: CurrentActor) -> Draft:
    """Text only, and only while the draft is still a draft. Every edit is audited."""
    with transaction(db):
        edited = service.edit(db, actor, case, draft_id, body.body)
    return edited


@router.post("/{case_id}/reply-draft/{draft_id}/submit")
def submit_draft(draft_id: str, case: AccessibleCase, db: Db, actor: CurrentActor) -> SubmitOut:
    """Sends the draft to the assigned legal reviewer as a message approval. Nothing is sent to the client."""
    with transaction(db):
        draft, proposal = service.submit(db, actor, case, draft_id)
    return SubmitOut(draft=draft, proposal=proposal)


@router.get("/{case_id}/missing-fields-draft")
def get_missing_fields(case: AccessibleCase, db: Db) -> MissingFieldsOut:
    """What the firm still needs from the client, read only, and the email draft if one exists."""
    built = service.build_missing(db, case, engine.compute_states(db, case.case_id))
    return MissingFieldsOut(items=built.asks, draft=service.current_draft(db, case.case_id, service.MISSING, None))


@router.post("/{case_id}/missing-fields-draft")
def create_missing_fields(case: AccessibleCase, db: Db, actor: CurrentActor) -> MissingFieldsOut:
    """Only the assigned OPS user. Writes the email draft, or rewrites the open one."""
    service.require_ops(actor, case, AuditAction.MESSAGE_DRAFT_CREATED)
    built = service.build_missing(db, case, engine.read(db, case.case_id))
    if not built.asks:
        raise AppError("NOTHING_TO_ASK", "Nothing is missing, so there is no email to draft", 409)
    with transaction(db):
        saved = service.save(db, actor, case, built, reply_to=None, regenerate=True)
    return MissingFieldsOut(items=built.asks, draft=saved)
