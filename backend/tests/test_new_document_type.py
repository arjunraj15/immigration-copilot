import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ai import api as ai_api, doctype_agent, seed
from app.ai.client import STATUS_OK, CallResult
from app.core import audit
from app.db.session import SessionLocal
from app.main import app
from tests.conftest import make_case
from tests.test_ai_review import add_read, add_upload

client = TestClient(app)


def make_body(category: str) -> dict:
    return {
        "category": category, "title": "New type", "recognition_hint": "A card with a number.", "system_text": "Read the card.",
        "fields": [{"label": "Number", "type": "string", "required": True, "hint": "The card number", "quote": "1234", "page": 1},
                   {"label": "Issued", "type": "date", "required": False, "hint": "", "quote": "", "page": 0}],
    }


@pytest.fixture
def setup(monkeypatch):
    queued: list[str] = []
    monkeypatch.setattr(ai_api, "_reread", lambda actor, upload_id: queued.append(upload_id))
    category = "NTYPE" + uuid.uuid4().hex[:6].upper()
    case_id = f"CASE-N{uuid.uuid4().hex[:6].upper()}"
    ops = f"OPS-{uuid.uuid4().int % 90 + 10}"
    with SessionLocal() as db:
        seed.seed_prompts(db)
        make_case(db, case_id, ops=ops)
        upload = add_upload(db, case_id)
        add_read(db, upload, "UNKNOWN")
        db.commit()
    yield case_id, ops, upload, queued, category
    with SessionLocal() as db:
        db.execute(text("DELETE FROM document_reads WHERE upload_id = :u"), {"u": upload})
        db.execute(text("DELETE FROM uploads WHERE case_id = :c"), {"c": case_id})
        db.execute(text("UPDATE prompts SET enabled = false, deleted_at = now() WHERE category = :c"), {"c": category})
        db.commit()


def test_create_type_makes_active_additional_prompt_and_queues_only_the_source_upload(setup):
    _, ops, upload, queued, CATEGORY = setup
    response = client.post(f"/api/ai/review/{upload}/create-type", json=make_body(CATEGORY), headers={"X-Actor": ops})
    assert response.status_code == 201, response.text
    assert queued == [upload]
    with SessionLocal() as db:
        row = db.execute(text("SELECT p.origin, p.enabled, v.version, v.field_definitions, v.output_schema FROM prompts p JOIN prompt_versions v ON v.id = p.active_version_id WHERE p.category = :c"), {"c": CATEGORY}).one()
        assert row.origin == "ADDITIONAL" and row.enabled and row.version == 1
        assert [d["key"] for d in row.field_definitions] == [f"{CATEGORY}.Number", f"{CATEGORY}.Issued"]
        assert row.output_schema["properties"]["fields"]["required"] == [f"{CATEGORY}.Number"]
        actions = [e.action for e in audit.list_entries(db, audit.SYSTEM_STREAM, limit=10)[1]]
        assert "DOCUMENT_TYPE_CREATED" in actions and "PROMPT_VERSION_ACTIVATED" in actions
        assert audit.verify_stream(db, audit.SYSTEM_STREAM).valid
    listed = client.get("/api/ai/prompts").json()["read"]
    assert next(p for p in listed if p["category"] == CATEGORY)["origin"] == "ADDITIONAL"


def test_create_type_refuses_taken_and_reserved_categories(setup):
    _, ops, upload, _, category = setup
    url, h, body = f"/api/ai/review/{upload}/create-type", {"X-Actor": ops}, make_body(category)
    assert client.post(url, json=body, headers=h).status_code == 201
    assert client.post(url, json=body, headers=h).status_code == 409
    assert client.post(url, json=body | {"category": "UNKNOWN"}, headers=h).status_code == 422


def test_create_type_refuses_another_actors_upload(setup):
    _, _, upload, queued, category = setup
    assert client.post(f"/api/ai/review/{upload}/create-type", json=make_body(category), headers={"X-Actor": "OPS-99"}).status_code in (403, 404)
    assert queued == []


def test_draft_uses_the_model_result_and_checks_quotes(setup, monkeypatch):
    from app.ai import reader
    from app.ingest import service

    _, ops, upload, _, _ = setup
    pages = [(1, "Card Number: 1234 5678\nIssued: 2020-01-01")]
    monkeypatch.setattr(service, "load_pages", lambda db, u: reader.LoadedUpload("sha", pages))
    data = {"legible": True, "injection_flag": False, "matches_existing": "", "matches_reason": "", "category": "id card", "title": "ID card",
            "recognition_hint": "A card", "system_text": "Read it", "fields": [
                {"label": "Card Number", "type": "string", "required": True, "hint": "h", "quote": "1234 5678", "page": 1},
                {"label": "Made up", "type": "string", "required": False, "hint": "h", "quote": "not there", "page": 1}]}
    with SessionLocal() as db:
        draft = doctype_agent.draft_type(db, upload, call=lambda v, x: CallResult(status=STATUS_OK, data=data, run_id=None, stop_reason="end_turn"))
    assert draft.status == "OK" and draft.category == "ID_CARD"
    assert [(f["key"], f["verified"]) for f in draft.fields] == [("ID_CARD.Card Number", True), ("ID_CARD.Made up", False)]


BLANK = {"legible": True, "injection_flag": False, "matches_existing": "", "matches_reason": "", "category": "", "title": "",
         "recognition_hint": "", "system_text": "", "fields": []}


def test_a_blank_draft_is_asked_for_once_more(setup, monkeypatch):
    from app.ai import reader
    from app.ingest import service

    _, _, upload, _, _ = setup
    monkeypatch.setattr(service, "load_pages", lambda db, u: reader.LoadedUpload("sha", [(1, "Card Number: 1234")]))
    full = BLANK | {"category": "ID card", "fields": [{"label": "Card Number", "type": "string", "required": True, "hint": "h", "quote": "1234", "page": 1}]}
    answers = [BLANK, full]
    with SessionLocal() as db:
        draft = doctype_agent.draft_type(db, upload, call=lambda v, x: CallResult(status=STATUS_OK, data=answers.pop(0), run_id=None, stop_reason="end_turn"))
    assert answers == [] and draft.status == "OK" and draft.category == "ID_CARD" and len(draft.fields) == 1


def test_a_draft_blank_twice_says_so_and_has_no_fields(setup, monkeypatch):
    from app.ai import reader
    from app.ingest import service

    _, _, upload, _, _ = setup
    monkeypatch.setattr(service, "load_pages", lambda db, u: reader.LoadedUpload("sha", [(1, "text")]))
    calls = []
    with SessionLocal() as db:
        draft = doctype_agent.draft_type(db, upload, call=lambda v, x: calls.append(1) or CallResult(status=STATUS_OK, data=BLANK, run_id=None, stop_reason="end_turn"))
    assert len(calls) == 2 and draft.status == "NEEDS_REVIEW" and draft.fields == [] and "empty draft" in draft.error


def test_draft_failure_gives_needs_review_and_no_fields(setup, monkeypatch):
    from app.ai import reader
    from app.ingest import service

    _, _, upload, _, _ = setup
    monkeypatch.setattr(service, "load_pages", lambda db, u: reader.LoadedUpload("sha", [(1, "text")]))
    with SessionLocal() as db:
        draft = doctype_agent.draft_type(db, upload, call=lambda v, x: CallResult(status="NEEDS_REVIEW", data=None, run_id=None, stop_reason="refusal"))
    assert draft.status == "NEEDS_REVIEW" and draft.fields == [] and draft.error
