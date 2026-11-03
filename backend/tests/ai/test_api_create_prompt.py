import copy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.client import CallResult
from app.ai import api, reader, seed
from app.db.session import get_db

URL = "/api/ai/prompts"


def value_schema():
    return {
        "type": "object",
        "properties": {"value": {"type": "string"}, "quote": {"type": "string"}, "page": {"type": "integer"}},
        "required": ["value", "quote", "page"],
    }


def new_body(**over):
    body = {
        "key": "doc.read.visa",
        "step": "read",
        "category": "VISA",
        "title": "Visa",
        "recognition_hint": "A visa stamp or label",
        "system_text": "Read the visa.",
        "user_template": "{{document_text}}",
        "model": "claude-sonnet-5-5",
        "effort": "medium",
        "max_tokens": 2048,
        "output_schema": {"type": "object", "properties": {"fields": {"type": "object", "properties": {"VISA.number": value_schema()}}}},
        "field_definitions": [{"key": "VISA.number", "label": "Number", "type": "string", "required": True, "hint": None}],
        "note": "first",
    }
    return copy.deepcopy(body) | over


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


def test_create_prompt_succeeds_with_actor(http):
    res = http.post(URL, json=new_body(), headers={"X-Actor": "LEGAL-01"})
    assert res.status_code == 201
    data = res.json()
    assert (data["key"], data["step"], data["category"]) == ("doc.read.visa", "read", "VISA")
    assert data["active"]["created_by"] == "LEGAL-01"
    assert [d["key"] for d in data["field_definitions"]] == ["VISA.number"]


def test_version_one_is_active_and_only_version(http):
    http.post(URL, json=new_body())
    detail = http.get(f"{URL}/doc.read.visa").json()
    assert detail["active_version"] == 1
    assert [v["version"] for v in http.get(f"{URL}/doc.read.visa/versions").json()] == [1]


def test_duplicate_key_returns_409(http):
    res = http.post(URL, json=new_body(key="doc.read.passport", category="NEWPASS"))
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "PROMPT_EXISTS"


def test_read_without_category_returns_422(http):
    res = http.post(URL, json=new_body(category=None))
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "CATEGORY_REQUIRED"


def test_lowercase_category_returns_422(http):
    assert http.post(URL, json=new_body(category="visa")).status_code == 422


def test_schema_without_quote_returns_422(http):
    body = new_body()
    props = body["output_schema"]["properties"]["fields"]["properties"]["VISA.number"]
    props["required"].remove("quote")
    res = http.post(URL, json=body)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_PROMPT_VERSION"
    assert http.get(f"{URL}/doc.read.visa").status_code == 404


def test_duplicate_category_returns_409(http):
    http.post(URL, json=new_body())
    res = http.post(URL, json=new_body(key="doc.read.visa", category="VISA"))
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "PROMPT_EXISTS"


def test_read_key_must_match_category(http):
    res = http.post(URL, json=new_body(key="doc.read.other"))
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "KEY_CATEGORY_MISMATCH"


def test_only_document_type_prompts_can_be_added(http):
    for step in ("classify", "other"):
        res = http.post(URL, json=new_body(key="doc.extra", step=step, category=None))
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "DOCUMENT_TYPE_ONLY"


def test_unknown_category_is_reserved(http):
    res = http.post(URL, json=new_body(key="doc.read.unknown", category="UNKNOWN"))
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "CATEGORY_RESERVED"


def test_new_category_appears_in_classifier_categories(http, session_factory, monkeypatch):
    monkeypatch.setattr(reader, "SessionLocal", session_factory)
    http.post(URL, json=new_body())
    lines = reader._db_categories().splitlines()
    assert "- VISA: A visa stamp or label" in lines
    assert reader._db_get_version("doc.read.visa")["version"] == 1


def add_visa(http):
    assert http.post(URL, json=new_body()).status_code == 201


def categories(session_factory, monkeypatch):
    monkeypatch.setattr(reader, "SessionLocal", session_factory)
    return reader._db_categories()


