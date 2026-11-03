"""Claude call wrapper. Structured outputs, explicit effort, stop_reason check, run history.

Tools are optional and read only: a DocTools box of date helpers. A call without tools sends none. No forced tool
choice, no prefill and no sampling parameters. Model, effort and token limits always come from the prompt version row.
"""

import base64
import hashlib
import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from app.ai.doc_tools import DocTools
from app.ai.models import PromptRun
from app.ai.registry import render_template
from app.ai.trace import pack
from app.core.config import get_settings
from app.db.session import SessionLocal

STATUS_OK = "ok"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_ERROR = "error"

_TRANSIENT = (
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)
_MAX_ATTEMPTS = 3
MAX_TOOL_ROUNDS = 4
FINAL_REQUEST = "Write your final answer as JSON in the output schema."
_BACKOFF_SECONDS = 1.0


@dataclass
class CallResult:
    status: str
    data: dict[str, Any] | None
    run_id: int | None
    stop_reason: str | None = None


# (version_row, variables) -> CallResult. Tests replace this with a fake.
ClaudeCall = Callable[[Mapping[str, Any], Mapping[str, Any]], CallResult]


def input_hash(system: str, user: str, model: str, version: int) -> str:
    raw = json.dumps([system, user, model, version], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _content(user: str, images: Sequence[tuple[int, bytes]]) -> Any:
    """Plain text, or the text followed by each scanned page image as a base64 PNG block."""
    if not images:
        return user
    blocks: list[dict[str, Any]] = [{"type": "text", "text": user}]
    for page, png in images:
        blocks.append({"type": "text", "text": f"Image of page {page}:"})
        data = base64.b64encode(png).decode("ascii")
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}})
    return blocks


def _create_message(api: Any, version: Mapping[str, Any], system: str, user: str,
                    images: Sequence[tuple[int, bytes]] = ()) -> Any:  # fmt: skip
    return api.messages.create(
        model=version["model"],
        max_tokens=version["max_tokens"],
        system=system,
        messages=[{"role": "user", "content": _content(user, images)}],
        output_config={
            "effort": version["effort"],
            "format": {"type": "json_schema", "schema": version["output_schema"]},
        },
    )


def _send_with_retry(api: Any, version: Mapping[str, Any], system: str, user: str,
                     images: Sequence[tuple[int, bytes]] = (), tools: DocTools | None = None,
                     trace: list[dict[str, Any]] | None = None) -> Any:  # fmt: skip
    trace = [] if trace is None else trace
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        trace.clear()
        try:
            if tools is not None:
                return _converse(api, version, system, user, images, tools, trace)
            message = _create_message(api, version, system, user, images)
            _note(trace, message)
            return message, None, None
        except _TRANSIENT:
            if attempt == _MAX_ATTEMPTS:
                raise
            time.sleep(_BACKOFF_SECONDS * 2 ** (attempt - 1))
    raise AssertionError("unreachable")


def _block(item: Any) -> dict[str, Any]:
    if item.type == "tool_use":
        return {"type": "tool_use", "id": item.id, "name": item.name, "input": item.input}
    if item.type == "text":
        return {"type": "text", "text": item.text}
    return item.model_dump(exclude_none=True)  # a thinking block goes back unchanged


def _note(trace: list[dict[str, Any]], message: Any) -> None:
    """One model call for the trace: why it stopped, its tokens and what it said or asked for."""
    usage = getattr(message, "usage", None)
    trace.append({
        "stop_reason": message.stop_reason,
        "tokens_in": getattr(usage, "input_tokens", None),
        "tokens_out": getattr(usage, "output_tokens", None),
        "content": [_block(b) if hasattr(b, "model_dump") or b.type in ("tool_use", "text") else {"type": b.type} for b in message.content],
    })  # fmt: skip


def _tool_results(tools: DocTools, uses: list[Any]) -> list[dict[str, Any]]:
    blocks = []
    for use in uses:
        data, error = tools.call(use.name, dict(use.input or {}))
        blocks.append({"type": "tool_result", "tool_use_id": use.id, "content": json.dumps(data, ensure_ascii=False), "is_error": error})
    return blocks


