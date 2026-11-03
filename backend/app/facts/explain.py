"""The Consistency Agent. It explains a conflict in plain words and never picks a winner.

Code checks every id the model cites, drops what is not a source of that conflict, caches the result and
falls back to a fixed sentence when the model is off, fails or says something it should not."""

import hashlib
import json
import logging
import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from app.ai.client import STATUS_OK, ClaudeCall, run_prompt
from app.ai.envelope import build_envelope
from app.ai.reader import _db_get_version
from app.core.config import get_settings
from app.core.dates import us_text
from app.facts.engine import CONFLICT, FieldState

log = logging.getLogger(__name__)

PROMPT_KEY = "case.consistency"
_ID = re.compile(r"\b(?:UP-\d+|Z-\d+|MSG-[\d-]+|PROFILE-[\w-]+|EV-[\w-]+)")
# Words that would pick a winner or give advice. Such text is replaced by the fixed sentence.
_VERDICT = re.compile(r"\b(more likely|most likely|more reliable|should use|should be|is correct|is the correct|probably|winner)\b", re.I)
_CACHE: dict[str, "Explanation"] = {}


class Explanation(BaseModel):
    field: str
    text: str
    cited_source_ids: list[str]
    origin: str  # MODEL or FALLBACK


def fallback(state: FieldState) -> Explanation:
    """The fixed sentence. Sources with the same value are named together."""
    by_value: dict[str, list[str]] = {}
    for s in state.sources:
        by_value.setdefault(s.value, []).append(s.source_id)
    said = ", ".join(f'{" and ".join(ids)} says "{us_text(v)}"' if len(ids) == 1 else f'{" and ".join(ids)} say "{us_text(v)}"' for v, ids in by_value.items())
    head = "The sources disagree" if state.state == CONFLICT else (
        "Only the case profile and unchecked claims exist" if any(s.source_kind == "PROFILE" for s in state.sources) else "Only unchecked claims exist")
    held = any(s.source_kind == "DOCUMENT" for s in state.sources)
    tail = "" if state.state == CONFLICT else (
        ". A document is held for review" if held else ". A document is needed" if state.document_source else ". A person must confirm it")
    return Explanation(field=state.field, text=f"{head} on {state.label.lower()}: {said}{tail}.",
                       cited_source_ids=[s.source_id for s in state.sources], origin="FALLBACK")  # fmt: skip


def content_hash(state: FieldState, version: int) -> str:
    rows = sorted((s.source_id, s.trust, s.value) for s in state.sources)
    return hashlib.sha256(json.dumps([state.field, rows, version]).encode()).hexdigest()


def _block(state: FieldState) -> str:
    sources = [{"source_id": s.source_id, "trust": s.trust, "value": s.value, "quote": s.quote} for s in state.sources]
    return json.dumps({"field": state.field, "label": state.label, "sources": sources}, ensure_ascii=False)


def checked(state: FieldState, item: Mapping[str, Any]) -> Explanation | None:
    """The model answer for one conflict, or None when it cites something foreign or picks a side."""
    allowed = {s.source_id for s in state.sources}
    body = str(item.get("explanation") or "").strip()
    cited = [i for i in item.get("cited_source_ids") or [] if i in allowed]
    if not body or not cited or _VERDICT.search(body) or any(i not in allowed for i in _ID.findall(body)):
        return None
    return Explanation(field=state.field, text=us_text(body), cited_source_ids=cited, origin="MODEL")


def _ask(case_id: str, version: Mapping[str, Any], pending: list[FieldState], call: ClaudeCall | None) -> dict[str, Any]:
    pages = [(i, _block(s)) for i, s in enumerate(pending, 1)]
    variables = {"conflicts": build_envelope(pages)}
    text = "\n".join(t for _, t in pages)
    result = call(version, variables) if call else run_prompt(PROMPT_KEY, version, variables, input_text=text, case_id=case_id)
    if result.status != STATUS_OK or result.data is None or result.data.get("injection_flag"):
        return {}
    return {str(e.get("field")): e for e in result.data.get("explanations") or [] if isinstance(e, dict)}


def explain(case_id: str, states: list[FieldState], call: ClaudeCall | None = None) -> dict[str, Explanation]:
    """One explanation for each field in a CONFLICT and a fixed sentence for the other fields given. Never raises."""
    wanted = [s for s in states if s.sources]
    result = {s.field: fallback(s) for s in wanted}
    conflicts = [s for s in wanted if s.state == CONFLICT]
    settings = get_settings()
    version = _db_get_version(PROMPT_KEY) if conflicts and settings.auto_read and settings.anthropic_api_key else None
    if version is None:
        return result
    keys = {s.field: content_hash(s, version["version"]) for s in conflicts}
    pending = [s for s in conflicts if keys[s.field] not in _CACHE]
    try:
        answers = _ask(case_id, version, pending, call) if pending else {}
    except Exception:
        log.exception("Could not explain the conflicts of %s", case_id)
        answers = {}
    for s in pending:
        if (found := checked(s, answers[s.field]) if s.field in answers else None) is not None:
            _CACHE[keys[s.field]] = found
    for s in conflicts:
        result[s.field] = _CACHE.get(keys[s.field], result[s.field])
    return result
