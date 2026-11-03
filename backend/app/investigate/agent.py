"""The investigation agent. One question about one case, read only tools, cited answer.

The model may call the read tools in a bounded loop. Code then checks every citation and every date or name verdict.
When the model is off, fails or cannot be trusted, the answer is built from the checklist, conflicts and exceptions alone.
"""

import json
import logging
import time
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from app.ai.client import input_hash
from app.ai.envelope import wrap_untrusted
from app.ai.models import PromptRun
from app.ai.reader import _db_get_version
from app.ai.registry import render_template
from app.cases import repository
from app.cases.repository import CaseRecord
from app.core import audit
from app.core.config import get_settings
from app.core.contracts import AuditAction
from app.core.security import Actor
from app.db.session import SessionLocal
from app.investigate import answer
from app.investigate.tools import TOOL_SPECS, Toolbox
from app.replies import triage
from app.validation.reasons import us_date

log = logging.getLogger(__name__)

PROMPT_KEY = "case.investigate"
DEFAULT_QUESTION = "Why is this case blocked?"
MAX_QUESTION_CHARS = 300
MAX_ROUNDS = 6
MAX_TOTAL_TOKENS = 80000
FINAL_REQUEST = (
    "Write your final answer as JSON in the output schema. Write the summary and every reason as full sentences "
    "from the case records, and cite tool result ids such as T1."
)
REFUSE_ROUTES = (triage.Route.REFUSE_ADVICE, triage.Route.REFUSE_OTHER_CLIENT)


class Transcript:
    """What one model conversation used, kept for the run history."""

    def __init__(self) -> None:
        self.tokens_in = self.tokens_out = 0
        self.stop_reason: str | None = None
        self.raw: str | None = None

    @property
    def total(self) -> int:
        return self.tokens_in + self.tokens_out


def _block(item: Any) -> dict[str, Any]:
    if item.type == "tool_use":
        return {"type": "tool_use", "id": item.id, "name": item.name, "input": item.input}
    if item.type == "text":
        return {"type": "text", "text": item.text}
    return item.model_dump(exclude_none=True)  # a thinking block goes back unchanged


def _tool_results(box: Toolbox, uses: list[Any], sent: set[str]) -> list[dict[str, Any]]:
    blocks = []
    for use in uses:
        result = box.call(use.name, dict(use.input or {}))
        if result.id in sent:
            content = f"This call was already made. See result {result.id} above."
        else:
            body = json.dumps(result.data, ensure_ascii=False, default=str)
            content = body if result.is_compare else wrap_untrusted(body, None)
            sent.add(result.id)
        blocks.append({"type": "tool_result", "tool_use_id": use.id, "content": content, "is_error": result.error})
    return blocks


def _refused(use: Any) -> dict[str, Any]:
    return {"type": "tool_result", "tool_use_id": use.id, "content": "Tool limit reached. Answer now from the results you have.", "is_error": True}


def _parse(message: Any, seen: Transcript) -> dict[str, Any] | None:
    text = next((b.text for b in message.content if b.type == "text"), None)
    seen.raw = text
    try:
        data = json.loads(text or "")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _create(api: Any, version: dict[str, Any], system: str, messages: list[dict[str, Any]], extra: dict[str, Any]) -> Any:
    return api.messages.create(
        model=version["model"], max_tokens=version["max_tokens"], system=system, messages=messages, tools=TOOL_SPECS,
        output_config={"effort": version["effort"], **extra}
    )  # fmt: skip


def _count(message: Any, seen: Transcript) -> None:
    seen.tokens_in += getattr(message.usage, "input_tokens", 0)
    seen.tokens_out += getattr(message.usage, "output_tokens", 0)
    seen.stop_reason = message.stop_reason


