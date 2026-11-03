import pytest

from app.ai import doctype_agent as agent, registry

PAGES = {1: "Name: Asha Rao\nUID Number: 1234 5678 9012\nDate of Birth: 01/02/1990"}


def raw(label: str, quote: str, page: int = 1, **over):
    return {"label": label, "type": "string", "required": True, "hint": "h", "quote": quote, "page": page} | over


def test_normalise_category():
    assert agent.normalise_category("national id card") == "NATIONAL_ID_CARD"
    assert agent.normalise_category("  uid-card!! ") == "UID_CARD"
    assert agent.normalise_category("12 card") == "DOC_12_CARD"


def test_category_rules():
    assert agent.category_error("UNKNOWN", set()) is not None
    assert agent.category_error("PASSPORT", {"PASSPORT"}) is not None
    assert agent.category_error("lower", set()) is not None
    assert agent.category_error("AADHAAR", {"PASSPORT"}) is None


def test_unused_category_numbers_a_clash():
    assert agent.unused_category("AADHAAR", {"PASSPORT"}) == "AADHAAR"
    assert agent.unused_category("AADHAAR", {"AADHAAR", "AADHAAR_2"}) == "AADHAAR_3"


def test_fields_keys_built_by_code_and_quotes_checked():
    fields = agent.build_fields("AADHAAR", [raw("Number", "1234 5678 9012"), raw("Invented", "not in the text")], PAGES, set())
    assert [f["key"] for f in fields] == ["AADHAAR.Number", "AADHAAR.Invented"]
    assert [f["verified"] for f in fields] == [True, False]


def test_fields_drop_empty_and_duplicate_labels_and_bad_types():
    fields = agent.build_fields("X", [raw("", "q"), raw("Name", "Asha Rao"), raw("name", "Asha Rao"), raw("Dob", "01/02/1990", type="blob")], PAGES, set())
    assert [f["label"] for f in fields] == ["Name", "Dob"] and fields[1]["type"] == "string"


def test_image_page_quote_is_never_verified():
    fields = agent.build_fields("X", [raw("Name", "Asha Rao", page=1)], PAGES, {1})
    assert fields[0]["verified"] is False and fields[0]["from_image"] is True


def test_schema_from_fields_matches_definitions():
    defs = agent.field_definitions(agent.build_fields("AADHAAR", [raw("Number", "1234"), raw("Dob", "x", required=False, type="date")], PAGES, set()))
    schema = registry.schema_from_fields("AADHAAR", defs)
    assert registry.validate_output_schema(schema) == ["AADHAAR.Number", "AADHAAR.Dob"]
    assert schema["properties"]["fields"]["required"] == ["AADHAAR.Number"]
    assert schema["properties"]["category"]["enum"] == ["AADHAAR"]
    row = registry.create_version([], None, {"system_text": "s", "user_template": "t", "model": "m", "effort": "low", "max_tokens": 10,
                                             "output_schema": schema, "field_definitions": defs, "tools": []})
    assert row["version"] == 1


def test_schema_from_fields_rejects_bad_definitions():
    with pytest.raises(registry.RegistryError):
        registry.schema_from_fields("X", [{"key": "X.a", "label": "a", "type": "string", "required": True}, {"key": "X.a", "label": "a", "type": "string", "required": True}])
