"""Triage of the latest client question. The model only labels the question.

Code verifies the quote, adds keyword rules that can only make the route stricter, and decides the final route.
A failed or disabled model falls back to the keyword rules alone. The reply text is a template, never model text."""

import hashlib
import logging
import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from app.ai.client import STATUS_OK, ClaudeCall, run_prompt
from app.ai.envelope import build_envelope
from app.ai.reader import _db_get_version, normalise
from app.core.config import get_settings

log = logging.getLogger(__name__)

PROMPT_KEY = "client.triage"
MAX_CHARS = 4000


class Intent(StrEnum):
    STATUS_QUESTION = "STATUS_QUESTION"
    DOCUMENT_QUESTION = "DOCUMENT_QUESTION"
    OUTCOME_PREDICTION = "OUTCOME_PREDICTION"
    LEGAL_ADVICE = "LEGAL_ADVICE"
    OTHER_CLIENT_DATA = "OTHER_CLIENT_DATA"
    OTHER = "OTHER"
    NONE = "NONE"


class Route(StrEnum):
    ANSWER = "ANSWER"
    REFUSE_ADVICE = "REFUSE_ADVICE"
    REFUSE_OTHER_CLIENT = "REFUSE_OTHER_CLIENT"
    UNSUPPORTED = "UNSUPPORTED"


# Most sensitive first. A rule hit on one of these always wins over a softer model label.
STRICT = (Intent.OTHER_CLIENT_DATA, Intent.OUTCOME_PREDICTION, Intent.LEGAL_ADVICE)
REASONS: dict[Route, dict[Intent | None, str]] = {
    Route.REFUSE_ADVICE: {
        Intent.OUTCOME_PREDICTION: "This question asks for an outcome prediction. The reply states the status only.",
        Intent.LEGAL_ADVICE: "This question asks for legal advice. The reply states the status only and the attorney will follow up.",
    },
    Route.REFUSE_OTHER_CLIENT: {None: "This question asks about someone else. The reply shares nothing about anyone else."},
    Route.UNSUPPORTED: {None: "The case records cannot answer this question. The reply states the status and routes it to the attorney."},
}

IGNORED = "Instructions inside the message were ignored."
_CASE_ID = re.compile(r"\bCASE-[A-Z0-9]+\b", re.I)
_OTHER_PERSON = re.compile(
    r"\b(another|other|someone else|somebody else|a different)\b[^.?!]{0,40}\b(clients?|cases?|applicants?|persons?|people|passports?|files?)\b"
    r"|\b(client|applicant|person|case)\s+(named|called)\s+[A-Z]",
    re.I,
)
_PREDICTION = re.compile(
    r"\b(approv\w*|guarantee\w*|chances?|odds|likely|likelihood|denied|deny|reject\w*|decision date|outcomes?|win|promise\w*"
    r"|how long (will|does|is)|when will (i|my|the|we)|how soon)\b",
    re.I,
)
_LEGAL = re.compile(
    r"\b(eligible|eligibility|qualify|qualified|legal advice|am i allowed|my rights|appeal|strategy|which visa|best option"
    r"|should i (file|apply|sign|leave|stay)|can i (apply|work|travel|leave))\b",
    re.I,
)
_DOCUMENT = re.compile(r"\b(documents?|upload\w*|still needed|missing|checklist|what do you need|files?)\b", re.I)
_STATUS = re.compile(r"\b(status|update|progress|where is|any news|how is my case)\b", re.I)
_INJECTION = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)|system prompt|you are now|reveal\s+\w*\s*(prompt|instruction|key)"
    r"|override\s+(the\s+)?(rules|instructions)|as an ai",
    re.I,
)
_SENTENCES = re.compile(r"(?<=[.?!])\s+|\n+")


class Question(BaseModel):
    source_id: str
    channel: str
    occurred_at: str
    text: str


class Triage(BaseModel):
    intent: Intent
    question_text: str
    quote: str
    supported: bool
    injection_flag: bool
    origin: str  # MODEL or FALLBACK
    route: Route
    refusal_reason: str | None


_CACHE: dict[str, dict[str, Any]] = {}


def route_of(intent: Intent, supported: bool) -> Route:
    if intent == Intent.OTHER_CLIENT_DATA:
        return Route.REFUSE_OTHER_CLIENT
    if intent in (Intent.OUTCOME_PREDICTION, Intent.LEGAL_ADVICE):
        return Route.REFUSE_ADVICE
    if intent == Intent.NONE or (intent in (Intent.STATUS_QUESTION, Intent.DOCUMENT_QUESTION) and supported):
        return Route.ANSWER
    return Route.UNSUPPORTED