def _converse(api: Any, version: Mapping[str, Any], system: str, user: str, images: Sequence[tuple[int, bytes]],
              tools: DocTools, trace: list[dict[str, Any]]) -> tuple[Any, int, int]:
    """Run the tool rounds, then ask for the answer in the registry schema. Returns the last message and token totals.

    The rounds go without the output format, because a schema on every turn makes the model write placeholder JSON beside
    its tool calls, and a schema on a read can make it return empty fields it had just read. A first answer that needs no
    tools and is a JSON object is final, a single call. Otherwise a last call turns tools off so it can only answer.
    """
    messages: list[dict[str, Any]] = [{"role": "user", "content": _content(user, images)}]
    base = {"model": version["model"], "max_tokens": version["max_tokens"], "system": system, "tools": tools.specs}
    used = [0, 0]

    def send(**extra: Any) -> Any:
        message = api.messages.create(**base, messages=messages, **extra)
        used[0] += getattr(message.usage, "input_tokens", 0)
        used[1] += getattr(message.usage, "output_tokens", 0)
        _note(trace, message)
        return message

    schema = {"type": "json_schema", "schema": version["output_schema"]}
    for round_no in range(MAX_TOOL_ROUNDS + 1):
        message = send(output_config={"effort": version["effort"]})
        uses = [b for b in message.content if b.type == "tool_use"]
        if message.stop_reason in ("refusal", "max_tokens"):
            return message, used[0], used[1]
        messages.append({"role": "assistant", "content": [_block(b) for b in message.content]})
        if not uses:
            if round_no == 0 and _is_json_object(_first_text(message)) and _fields_fit(_first_text(message), version["output_schema"]):
                return message, used[0], used[1]
            break
        if round_no == MAX_TOOL_ROUNDS:
            limit = "Tool limit reached. Answer now from what you have."
            results = [{"type": "tool_result", "tool_use_id": u.id, "content": limit, "is_error": True} for u in uses]
        else:
            results = _tool_results(tools, uses)
        messages.append({"role": "user", "content": results})
        trace.append({"tool_results": results})
        if round_no == MAX_TOOL_ROUNDS:
            break
    messages.append({"role": "user", "content": FINAL_REQUEST})
    final = send(tool_choice={"type": "none"}, output_config={"effort": version["effort"], "format": schema})
    return final, used[0], used[1]


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _parse_json(raw: str | None) -> Any:
    """json.loads that also takes an answer wrapped in a markdown code fence. Raises ValueError otherwise."""
    fenced = _FENCE.match(raw or "")
    return json.loads(fenced.group(1) if fenced else (raw or ""))


def _allowed_fields(schema: Mapping[str, Any]) -> Mapping[str, Any] | None:
    return ((schema.get("properties") or {}).get("fields") or {}).get("properties")


def _full_keys(fields: Mapping[str, Any], allowed: Mapping[str, Any]) -> dict[str, str] | None:
    """Each answer key mapped to its schema key. A first answer written without the schema can shorten a key, such as
    Last Recorded Entry for ARRIVAL_RECORD.Last Recorded Entry. A short key that names exactly one schema key is mapped to
    it. None when any key names no schema key or more than one."""
    mapping = {}
    for key in fields:
        found = [key] if key in allowed else [a for a in allowed if a.split(".", 1)[-1] == key]
        if len(found) != 1:
            return None
        mapping[key] = found[0]
    return mapping if len(set(mapping.values())) == len(mapping) else None


def _fields_fit(raw: str | None, schema: Mapping[str, Any]) -> bool:
    """True when every field key of the answer is a schema key or a short key that names exactly one."""
    allowed = _allowed_fields(schema)
    if not allowed:
        return True
    try:
        fields = _parse_json(raw).get("fields")
    except (ValueError, AttributeError):
        return False
    return isinstance(fields, dict) and _full_keys(fields, allowed) is not None