def test_disable_excludes_category_and_enable_restores(http, session_factory, monkeypatch):
    add_visa(http)
    res = http.post(f"{URL}/doc.read.visa/disable")
    assert (res.status_code, res.json()["enabled"]) == (200, False)
    assert "VISA" not in categories(session_factory, monkeypatch)
    assert reader._db_get_version("doc.read.visa") is None
    assert http.post(f"{URL}/doc.read.visa/enable").json()["enabled"] is True
    assert "VISA" in categories(session_factory, monkeypatch)
    assert reader._db_get_version("doc.read.visa")["version"] == 1


def fake_call(seen):
    def call(version, _vars):
        seen.append(version["prompt_key"])
        return CallResult("ok", {"fields": {}}, None)
    return call


def test_disabled_prompt_routes_to_generic_and_enable_restores(http, session_factory, monkeypatch):
    add_visa(http)
    monkeypatch.setattr(reader, "SessionLocal", session_factory)
    group = [(1, "visa text")]
    http.post(f"{URL}/doc.read.visa/disable")
    seen = []
    deps = reader.ReaderDeps(None, reader._db_get_version, lambda: "", call=fake_call(seen))
    reader._read_group(deps, "VISA", group, "sha")
    http.post(f"{URL}/doc.read.visa/enable")
    reader._read_group(deps, "VISA", group, "sha")
    assert seen == ["doc.read.generic", "doc.read.visa"]


def test_delete_hides_prompt(http):
    add_visa(http)
    assert http.delete(f"{URL}/doc.read.visa").status_code == 204
    keys = [p["key"] for p in http.get(URL).json()["read"]]
    assert "doc.read.visa" not in keys
    shown = http.get(URL, params={"include_deleted": "true"}).json()["read"]
    assert any(p["key"] == "doc.read.visa" and p["deleted"] for p in shown)
    assert http.get(f"{URL}/doc.read.visa").status_code == 404


def test_seed_does_not_resurrect_deleted_key(http, session_factory):
    http.delete(f"{URL}/doc.read.passport")
    with session_factory() as db:
        assert seed.seed_prompts(db) == []
    keys = [p["key"] for p in http.get(URL).json()["read"]]
    assert "doc.read.passport" not in keys


def test_create_with_deleted_key_rejected_and_restore_works(http):
    add_visa(http)
    http.delete(f"{URL}/doc.read.visa")
    res = http.post(URL, json=new_body())
    assert (res.status_code, res.json()["error"]["code"]) == (409, "PROMPT_DELETED")
    assert http.post(f"{URL}/doc.read.visa/restore").json()["deleted"] is False


@pytest.mark.parametrize("key", ["doc.classify", "doc.read.generic"])
def test_protected_keys_return_409(http, key):
    for res in (http.post(f"{URL}/{key}/disable"), http.delete(f"{URL}/{key}")):
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "PROMPT_PROTECTED"


def test_tools_route_lists_the_catalog(http):
    out = http.get("/api/ai/tools").json()
    assert {t["name"] for t in out} >= {"get_today", "parse_date", "date_in_range"}
    assert all(t["description"] for t in out)


def test_create_prompt_saves_its_tools_and_drops_repeats(http):
    body = new_body(tools=["parse_date", "get_today", "parse_date"])
    detail = http.post(URL, json=body).json()
    assert detail["tools"] == ["parse_date", "get_today"]
    assert detail["active"]["tools"] == ["parse_date", "get_today"]


def test_create_prompt_defaults_to_no_tools(http):
    assert http.post(URL, json=new_body()).json()["tools"] == []


def test_create_prompt_rejects_an_unknown_tool(http):
    res = http.post(URL, json=new_body(tools=["delete_case"]))
    assert res.status_code == 422 and "delete_case" in res.json()["error"]["message"]


def test_a_new_version_can_change_the_tools(http):
    http.post(URL, json=new_body())
    body = new_body(tools=["get_today"])
    for k in ("key", "step", "category", "title", "recognition_hint"):
        body.pop(k)
    res = http.post(f"{URL}/doc.read.visa/versions", json=body)
    assert res.status_code == 201 and res.json()["tools"] == ["get_today"]
