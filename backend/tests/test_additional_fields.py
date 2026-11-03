import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ai import api as ai_api, doctype_agent, form_fields, seed
from app.core import audit
from app.db.session import SessionLocal
from app.facts import engine, sources
from app.main import app
from app.replies import service as replies
from tests.test_ai_review import add_read, add_upload
from tests.conftest import make_case
from tests.test_facts import OPS, add_doc, call, draft, facts, new_case

client = TestClient(app)
HEADERS = {"X-Actor": OPS}


@pytest.fixture
def make_extra():
    """Make an additional client field and a read type that fills it. Everything made is removed afterwards."""
    made: list[tuple[str, str]] = []

    def build(value_type: str = "string") -> tuple[str, str]:
        suffix = uuid.uuid4().hex[:6]
        category = f"ADDX{suffix.upper()}"
        field = client.post("/api/ai/form-fields", json={"label": f"Extra {suffix}", "value_type": value_type}, headers=HEADERS)
        assert field.status_code == 201, field.text
        target = field.json()["target"]
        body = {
            "key": f"doc.read.{category.lower()}", "step": "read", "category": category, "title": category, "recognition_hint": "x",
            "system_text": "Read it.", "user_template": "{{document_text}}", "model": "claude-sonnet-5-5", "effort": "low", "max_tokens": 1000,
            "field_definitions": [{"key": f"{category}.Number", "label": "Number", "type": value_type, "required": True, "hint": "", "form_target": target}],
        }
        created = client.post("/api/ai/prompts", json=body, headers=HEADERS)
        assert created.status_code == 201, created.text
        made.append((target, category))
        return target, category

    yield build
    with SessionLocal() as db:
        for target, category in made:
            db.execute(text("UPDATE prompts SET enabled = false, deleted_at = now() WHERE category = :c"), {"c": category})
            db.execute(text("DELETE FROM additional_form_fields WHERE target = :t"), {"t": target})
        engine.invalidate(db)
        db.commit()


def test_target_is_a_code_built_slug():
    assert form_fields.target_for("Aadhaar Number") == "additional.aadhaar_number"
    assert form_fields.target_for("  PAN / Tax ID!  ") == "additional.pan_tax_id"
    assert form_fields.target_for("???") is None


def test_adding_a_field_lists_it_in_the_picker_audits_it_and_refuses_a_repeat(make_extra):
    target, _ = make_extra()
    listed = client.get("/api/ai/form-targets").json()
    assert {"target": target, "label": target.removeprefix("additional.").replace("_", " ").capitalize(), "section": "Additional client fields"} in listed
    assert client.post("/api/ai/form-fields", json={"label": target.removeprefix("additional."), "value_type": "string"}, headers=HEADERS).status_code == 409
    assert client.post("/api/ai/form-fields", json={"label": "!!!", "value_type": "string"}, headers=HEADERS).status_code == 422
    assert client.post("/api/ai/form-fields", json={"label": "Fine label", "value_type": "blob"}, headers=HEADERS).status_code == 422
    with SessionLocal() as db:
        entries = audit.list_entries(db, audit.SYSTEM_STREAM, limit=50)[1]
        assert any(e.action == "FORM_FIELD_ADDED" and e.target_id == target for e in entries)
        assert audit.verify_stream(db, audit.SYSTEM_STREAM).valid


def test_a_document_value_fills_the_additional_row_with_its_evidence(make_extra):
    target, category = make_extra()
    case_id = new_case()
    upload = add_doc(case_id, f"{category}.Number", "1234 5678 9012")
    state = facts(case_id)[target]
    assert state["state"] == "SINGLE_SOURCE_EVIDENCE" and state["value"] == "1234 5678 9012"
    body = call("GET", f"/api/cases/{case_id}/form-draft").json()
    section = body["sections"][-1]
    assert section["title"] == "Additional client fields"
    assert [(f["target"], f["required"]) for f in section["fields"]] == [(target, False)]
    row = draft(case_id)[target]
    assert row["status"] == "PROPOSED" and row["value"] == "1234 5678 9012" and row["evidence_refs"] == [upload]


def test_two_documents_that_disagree_hold_the_additional_row(make_extra):
    target, category = make_extra()
    case_id = new_case()
    add_doc(case_id, f"{category}.Number", "1111")
    add_doc(case_id, f"{category}.Number", "2222")
    assert facts(case_id)[target]["state"] == "CONFLICT"
    row = draft(case_id)[target]
    assert row["status"] == "HELD_FOR_REVIEW" and row["value"] is None


def test_an_additional_date_field_is_written_as_iso(make_extra):
    target, category = make_extra("date")
    case_id = new_case()
    add_doc(case_id, f"{category}.Number", "April 8, 1982")
    assert facts(case_id)[target]["value"] == "1982-04-08"


def test_an_empty_additional_field_is_not_a_gap(make_extra):
    target, _ = make_extra()
    case_id = new_case()
    assert target not in facts(case_id)
    row = draft(case_id)[target]
    assert row["status"] == "NOT_AVAILABLE" and row["value"] is None
    with SessionLocal() as db:
        asks, _ = replies.asks_of(db, engine.read(db, case_id))
    assert not any(target.removeprefix("additional.").replace("_", " ") in ask.lower() for ask in asks)