def _with_full_keys(data: dict[str, Any], schema: Mapping[str, Any]) -> dict[str, Any]:
    """The answer with every short field key replaced by its schema key. Unchanged when a key cannot be mapped."""
    allowed, fields = _allowed_fields(schema), data.get("fields")
    if not allowed or not isinstance(fields, dict):
        return data
    mapping = _full_keys(fields, allowed)
    return data if mapping is None else {**data, "fields": {mapping[k]: v for k, v in fields.items()}}


def _is_json_object(raw: str | None) -> bool:
    try:
        return isinstance(_parse_json(raw), dict)
    except ValueError:
        return False


def _first_text(message: Any) -> str | None:
    blocks = [b for b in message.content if getattr(b, "type", None) == "text"]
    return blocks[0].text if blocks else None


def _interpret(message: Any) -> tuple[str, dict[str, Any] | None, str | None]:
    """Return (status, parsed data, raw text). Content is parsed only after stop_reason is ok."""
    if message.stop_reason in ("refusal", "max_tokens"):
        return STATUS_NEEDS_REVIEW, None, None
    raw = _first_text(message)
    if raw is None:
        return STATUS_NEEDS_REVIEW, None, None
    try:
        data = _parse_json(raw)
    except ValueError:
        return STATUS_NEEDS_REVIEW, None, raw
    if not isinstance(data, dict):
        return STATUS_NEEDS_REVIEW, None, raw
    return STATUS_OK, data, raw


def _save_run(
    session_factory: Callable[[], Session],
    row: dict[str, Any],
    capture: dict[str, Any],
) -> int:
    if get_settings().ai_run_capture == "full":
        row.update(capture)
    with session_factory() as db:
        run = PromptRun(**row)
        db.add(run)
        db.commit()
        return run.id


def run_prompt(
    prompt_key: str,
    version: Mapping[str, Any],
    variables: Mapping[str, Any],
    *,
    input_text: str = "",
    case_id: str | None = None,
    tools: DocTools | None = None,
    api: Any = None,
    session_factory: Callable[[], Session] = SessionLocal,
) -> CallResult:
    """Render the version, call Claude once (retrying transient errors) and record a run.

    version needs: version, model, effort, max_tokens, system_text, user_template, output_schema.
    input_text is the document text sent, kept only when capture is full.
    variables may hold images, a list of (page, png bytes) sent after the text. They are untrusted data too.
    case_id ties the run to a case so the history can be read per case.
    tools lets the model call the read only date helpers. Token counts then cover every round.
    """
    system = render_template(version["system_text"], variables)
    user = render_template(version["user_template"], variables)
    images: list[tuple[int, bytes]] = list(variables.get("images") or [])
    image_digest = "".join(hashlib.sha256(png).hexdigest() for _, png in images)
    row: dict[str, Any] = {
        "prompt_key": prompt_key,
        "version": version["version"],
        "model": version["model"],
        "case_id": case_id,
        "input_hash": input_hash(system, user + image_digest, version["model"], version["version"]),
    }
    capture: dict[str, Any] = {
        "rendered_prompt": f"{system}\n\n{user}",
        "input_text": input_text,
        "raw_output": None,
        "trace": None,
    }
    trace: list[dict[str, Any]] = []
    api = api or anthropic.Anthropic(
        api_key=get_settings().anthropic_api_key or None, max_retries=0
    )
    started = time.monotonic()
    status, data, stop, usage, tokens = STATUS_ERROR, None, None, None, (None, None)
    try:
        message, total_in, total_out = _send_with_retry(api, version, system, user, images, tools, trace)
        status, data, capture["raw_output"] = _interpret(message)
        data = data if data is None else _with_full_keys(data, version.get("output_schema") or {})
        stop, usage = message.stop_reason, message.usage
        tokens = (total_in, total_out) if total_in is not None else (getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None))
    except anthropic.APIError as exc:
        capture["raw_output"] = f"{type(exc).__name__}: {exc}"
    capture["trace"] = pack({"calls": trace, "error": capture["raw_output"] if status == STATUS_ERROR else None})
    row.update(
        status=status,
        stop_reason=stop,
        tokens_in=tokens[0],
        tokens_out=tokens[1],
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    run_id = _save_run(session_factory, row, capture)
    return CallResult(status=status, data=data, run_id=run_id, stop_reason=stop)
