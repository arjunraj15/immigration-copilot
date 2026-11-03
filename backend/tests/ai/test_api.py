import copy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.ai import api, reader, seed
from app.ai.models import Prompt, PromptRun, PromptVersion
from app.db.session import get_db
from tests.ai.fakes import FakeModel, field, make_deps, page_entry, read_data

KEY = "doc.read.passport"
EDITABLE = ("system_text", "user_template", "model", "effort", "max_tokens", "output_schema", "field_definitions", "note")


@pytest.fixture
def http(session_factory):
    with session_factory() as db:
        seed.seed_prompts(db)
    app = FastAPI()
    app.include_router(api.router)
    app.add_exception_handler(api.ApiError, api.api_error_handler)

    def override():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def body_from_active(http, key=KEY):
    active = http.get(f"/api/ai/prompts/{key}").json()["active"]
    return {k: copy.deepcopy(active[k]) for k in EDITABLE}


def state(session_factory):
    with session_factory() as db:
        prompts = [(p.key, p.active_version_id, p.title) for p in db.scalars(select(Prompt).order_by(Prompt.key))]
        versions = db.scalar(select(func.count()).select_from(PromptVersion))
        runs = db.scalar(select(func.count()).select_from(PromptRun))
    return prompts, versions, runs


def test_unknown_prompt_returns_404_with_error_shape(http):
    res = http.get("/api/ai/prompts/doc.read.nothing")
    assert res.status_code == 404
    assert res.json() == {"error": {"code": "PROMPT_NOT_FOUND", "message": "No prompt with key doc.read.nothing"}}


def test_list_prompts_grouped_by_step(http):
    data = http.get("/api/ai/prompts").json()
    assert [p["key"] for p in data["classify"]] == ["doc.classify"]
    assert len(data["read"]) == 11
    assert data["read"][0]["active_version"] == 1


def test_get_prompt_returns_active_and_field_definitions(http):
    data = http.get(f"/api/ai/prompts/{KEY}").json()
    assert data["active"]["version"] == 1
    assert {d["key"] for d in data["field_definitions"]} == {k for k in data["active"]["output_schema"]["properties"]["fields"]["properties"]}


def test_new_version_auto_increments(http):
    body = body_from_active(http)
    first = http.post(f"/api/ai/prompts/{KEY}/versions", json=body | {"note": "a"}, headers={"X-Actor": "LEGAL-01"})
    second = http.post(f"/api/ai/prompts/{KEY}/versions", json=body | {"note": "b"})
    assert (first.status_code, first.json()["version"]) == (201, 2)
    assert first.json()["created_by"] == "LEGAL-01"
    assert second.json()["version"] == 3
    assert [v["version"] for v in http.get(f"/api/ai/prompts/{KEY}/versions").json()] == [3, 2, 1]


def test_new_version_is_not_active_until_activated(http):
    http.post(f"/api/ai/prompts/{KEY}/versions", json=body_from_active(http))
    assert http.get(f"/api/ai/prompts/{KEY}").json()["active_version"] == 1


def test_removed_field_returns_409_key_locked(http):
    body = body_from_active(http)
    dropped = body["field_definitions"].pop()["key"]
    del body["output_schema"]["properties"]["fields"]["properties"][dropped]
    res = http.post(f"/api/ai/prompts/{KEY}/versions", json=body)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "KEY_LOCKED"
    assert dropped in res.json()["error"]["message"]


def test_renamed_field_returns_409_key_locked(http):
    body = body_from_active(http)
    old = body["field_definitions"][0]["key"]
    body["field_definitions"][0]["key"] = "PASSPORT.renamed"
    props = body["output_schema"]["properties"]["fields"]["properties"]
    props["PASSPORT.renamed"] = props.pop(old)
    assert http.post(f"/api/ai/prompts/{KEY}/versions", json=body).status_code == 409


def test_schema_without_quote_returns_422(http):
    body = body_from_active(http)
    first = next(iter(body["output_schema"]["properties"]["fields"]["properties"].values()))
    first["required"].remove("quote")
    res = http.post(f"/api/ai/prompts/{KEY}/versions", json=body)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_PROMPT_VERSION"
    assert "quote" in res.json()["error"]["message"]


def test_schema_without_page_returns_422(http):
    body = body_from_active(http)
    first = next(iter(body["output_schema"]["properties"]["fields"]["properties"].values()))
    del first["properties"]["page"]
    first["required"].remove("page")
    assert http.post(f"/api/ai/prompts/{KEY}/versions", json=body).status_code == 422


