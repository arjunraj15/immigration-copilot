from datetime import date
from types import SimpleNamespace

import pytest

from app.ai import client
from app.ai import reader
from app.ai.doc_tools import ARGS, TOOL_SPECS, DocTools, catalog, unknown_tools
from tests.ai.fakes import FakeApi, message
from tests.ai.test_client import SCHEMA, VARS, capture, no_sleep, runs, version  # noqa: F401

REVIEW = date(2026, 10, 24)


@pytest.fixture
def tools():
    return DocTools(REVIEW)


def call(box, name, **args):
    data, error = box.call(name, args)
    assert not error, data
    return data


def test_specs_match_args_and_never_take_a_case_id():
    assert {s["name"] for s in TOOL_SPECS} == set(ARGS)
    assert all("case_id" not in props for props in ARGS.values())
    assert all(s["input_schema"]["additionalProperties"] is False for s in TOOL_SPECS)


def test_get_today_is_the_review_date_not_the_clock(tools):
    today = call(tools, "get_today")["today"]
    assert (today["iso"], today["us"], today["weekday"]) == ("2026-10-24", "10/24/2026", "Saturday")


@pytest.mark.parametrize("text,iso", [("2025-03-04", "2025-03-04"), ("03/04/2025", "2025-03-04")])
def test_parse_date_reads_both_formats(tools, text, iso):
    out = call(tools, "parse_date", text=text)
    assert out["readable"] and out["date"]["iso"] == iso


@pytest.mark.parametrize("text", ["03/04/25", "2025-02-30", "March fourth", ""])
def test_parse_date_says_why_it_cannot_read(tools, text):
    out = call(tools, "parse_date", text=text)
    assert out["readable"] is False and out["reason"]


def test_days_between_gives_days_and_a_span(tools):
    out = call(tools, "days_between", start="2026-01-31", end="2026-03-01")
    assert out["days"] == 29
    assert out["span"] == {"years": 0, "months": 1, "days": 1}


def test_days_between_is_negative_when_end_is_first(tools):
    out = call(tools, "days_between", start="2026-03-01", end="2026-01-31")
    assert out["days"] == -29 and out["span"] == {"years": 0, "months": 1, "days": 1}


def test_days_between_whole_years(tools):
    assert call(tools, "days_between", start="2020-02-29", end="2025-02-28")["span"] == {"years": 4, "months": 11, "days": 30}


def test_date_in_range_defaults_to_the_review_date(tools):
    inside = call(tools, "date_in_range", start="2026-01-01", end="2027-01-01", date="")
    assert inside["inside"] and inside["position"] == "INSIDE" and inside["days_until_end"] == 69
    after = call(tools, "date_in_range", start="2025-01-01", end="2026-01-01", date="")
    assert after["position"] == "AFTER_END" and not after["inside"]


def test_date_in_range_edges_are_inside_and_before_start(tools):
    assert call(tools, "date_in_range", start="2026-01-01", end="2026-01-31", date="2026-01-31")["inside"]
    assert call(tools, "date_in_range", start="2026-01-01", end="2026-01-31", date="2025-12-31")["position"] == "BEFORE_START"


def test_date_in_range_rejects_reversed_window(tools):
    data, error = tools.call("date_in_range", {"start": "2026-02-01", "end": "2026-01-01", "date": ""})
    assert "before the start" in data["error"] and not error


def test_add_days_reuses_the_validation_layer(tools):
    assert call(tools, "add_days", start="2026-10-24", days=30)["result"]["iso"] == "2026-11-23"


@pytest.mark.parametrize("name,args", [("delete_case", {}), ("add_days", {"start": "2026-01-01", "days": 1, "case_id": "CASE-0001"}),
                                       ("add_days", {"start": "2026-01-01"})])
def test_unknown_tool_extra_or_missing_argument_is_an_error(tools, name, args):
    data, error = tools.call(name, args)
    assert error and "error" in data


def tool_use(id, name, **args):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=args)


def text(body):
    return SimpleNamespace(type="text", text=body)


def test_run_prompt_runs_tool_rounds_then_asks_for_the_schema(session_factory, capture):
    api = FakeApi(
        message(content=[tool_use("u1", "get_today")], stop_reason="tool_use"),
        message(content=[text("done")]),
        message('{"fields": {}}'),
    )
    result = client.run_prompt("doc.read.passport", version(), VARS, api=api, session_factory=session_factory, tools=DocTools(REVIEW))
    assert (result.status, result.data) == ("ok", {"fields": {}})
    first, _, last = api.requests
    assert "format" not in first["output_config"] and first["tools"] == DocTools(REVIEW).specs == TOOL_SPECS
    sent = last["messages"][2]["content"][0]  # the fake shares one growing list across requests
    assert sent["type"] == "tool_result" and sent["tool_use_id"] == "u1" and "2026-10-24" in sent["content"] and not sent["is_error"]
    assert last["tool_choice"] == {"type": "none"} and last["output_config"]["format"]["schema"] == SCHEMA
    row = runs(session_factory)[0]
    assert (row.tokens_in, row.tokens_out, row.status) == (33, 21, "ok")


def test_run_prompt_without_tools_sends_none(session_factory, capture):
    api = FakeApi(message('{"fields": {}}'))
    client.run_prompt("doc.read.passport", version(), VARS, api=api, session_factory=session_factory)
    assert "tools" not in api.requests[0] and len(api.requests) == 1


def test_run_prompt_stops_tool_rounds_at_the_limit(session_factory, capture):
    looping = message(content=[tool_use("u", "get_today")], stop_reason="tool_use")
    api = FakeApi(looping, looping, looping, looping, looping, message('{"fields": {}}'))
    result = client.run_prompt("doc.read.passport", version(), VARS, api=api, session_factory=session_factory, tools=DocTools(REVIEW))
    assert result.status == "ok" and len(api.requests) == client.MAX_TOOL_ROUNDS + 2
    refused = api.requests[-1]["messages"][-2]["content"][0]
    assert refused["is_error"] and "limit" in refused["content"]


def test_run_prompt_with_tools_refusal_needs_review(session_factory, capture):
    api = FakeApi(message("{}", stop_reason="refusal"))
    result = client.run_prompt("doc.read.passport", version(), VARS, api=api, session_factory=session_factory, tools=DocTools(REVIEW))
    assert (result.status, result.data) == ("needs_review", None) and len(api.requests) == 1


def test_a_version_gets_only_the_tools_it_lists():
    assert DocTools.for_version({"tools": []}, REVIEW) is None
    assert DocTools.for_version({}, REVIEW) is None
    arrival = DocTools.for_version({"tools": ["parse_date", "date_in_range"]}, REVIEW)
    assert {s["name"] for s in arrival.specs} == {"parse_date", "date_in_range"}


def test_a_tool_outside_the_version_list_is_refused():
    arrival = DocTools.for_version({"tools": ["parse_date"]}, REVIEW)
    data, error = arrival.call("get_today", {})
    assert error and "Unknown tool" in data["error"]


def test_catalog_lists_every_tool_with_a_description():
    assert [c["name"] for c in catalog()] == [s["name"] for s in TOOL_SPECS]
    assert all(c["description"] for c in catalog())
    assert unknown_tools(["get_today", "nope", "nope"]) == ["nope"]


def test_reader_passes_tools_only_when_the_version_lists_them():
    assert reader._tools({"tools": []}, lambda: REVIEW) is None
    assert reader._tools({"tools": ["get_today"]}, None) is None
    assert [s["name"] for s in reader._tools({"tools": ["get_today"]}, lambda: REVIEW).specs] == ["get_today"]