def _converse(api: Any, version: dict[str, Any], system: str, user: str, box: Toolbox, seen: Transcript) -> dict[str, Any] | None:
    """The final JSON of the model, or None when it refused or sent bad JSON. At the round or token cap no more tool runs.

    The tool rounds run without the output format, because a schema on every turn makes the model write placeholder JSON
    next to its tool calls. When it stops calling tools, one last call asks for the answer in the registry schema.
    """
    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    sent: set[str] = set()
    for round_no in range(MAX_ROUNDS + 1):
        message = _create(api, version, system, messages, {})
        _count(message, seen)
        if message.stop_reason in ("refusal", "max_tokens"):
            return None
        uses = [b for b in message.content if b.type == "tool_use"]
        messages.append({"role": "assistant", "content": [_block(b) for b in message.content]})
        if not uses:
            break
        if round_no == MAX_ROUNDS or seen.total > MAX_TOTAL_TOKENS:
            messages.append({"role": "user", "content": [_refused(use) for use in uses]})
            break
        messages.append({"role": "user", "content": _tool_results(box, uses, sent)})
    messages.append({"role": "user", "content": FINAL_REQUEST})
    last = api.messages.create(
        model=version["model"], max_tokens=version["max_tokens"], system=system, messages=messages, tools=TOOL_SPECS,
        tool_choice={"type": "none"},
        output_config={"effort": version["effort"], "format": {"type": "json_schema", "schema": version["output_schema"]}},
    )  # fmt: skip
    _count(last, seen)
    return None if last.stop_reason in ("refusal", "max_tokens") else _parse(last, seen)


def _save_run(case_id: str, version: dict[str, Any], system: str, user: str, seen: Transcript, status: str, started: float) -> int:
    row = PromptRun(
        prompt_key=PROMPT_KEY, version=version["version"], model=version["model"], case_id=case_id, input_hash=input_hash(system, user, version["model"], version["version"]),
        tokens_in=seen.tokens_in, tokens_out=seen.tokens_out, latency_ms=int((time.monotonic() - started) * 1000),
        stop_reason=seen.stop_reason, status=status,
    )  # fmt: skip
    if get_settings().ai_run_capture == "full":
        row.rendered_prompt, row.raw_output = f"{system}\n\n{user}", seen.raw
    with SessionLocal() as session:
        session.add(row)
        session.commit()
        return row.id


def _ask_model(
    db: Session, actor: Actor, case: CaseRecord, question: str, as_of: Any, api: Any
) -> tuple[answer.InvestigationOut | None, int | None, int]:
    """The checked model answer, the run id and the number of tool calls. None when the model cannot be used."""
    settings = get_settings()
    version = _db_get_version(PROMPT_KEY) if (api or settings.anthropic_api_key) else None
    if version is None:
        return None, None, 0
    variables = {"case_id": case.case_id, "review_date": us_date(as_of), "question": wrap_untrusted(question, None)}
    system, user = render_template(version["system_text"], variables), render_template(version["user_template"], variables)
    box, seen, started, data = Toolbox(db, case.case_id, actor, as_of), Transcript(), time.monotonic(), None
    try:
        client = api or anthropic.Anthropic(api_key=settings.anthropic_api_key or None, timeout=settings.ai_timeout_seconds)
        data = _converse(client, version, system, user, box, seen)
    except Exception:
        log.exception("The investigation model failed for %s", case.case_id)
    checked = answer.verify(data, box.results) if data else None
    run_id = _save_run(case.case_id, version, system, user, seen, "ok" if checked else "needs_review", started)
    if checked is None:
        return None, run_id, len(box.results)
    summary, reasons, dropped = checked
    out = answer.InvestigationOut(question=question, answer=summary, reasons=reasons, trace=answer.trace_of(box), origin="MODEL", dropped=dropped,
                                 injection_flagged=bool(data and data.get("injection_flag")))
    return out, run_id, len(box.results)


def investigate(db: Session, actor: Actor, case: CaseRecord, question: str | None, api: Any = None) -> answer.InvestigationOut:
    """Explain why the case is blocked. Never raises for a model problem and never writes except one audit line."""
    asked = (question or "").strip()[:MAX_QUESTION_CHARS] or DEFAULT_QUESTION
    as_of = repository.get_as_of(db)
    verdict = triage.fallback(asked, case.case_id)
    run_id, calls = None, 0
    if verdict.route in REFUSE_ROUTES:
        out = answer.InvestigationOut(question=asked, answer=answer.REFUSED, reasons=[], trace=[], origin="REFUSED")
    else:
        found, run_id, calls = _ask_model(db, actor, case, asked, as_of, api)
        out = found or answer.fallback(Toolbox(db, case.case_id, actor, as_of), asked)
    evidence = sorted({s for r in out.reasons for s in r.source_ids})
    audit.record(
        db, actor=actor, action=AuditAction.CHAT_QUESTION, case_id=case.case_id, target_type="investigation", target_id=case.case_id,
        evidence_ids=evidence, prompt_run_id=run_id,
        details={"origin": out.origin, "tool_calls": calls, "reasons": len(out.reasons), "dropped": out.dropped, "injection_flagged": out.injection_flagged},
    )  # fmt: skip
    return out
