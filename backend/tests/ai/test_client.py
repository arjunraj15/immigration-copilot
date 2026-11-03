import json
from datetime import date
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from sqlalchemy import select

from app.ai import client
from app.ai.doc_tools import DocTools
from app.ai.models import PromptRun
from tests.ai.fakes import FakeApi, message

_REQ = httpx.Request("POST", "https://example.invalid/v1/messages")

SCHEMA = {"type": "object", "properties": {"fields": {"type": "object", "properties": {}}}}


def version(**over):
    base = {
        "version": 3, "model": "claude-sonnet-5-5", "effort": "medium", "max_tokens": 777,
        "system_text": "System for {{category}}", "user_template": "Text: {{document_text}}",
        "output_schema": SCHEMA,
    }
    return base | over


VARS = {"category": "PASSPORT", "document_text": "Name: Ana"}


def status_error(cls, code):
    return cls("boom", response=httpx.Response(code, request=_REQ), body=None)


def connection_error():
    return anthropic.APIConnectionError(request=_REQ)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(client.time, "sleep", lambda _s: None)


@pytest.fixture
def capture(monkeypatch):
    def setter(mode):
        monkeypatch.setattr(client, "get_settings", lambda: SimpleNamespace(ai_run_capture=mode))
    setter("full")
    return setter


def run(api, session_factory, ver=None, **kw):
    return client.run_prompt("doc.read.passport", ver or version(), VARS, api=api,
                             session_factory=session_factory, **kw)


def runs(session_factory):
    with session_factory() as db:
        return list(db.scalars(select(PromptRun).order_by(PromptRun.id)))


def test_ok_parses_json_and_writes_run(session_factory, capture):
    api = FakeApi(message('{"fields": {}}'))
    result = run(api, session_factory, input_text="Name: Ana")
    assert result.status == "ok"
    assert result.data == {"fields": {}}
    rows = runs(session_factory)
    assert len(rows) == 1
    assert rows[0].id == result.run_id
    assert (rows[0].status, rows[0].prompt_key, rows[0].version) == ("ok", "doc.read.passport", 3)
    assert (rows[0].tokens_in, rows[0].tokens_out, rows[0].stop_reason) == (11, 7, "end_turn")
    assert rows[0].latency_ms is not None


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_bad_stop_reason_needs_review_and_nothing_parsed(session_factory, capture, stop):
    api = FakeApi(message('{"fields": {}}', stop_reason=stop))
    result = run(api, session_factory)
    assert result.status == "needs_review"
    assert result.data is None
    assert result.stop_reason == stop
    assert runs(session_factory)[0].status == "needs_review"


def test_bad_json_needs_review(session_factory, capture):
    result = run(FakeApi(message("not json {")), session_factory)
    assert (result.status, result.data) == ("needs_review", None)


def test_json_that_is_not_an_object_needs_review(session_factory, capture):
    result = run(FakeApi(message("[1, 2]")), session_factory)
    assert (result.status, result.data) == ("needs_review", None)


def test_empty_content_needs_review(session_factory, capture):
    result = run(FakeApi(message(content=[])), session_factory)
    assert (result.status, result.data) == ("needs_review", None)
    assert len(runs(session_factory)) == 1


def test_non_text_blocks_only_needs_review(session_factory, capture):
    result = run(FakeApi(message(content=[SimpleNamespace(type="thinking", thinking="x")])), session_factory)
    assert (result.status, result.data) == ("needs_review", None)


@pytest.mark.parametrize("make", [
    connection_error,
    lambda: status_error(anthropic.RateLimitError, 429),
    lambda: status_error(anthropic.InternalServerError, 500),
])
def test_transient_error_is_retried_then_succeeds(session_factory, capture, make):
    api = FakeApi(make(), message('{"a": 1}'))
    result = run(api, session_factory)
    assert result.status == "ok"
    assert len(api.requests) == 2


@pytest.mark.parametrize("cls,code", [
    (anthropic.BadRequestError, 400),
    (anthropic.AuthenticationError, 401),
    (anthropic.PermissionDeniedError, 403),
    (anthropic.NotFoundError, 404),
    (anthropic.UnprocessableEntityError, 422),
])
def test_client_error_not_retried(session_factory, capture, cls, code):
    api = FakeApi(status_error(cls, code), message('{"a": 1}'))
    result = run(api, session_factory)
    assert result.status == "error"
    assert result.data is None
    assert len(api.requests) == 1


def test_retry_cap_honoured(session_factory, capture):
    api = FakeApi(status_error(anthropic.RateLimitError, 429))
    result = run(api, session_factory)
    assert result.status == "error"
    assert len(api.requests) == client._MAX_ATTEMPTS


def test_error_run_is_written(session_factory, capture):
    run(FakeApi(status_error(anthropic.BadRequestError, 400)), session_factory)
    rows = runs(session_factory)
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert rows[0].tokens_in is None
    assert "BadRequestError" in rows[0].raw_output


def test_request_has_no_forbidden_parameters(session_factory, capture):
    api = FakeApi(message())
    run(api, session_factory)
    request = api.requests[0]
    for name in ("tools", "tool_choice", "temperature", "top_p", "top_k"):
        assert name not in request
    assert set(request) == {"model", "max_tokens", "system", "messages", "output_config"}
    assert [m["role"] for m in request["messages"]] == ["user"]


