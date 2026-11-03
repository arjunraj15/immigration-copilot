"""Registry rules for array fields."""

import copy
from typing import Any

import pytest

from app.ai.registry import (
    FieldDefinitionError,
    KeyLockError,
    SchemaError,
    create_version,
    locked_key_violations,
    validate_field_definitions,
    validate_output_schema,
)

TEXT = {"type": "string"}


def scalar_def(key: str = "P.name") -> dict[str, Any]:
    return {"key": key, "label": key, "type": "string", "required": True, "hint": None}


def sub_def(key: str, **extra: Any) -> dict[str, Any]:
    return {"key": key, "label": key, "type": "string", "required": True, "hint": None} | extra


def array_def(key: str = "P.rows", items: Any = None) -> dict[str, Any]:
    subs = [sub_def("Label"), sub_def("Amount")] if items is None else items
    return {"key": key, "label": key, "type": "array", "required": False, "hint": None, "items": subs}


def scalar_schema() -> dict[str, Any]:
    return {"type": "object", "required": ["value", "quote", "page"],
            "properties": {"value": TEXT, "quote": TEXT, "page": {"type": "integer"}}}


def item_schema(subs: tuple[str, ...] = ("Label", "Amount"), require: tuple[str, ...] = ("quote", "page")) -> dict[str, Any]:
    props = {name: TEXT for name in subs} | {"quote": TEXT, "page": {"type": "integer"}}
    return {"type": "object", "required": [*subs, *require], "properties": props}


def array_schema(item: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": "object", "required": ["value"],
            "properties": {"value": {"type": "array", "items": item or item_schema()}}}


def output_schema(fields: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": {"fields": {"type": "object", "properties": fields}}}


def data(definitions: list[dict[str, Any]], schema: dict[str, Any]) -> dict[str, Any]:
    return {"system_text": "s", "user_template": "u", "model": "m", "effort": "low", "max_tokens": 10,
            "output_schema": schema, "field_definitions": definitions, "note": "", "created_by": "t"}


def good() -> dict[str, Any]:
    return data([scalar_def(), array_def()],
                output_schema({"P.name": scalar_schema(), "P.rows": array_schema()}))


def test_valid_array_definition_and_schema():
    row = create_version([], None, good())
    assert row["version"] == 1
    assert validate_field_definitions(row["field_definitions"]) == ["P.name", "P.rows"]
    assert validate_output_schema(row["output_schema"]) == ["P.name", "P.rows"]


def test_array_definition_needs_items():
    for bad in (None, [], "x"):
        with pytest.raises(FieldDefinitionError):
            validate_field_definitions([array_def() | {"items": bad}])


def test_items_only_allowed_on_array_type():
    with pytest.raises(FieldDefinitionError):
        validate_field_definitions([scalar_def() | {"items": [sub_def("a")]}])


def test_scalar_with_null_items_is_fine():
    assert validate_field_definitions([scalar_def() | {"items": None}]) == ["P.name"]


def test_item_definition_must_be_valid_and_unique():
    with pytest.raises(FieldDefinitionError):
        validate_field_definitions([array_def(items=[sub_def("a"), sub_def("a")])])
    with pytest.raises(FieldDefinitionError):
        validate_field_definitions([array_def(items=[{"key": "a"}])])


def test_item_keys_quote_and_page_are_reserved():
    for name in ("quote", "page"):
        with pytest.raises(FieldDefinitionError):
            validate_field_definitions([array_def(items=[sub_def(name)])])


def test_nested_array_in_definitions_rejected():
    with pytest.raises(FieldDefinitionError, match="one level"):
        validate_field_definitions([array_def(items=[sub_def("a", type="array", items=[sub_def("b")])])])
    with pytest.raises(FieldDefinitionError, match="one level"):
        validate_field_definitions([array_def(items=[sub_def("a", items=[sub_def("b")])])])


def test_item_missing_quote_rejected_by_schema():
    for missing in ("quote", "page"):
        item = item_schema()
        del item["properties"][missing]
        with pytest.raises(SchemaError, match=missing):
            validate_output_schema(output_schema({"P.rows": array_schema(item)}))


def test_item_quote_not_required_rejected():
    with pytest.raises(SchemaError, match="must require"):
        validate_output_schema(output_schema({"P.rows": array_schema(item_schema(require=("page",)))}))


def test_array_value_must_be_required_and_have_items():
    schema = array_schema()
    schema["required"] = []
    with pytest.raises(SchemaError, match="require 'value'"):
        validate_output_schema(output_schema({"P.rows": schema}))
    schema = array_schema()
    del schema["properties"]["value"]["items"]
    with pytest.raises(SchemaError, match="items"):
        validate_output_schema(output_schema({"P.rows": schema}))


def test_nested_array_in_schema_rejected():
    item = item_schema()
    item["properties"]["Inner"] = {"type": "array", "items": TEXT}
    with pytest.raises(SchemaError, match="one level"):
        validate_output_schema(output_schema({"P.rows": array_schema(item)}))
    item = item_schema()
    item["properties"]["Inner"] = {"type": "object", "properties": {}}
    with pytest.raises(SchemaError, match="one level"):
        validate_output_schema(output_schema({"P.rows": array_schema(item)}))


def test_schema_item_keys_must_match_definitions():
    payload = good()
    payload["output_schema"] = output_schema(
        {"P.name": scalar_schema(), "P.rows": array_schema(item_schema(("Label", "Other")))})
    with pytest.raises(SchemaError, match="items keys"):
        create_version([], None, payload)


def test_array_definition_with_scalar_schema_rejected():
    payload = data([array_def()], output_schema({"P.rows": scalar_schema()}))
    with pytest.raises(SchemaError):
        create_version([], None, payload)


def test_empty_array_is_allowed_by_the_schema():
    schema = array_schema()
    assert "minItems" not in schema["properties"]["value"]
    assert validate_output_schema(output_schema({"P.rows": schema})) == ["P.rows"]


# key lock


def test_key_lock_covers_array_item_keys():
    active = {"version": 1, "field_definitions": good()["field_definitions"]}
    dropped = copy.deepcopy(good())
    dropped["field_definitions"][1]["items"] = [sub_def("Label")]
    dropped["output_schema"] = output_schema(
        {"P.name": scalar_schema(), "P.rows": array_schema(item_schema(("Label",)))})
    with pytest.raises(KeyLockError, match=r"P\.rows\[\]\.Amount"):
        create_version([{"version": 1}], active, dropped)


def test_key_lock_allows_adding_an_item_key():
    active = {"version": 1, "field_definitions": good()["field_definitions"]}
    more = copy.deepcopy(good())
    more["field_definitions"][1]["items"].append(sub_def("Note", required=False))
    more["output_schema"] = output_schema(
        {"P.name": scalar_schema(), "P.rows": array_schema(item_schema(("Label", "Amount", "Note")))})
    assert create_version([{"version": 1}], active, more)["version"] == 2


def test_key_lock_blocks_removing_the_array_field():
    violations = locked_key_violations([array_def()], [scalar_def()])
    assert violations == ["P.rows", "P.rows[].Amount", "P.rows[].Label"]