def test_the_form_has_the_section_only_when_a_field_exists():
    case_id = new_case()
    titles = [s["title"] for s in call("GET", f"/api/cases/{case_id}/form-draft").json()["sections"]]
    with SessionLocal() as db:
        assert ("Additional client fields" in titles) == bool(sources.additional_fields(db))


# ---------------------------------------------------------------- the draft agent and create-type

PAGES = {1: "Name: Asha Rao\nUID Number: 1234 5678 9012"}


def raw(label: str, target: str | None, **over):
    return {"label": label, "type": "string", "required": True, "hint": "h", "quote": "Asha Rao", "page": 1, "form_target": target} | over


def test_the_draft_keeps_a_known_target_drops_an_unknown_one_and_flags_new():
    known = {"applicant.legal_name", "additional.uid_number"}
    fields = doctype_agent.build_fields(
        "X", [raw("Name", "applicant.legal_name"), raw("Shoe", "applicant.shoe_size"), raw("Blood group", "NEW"), raw("UID Number", "NEW"), raw("Plain", "")],
        PAGES, set(), known,
    )
    got = [(f["label"], f["form_target"], f["new_form_field"]) for f in fields]
    assert got == [("Name", "applicant.legal_name", False), ("Shoe", None, False), ("Blood group", None, True),
                   ("UID Number", "additional.uid_number", False), ("Plain", None, False)]


def test_field_definitions_carry_the_form_target_only_when_there_is_one():
    defs = doctype_agent.field_definitions([
        {"key": "X.A", "label": "A", "type": "string", "required": True, "form_target": "applicant.legal_name"},
        {"key": "X.B", "label": "B", "type": "string", "required": False, "form_target": None},
    ])
    assert defs[0]["form_target"] == "applicant.legal_name" and "form_target" not in defs[1]


@pytest.fixture
def new_type(monkeypatch):
    queued: list[str] = []
    monkeypatch.setattr(ai_api, "_reread", lambda actor, upload_id: queued.append(upload_id))
    suffix = uuid.uuid4().hex[:6]
    category, case_id, ops = f"NTYPE{suffix.upper()}", f"CASE-N{suffix.upper()}", f"OPS-{uuid.uuid4().int % 90 + 10}"
    with SessionLocal() as db:
        seed.seed_prompts(db)
        make_case(db, case_id, ops=ops)
        upload = add_upload(db, case_id)
        add_read(db, upload, "UNKNOWN")
        db.commit()
    yield upload, ops, category, suffix
    with SessionLocal() as db:
        db.execute(text("DELETE FROM document_reads WHERE upload_id = :u"), {"u": upload})
        db.execute(text("DELETE FROM uploads WHERE case_id = :c"), {"c": case_id})
        db.execute(text("UPDATE prompts SET enabled = false, deleted_at = now() WHERE category = :c"), {"c": category})
        db.execute(text("DELETE FROM additional_form_fields WHERE label LIKE :l"), {"l": f"%{suffix}"})
        engine.invalidate(db)
        db.commit()


def type_body(category: str, suffix: str) -> dict:
    return {
        "category": category, "title": "New type", "recognition_hint": "A card.", "system_text": "Read the card.",
        "fields": [
            {"label": f"Card number {suffix}", "type": "string", "required": True, "hint": "", "quote": "1234", "page": 1, "new_form_field": True},
            {"label": "Full name", "type": "string", "required": False, "hint": "", "quote": "", "page": 0, "form_target": "applicant.legal_name"},
        ],
    }


def test_create_type_makes_the_new_form_field_and_maps_it(new_type):
    upload, ops, category, suffix = new_type
    response = client.post(f"/api/ai/review/{upload}/create-type", json=type_body(category, suffix), headers={"X-Actor": ops})
    assert response.status_code == 201, response.text
    target = f"additional.card_number_{suffix}"
    with SessionLocal() as db:
        assert target in {f.target for f in sources.additional_fields(db)}
        definitions = db.execute(
            text("SELECT v.field_definitions FROM prompts p JOIN prompt_versions v ON v.id = p.active_version_id WHERE p.category = :c"), {"c": category}
        ).scalar_one()
        assert [d.get("form_target") for d in definitions] == [target, "applicant.legal_name"]
        entries = audit.list_entries(db, audit.SYSTEM_STREAM, limit=50)[1]
        assert any(e.action == "FORM_FIELD_ADDED" and e.target_id == target for e in entries)
        assert audit.verify_stream(db, audit.SYSTEM_STREAM).valid


def test_create_type_refuses_an_unknown_form_target(new_type):
    upload, ops, category, suffix = new_type
    body = type_body(category, suffix)
    body["fields"][1]["form_target"] = "applicant.shoe_size"
    assert client.post(f"/api/ai/review/{upload}/create-type", json=body, headers={"X-Actor": ops}).status_code == 422
    with SessionLocal() as db:
        assert not any(f.target.endswith(suffix) for f in sources.additional_fields(db))  # the refusal rolled the new field back