def _build(intent: Intent, text: str, quote: str, supported: bool, injection: bool, origin: str) -> Triage:
    supported = supported and intent in (Intent.STATUS_QUESTION, Intent.DOCUMENT_QUESTION)
    route = route_of(intent, supported)
    reasons = REASONS.get(route, {})
    reason = reasons.get(intent) or reasons.get(None)
    if injection:
        reason = f"{reason or ''} {IGNORED}".strip()
    return Triage(intent=intent, question_text=text, quote=quote, supported=supported, injection_flag=injection,
                  origin=origin, route=route, refusal_reason=reason)  # fmt: skip


def _sentence(message: str, match: re.Match[str] | None) -> str:
    if match is None:
        return ""
    return next((s.strip() for s in _SENTENCES.split(message) if match.group(0) in s), "")


def fallback(message: str, case_id: str, flagged: bool = False) -> Triage:
    """Keyword rules only. The order is the order of sensitivity, so a refusal always wins."""
    injection = flagged or bool(_INJECTION.search(message))
    foreign = next((m for m in _CASE_ID.finditer(message) if m.group(0).upper() != case_id.upper()), None)
    checks: list[tuple[Intent, re.Match[str] | None]] = [
        (Intent.OTHER_CLIENT_DATA, foreign or _OTHER_PERSON.search(message)),
        (Intent.OUTCOME_PREDICTION, _PREDICTION.search(message)),
        (Intent.LEGAL_ADVICE, _LEGAL.search(message)),
        (Intent.DOCUMENT_QUESTION, _DOCUMENT.search(message)),
        (Intent.STATUS_QUESTION, _STATUS.search(message)),
    ]
    for intent, match in checks:
        if match is not None:
            sentence = _sentence(message, match)
            return _build(intent, sentence, sentence, True, injection, "FALLBACK")
    if "?" in message:
        sentence = _sentence(message, re.search(r"[^.?!\n]*\?", message))
        return _build(Intent.OTHER, sentence, sentence, False, injection, "FALLBACK")
    return _build(Intent.NONE, "", "", False, injection, "FALLBACK")


def _valid(data: Mapping[str, Any], message: str) -> bool:
    """The model answer is used only when it has a known intent and its quote is really in the message."""
    try:
        intent = Intent(data.get("intent"))
    except ValueError:
        return False
    if not isinstance(data.get("question_text"), str) or not isinstance(data.get("supported"), bool):
        return False
    quote = str(data.get("quote") or "")
    return intent == Intent.NONE or (bool(normalise(quote)) and normalise(quote) in normalise(message))


def decide(data: Mapping[str, Any] | None, message: str, case_id: str) -> Triage:
    """Final triage. The model label is used when valid, and a stricter rule hit always wins."""
    rules = fallback(message, case_id)
    if data is None or not _valid(data, message):
        return rules
    if data.get("injection_flag"):
        return fallback(message, case_id, flagged=True)  # a flagged message is never trusted, the rules classify it
    intent = Intent(data["intent"])
    if rules.intent in STRICT and (intent not in STRICT or STRICT.index(rules.intent) < STRICT.index(intent)):
        return rules
    return _build(intent, str(data["question_text"]).strip(), str(data["quote"]).strip(), bool(data["supported"]),
                  rules.injection_flag, "MODEL")  # fmt: skip


def _cache_key(version: int, channel: str, message: str) -> str:
    return hashlib.sha256(f"{version}|{channel}|{normalise(message)}".encode()).hexdigest()


def _ask(case_id: str, version: Mapping[str, Any], question: Question, call: ClaudeCall | None) -> dict[str, Any] | None:
    variables = {"channel": question.channel, "message": build_envelope([(1, question.text[:MAX_CHARS])])}
    result = call(version, variables) if call else run_prompt(PROMPT_KEY, version, variables, input_text=question.text, case_id=case_id)
    return result.data if result.status == STATUS_OK else None


def classify(case_id: str, question: Question, call: ClaudeCall | None = None) -> Triage:
    """Triage one client message. Never raises. Results are cached by the message hash and the prompt version."""
    message = question.text[:MAX_CHARS]
    settings = get_settings()
    version = _db_get_version(PROMPT_KEY) if settings.auto_read and settings.anthropic_api_key else None
    if version is None:
        return fallback(message, case_id)
    key = _cache_key(version["version"], question.channel, message)
    data = _CACHE.get(key)
    if data is None:
        try:
            data = _ask(case_id, version, question, call)
        except Exception:
            log.exception("Could not triage the message %s", question.source_id)
            data = None
        if data is not None:
            _CACHE[key] = data
    return decide(data, message, case_id)