def test_rejected_version_is_not_saved(http, session_factory):
    before = state(session_factory)
    body = body_from_active(http)
    body["output_schema"] = {"type": "object"}
    http.post(f"/api/ai/prompts/{KEY}/versions", json=body)
    assert state(session_factory) == before


def test_activate_and_rollback(http):
    http.post(f"/api/ai/prompts/{KEY}/versions", json=body_from_active(http) | {"note": "v2"})
    up = http.post(f"/api/ai/prompts/{KEY}/activate", json={"version": 2})
    assert up.status_code == 200
    assert up.json()["active_version"] == 2
    assert up.json()["active"]["note"] == "v2"
    down = http.post(f"/api/ai/prompts/{KEY}/activate", json={"version": 1})
    assert down.json()["active_version"] == 1
    assert [v["version"] for v in http.get(f"/api/ai/prompts/{KEY}/versions").json()] == [2, 1]


def test_activate_unknown_version_returns_404(http):
    res = http.post(f"/api/ai/prompts/{KEY}/activate", json={"version": 99})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "VERSION_NOT_FOUND"


def test_runs_list_filters_by_prompt_key(http, session_factory):
    with session_factory() as db:
        for key in ("a", "a", "b"):
            db.add(PromptRun(prompt_key=key, version=1, model="m", input_hash="h" * 64, status="ok"))
        db.commit()
    assert len(http.get("/api/ai/runs").json()) == 3
    assert len(http.get("/api/ai/runs", params={"prompt_key": "a"}).json()) == 2
    assert len(http.get("/api/ai/runs", params={"limit": 1}).json()) == 1
    assert http.get("/api/ai/runs", params={"limit": 0}).status_code == 422


# POST /test

@pytest.fixture
def fake_reader(monkeypatch):
    model = FakeModel({"pages": [page_entry(1, "PASSPORT")]},
                      {"PASSPORT": read_data({"PASSPORT.applicant": field("Mira", "Applicant: Mira")})})
    deps = make_deps(model, [], read_keys=(KEY,), cache=reader._CACHE)
    monkeypatch.setattr(reader, "default_deps", lambda *a, **k: deps)
    return model


def test_post_test_returns_result_shape(http, fake_reader):
    res = http.post("/api/ai/test", json={"text": "Applicant: Mira"})
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "PASSPORT"
    assert data["fields"][0]["key"] == "PASSPORT.applicant"
    assert data["fields"][0]["verified"] is True
    assert data["prompt_run_ids"] == [1, 2]


def test_post_test_changes_no_prompts_versions_and_writes_no_cache(http, fake_reader, session_factory):
    reader._CACHE.clear()
    before = state(session_factory)
    override = body_from_active(http) | {"system_text": "Unsaved override"}
    res = http.post("/api/ai/test", json={"text": "Applicant: Mira", "prompt_key": KEY, "override": override})
    assert res.status_code == 200
    assert state(session_factory) == before
    assert reader._CACHE == {}
    used = [c for c in fake_reader.calls if c[0] == KEY][0]
    assert used[1]["system_text"] == "Unsaved override"
    assert http.get(f"/api/ai/prompts/{KEY}").json()["active"]["system_text"] != "Unsaved override"


def test_post_test_requires_text_or_upload(http):
    res = http.post("/api/ai/test", json={})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "TEST_INPUT_REQUIRED"


def test_post_test_upload_id_returns_501(http):
    res = http.post("/api/ai/test", json={"upload_id": 999999999})
    assert res.status_code == 501
    assert res.json()["error"]["code"] == "UPLOADS_UNAVAILABLE"


def test_rename_prompt(http):
    url = f"/api/ai/prompts/{KEY}"
    res = http.patch(url, json={"title": "  Travel passport "})
    assert res.status_code == 200 and res.json()["title"] == "Travel passport"
    assert http.patch(url, json={"title": "  "}).status_code == 422
    assert http.patch(url, json={"title": "x" * 201}).status_code == 422
    assert http.patch("/api/ai/prompts/doc.read.nope", json={"title": "A"}).status_code == 404
    generic = "/api/ai/prompts/doc.read.generic"
    assert http.patch(generic, json={"title": "Unclear document"}).json()["title"] == "Unclear document"
    assert http.post(f"{generic}/disable").status_code == 409
    assert http.delete(generic).status_code == 409
    assert http.patch("/api/ai/prompts/doc.classify", json={"title": "A"}).status_code == 409