def test_request_uses_version_model_effort_max_tokens(session_factory, capture):
    api = FakeApi(message())
    run(api, session_factory, ver=version(model="claude-opus-5-5", effort="high", max_tokens=4321))
    request = api.requests[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["max_tokens"] == 4321
    assert request["output_config"]["effort"] == "high"
    assert request["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}


def test_request_text_is_rendered_from_version(session_factory, capture):
    api = FakeApi(message())
    run(api, session_factory)
    assert api.requests[0]["system"] == "System for PASSPORT"
    assert api.requests[0]["messages"][0]["content"] == "Text: Name: Ana"


def test_capture_full_stores_content(session_factory, capture):
    capture("full")
    raw = json.dumps({"fields": {}})
    run(FakeApi(message(raw)), session_factory, input_text="Name: Ana")
    row = runs(session_factory)[0]
    assert row.rendered_prompt == "System for PASSPORT\n\nText: Name: Ana"
    assert row.input_text == "Name: Ana"
    assert row.raw_output == raw


def test_capture_hashes_stores_no_content(session_factory, capture):
    capture("hashes")
    run(FakeApi(message('{"fields": {}}')), session_factory, input_text="Name: Ana")
    row = runs(session_factory)[0]
    assert row.rendered_prompt is None
    assert row.input_text is None
    assert row.raw_output is None
    assert len(row.input_hash) == 64
    assert (row.model, row.version, row.status) == ("claude-sonnet-5-5", 3, "ok")


def test_capture_hashes_stores_no_error_text(session_factory, capture):
    capture("hashes")
    run(FakeApi(status_error(anthropic.BadRequestError, 400)), session_factory, input_text="secret")
    row = runs(session_factory)[0]
    assert (row.rendered_prompt, row.input_text, row.raw_output) == (None, None, None)


def test_input_hash_is_stable(session_factory, capture):
    run(FakeApi(message()), session_factory)
    run(FakeApi(message()), session_factory)
    first, second = runs(session_factory)
    assert first.input_hash == second.input_hash


def test_input_hash_changes_with_version(session_factory, capture):
    run(FakeApi(message()), session_factory, ver=version(version=3))
    run(FakeApi(message()), session_factory, ver=version(version=4))
    first, second = runs(session_factory)
    assert first.input_hash != second.input_hash


def test_input_hash_changes_with_text_and_model():
    base = client.input_hash("s", "u", "m", 1)
    assert base == client.input_hash("s", "u", "m", 1)
    assert base != client.input_hash("s", "u2", "m", 1)
    assert base != client.input_hash("s2", "u", "m", 1)
    assert base != client.input_hash("s", "u", "m2", 1)



def test_run_saves_compressed_trace_that_unpacks(session_factory, capture):
    from app.ai import trace as run_trace

    run(FakeApi(message('{"fields": {}}')), session_factory, input_text="x")
    blob = runs(session_factory)[0].trace
    assert isinstance(blob, bytes) and blob[:1] == b"x"
    saved = run_trace.unpack(blob)
    assert saved["error"] is None
    assert (saved["calls"][0]["stop_reason"], saved["calls"][0]["tokens_out"]) == ("end_turn", 7)
    assert saved["calls"][0]["content"][0]["type"] == "text"


def test_trace_is_not_kept_when_capture_is_off(session_factory, capture):
    capture("off")
    run(FakeApi(message('{"fields": {}}')), session_factory, input_text="x")
    assert runs(session_factory)[0].trace is None


FIELD_SCHEMA = {"type": "object", "properties": {"fields": {"type": "object", "properties": {
    "ARRIVAL_RECORD.Applicant": {}, "ARRIVAL_RECORD.Last Recorded Entry": {}}}}}


def test_a_first_answer_with_the_schema_field_keys_is_final_in_one_call(session_factory, capture):
    api = FakeApi(message('{"fields": {"ARRIVAL_RECORD.Last Recorded Entry": {"value": "2025-06-10"}}}'))
    result = run(api, session_factory, ver=version(output_schema=FIELD_SCHEMA), tools=DocTools(date(2026, 10, 23)))
    assert len(api.requests) == 1 and result.status == "ok"


def test_a_first_answer_with_shortened_field_keys_is_final_with_the_schema_keys(session_factory, capture):
    api = FakeApi(message('{"fields": {"Last Recorded Entry": {"value": "2025-06-10"}, "ARRIVAL_RECORD.Applicant": {"value": "A"}}}'))
    result = run(api, session_factory, ver=version(output_schema=FIELD_SCHEMA), tools=DocTools(date(2026, 10, 23)))
    assert len(api.requests) == 1
    assert result.data["fields"] == {"ARRIVAL_RECORD.Last Recorded Entry": {"value": "2025-06-10"}, "ARRIVAL_RECORD.Applicant": {"value": "A"}}


def test_a_first_answer_with_a_field_key_the_schema_lacks_is_asked_again_with_the_schema(session_factory, capture):
    api = FakeApi(message('{"fields": {"Entry": {"value": "2025-06-10"}}}'),
                  message('{"fields": {"ARRIVAL_RECORD.Last Recorded Entry": {"value": "2025-06-10"}}}'))
    result = run(api, session_factory, ver=version(output_schema=FIELD_SCHEMA), tools=DocTools(date(2026, 10, 23)))
    assert len(api.requests) == 2 and list(result.data["fields"]) == ["ARRIVAL_RECORD.Last Recorded Entry"]
    assert "format" in api.requests[1]["output_config"]  # the second call carries the schema