def test_stats_counts_runs_failures_and_latency(http, session_factory):
    now = datetime.now(timezone.utc)
    rows = [("ok", 1000, now), ("ok", 3000, now), ("error", 5000, now), ("ok", 900, now - timedelta(days=10))]
    with session_factory() as db:
        for status, latency, at in rows:
            db.add(PromptRun(prompt_key=KEY, version=1, model="m", input_hash="h", status=status, latency_ms=latency, created_at=at))
        db.commit()
    data = http.get("/api/ai/stats").json()
    assert (data["runs"], data["failed"], data["runs_prev"]) == (3, 1, 1)
    listed = http.get("/api/ai/prompts").json()
    assert data["prompts"] == data["enabled"] == sum(len(rows) for rows in listed.values())
    assert [d["runs"] for d in data["days"]] == [0, 0, 0, 0, 0, 0, 3]
    health = data["by_prompt"][KEY]
    assert (health["ok_pct"], health["median_latency_ms"], health["spark"][-1]) == (67, 3000, 3)


def test_trace_endpoint_expands_saved_trace(http, session_factory):
    from app.ai import trace as run_trace

    blob = run_trace.pack({"calls": [{"stop_reason": "end_turn", "content": []}], "error": None})
    with session_factory() as db:
        run = PromptRun(prompt_key=KEY, version=1, model="m", input_hash="h", status="ok", rendered_prompt="sys", trace=blob)
        legacy = PromptRun(prompt_key=KEY, version=1, model="m", input_hash="h2", status="ok")
        db.add_all([run, legacy])
        db.commit()
        ids = (run.id, legacy.id)
    data = http.get(f"/api/ai/runs/{ids[0]}/trace").json()
    assert (data["saved"], data["prompt"], data["calls"][0]["stop_reason"]) == (True, "sys", "end_turn")
    assert http.get(f"/api/ai/runs/{ids[1]}/trace").json()["saved"] is False
    assert http.get("/api/ai/runs/999999/trace").status_code == 404


def test_form_targets_list_the_fields_the_form_template_names(http):
    res = http.get("/api/ai/form-targets")
    assert res.status_code == 200
    targets = [item["target"] for item in res.json()]
    assert "applicant.passport_expiration" in targets and all(set(item) == {"target", "label", "section"} for item in res.json())


def test_version_with_an_unknown_form_target_is_refused_and_a_known_one_is_saved(http):
    body = body_from_active(http)
    body["field_definitions"][0]["form_target"] = "applicant.shoe_size"
    res = http.post(f"/api/ai/prompts/{KEY}/versions", json=body)
    assert res.status_code == 422 and res.json()["error"]["code"] == "UNKNOWN_FORM_TARGET"
    body["field_definitions"][0]["form_target"] = "applicant.legal_name"
    assert http.post(f"/api/ai/prompts/{KEY}/versions", json=body).status_code == 201
    body["field_definitions"][0]["form_target"] = None  # validate only
    assert http.post(f"/api/ai/prompts/{KEY}/versions", json=body).status_code == 201


def test_schema_is_built_from_the_fields_when_left_out(http):
    body = body_from_active(http)
    stored = body.pop("output_schema")
    body["field_definitions"].append({"key": "PASSPORT.Issuing Office", "label": "Issuing office", "type": "string", "required": False, "hint": None})
    res = http.post(f"/api/ai/prompts/{KEY}/versions", json=body)
    assert res.status_code == 201
    saved = res.json()["output_schema"]
    assert "PASSPORT.Issuing Office" in saved["properties"]["fields"]["properties"]
    assert "PASSPORT.Issuing Office" not in saved["properties"]["fields"]["required"]
    assert saved["properties"]["fields"]["required"] == stored["properties"]["fields"]["required"]


def test_preview_schema_matches_what_a_seeded_prompt_stores(http):
    active = http.get(f"/api/ai/prompts/{KEY}").json()["active"]
    res = http.post("/api/ai/output-schema", json={"category": "PASSPORT", "field_definitions": active["field_definitions"]})
    assert res.status_code == 200 and res.json() == active["output_schema"]


def test_preview_schema_needs_a_valid_category(http):
    assert http.post("/api/ai/output-schema", json={"category": "bad", "field_definitions": []}).status_code == 422
