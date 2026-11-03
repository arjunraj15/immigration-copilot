import copy
from typing import Any

import pytest

from app.ai.registry import (
    FieldDefinitionError,
    KeyLockError,
    MissingVariableError,
    SchemaError,
    VersionError,
    activate_version,
    create_version,
    locked_key_violations,
    next_version_number,
    render_template,
    rollback_version,
    template_variables,
    validate_field_definitions,
    validate_output_schema,
)


def _definition(key: str, **overrides: Any) -> dict[str, Any]:
    base = {"key": key, "label": str(key), "type": "string", "required": True, "hint": None}
    base.update(overrides)
    return base


def _value_schema(*, quote: bool = True, page: bool = True, require: bool = True) -> dict[str, Any]:
    props: dict[str, Any] = {"value": {"type": "string"}}
    required = ["value"]
    if quote:
        props["quote"] = {"type": "string"}
        if require:
            required.append("quote")
    if page:
        props["page"] = {"type": "integer"}
        if require:
            required.append("page")
    return {"type": "object", "properties": props, "required": required}


def _schema(keys: list[str], value_schema: dict[str, Any] | None = None) -> dict[str, Any]:
    value = value_schema or _value_schema()
    return {
        "type": "object",
        "properties": {
            "fields": {
                "type": "object",
                "properties": {key: copy.deepcopy(value) for key in keys},
            }
        },
    }


def _data(keys: list[str], **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "system_text": "system",
        "user_template": "read {{doc}}",
        "model": "claude-sonnet-5-5",
        "effort": "low",
        "max_tokens": 1024,
        "output_schema": _schema(keys),
        "field_definitions": [_definition(k) for k in keys],
        "note": "",
        "created_by": "tester",
    }
    data.update(overrides)
    return data


# render_template


def test_render_replaces_placeholders() -> None:
    assert render_template("Hi {{name}}, page {{ page }}", {"name": "Ana", "page": 2}) == (
        "Hi Ana, page 2"
    )


def test_render_missing_variable_raises_and_names_all_missing() -> None:
    with pytest.raises(MissingVariableError) as info:
        render_template("{{a}} {{b}} {{c}} {{a}}", {"b": 1})
    assert str(info.value) == "Missing template variables: a, c"


def test_render_extra_variables_are_ignored() -> None:
    assert render_template("{{a}}", {"a": "x", "unused": "y", "other": 3}) == "x"


def test_render_value_containing_placeholder_is_not_expanded() -> None:
    out = render_template("A={{a}} B={{b}}", {"a": "{{b}}", "b": "secret"})
    assert out == "A={{b}} B=secret"


def test_render_value_containing_placeholder_with_no_matching_key_stays_literal() -> None:
    assert render_template("{{a}}", {"a": "{{missing}}"}) == "{{missing}}"


def test_render_does_not_execute_import_payload() -> None:
    payload = "{{__import__('os').system('id')}}"
    assert render_template(payload, {}) == payload
    with pytest.raises(MissingVariableError):
        render_template("{{__import__}}", {})


def test_render_dunder_name_is_plain_text_when_supplied() -> None:
    assert render_template("{{__import__}}", {"__import__": "safe"}) == "safe"


def test_render_leaves_jinja_style_blocks_untouched() -> None:
    template = "{% for x in items %}{{ x }}{% endfor %} {{ __class__ }}"
    assert render_template(template, {"x": "1", "__class__": "C"}) == (
        "{% for x in items %}1{% endfor %} C"
    )


def test_render_repeated_placeholder_replaced_everywhere() -> None:
    assert render_template("{{x}}-{{x}}-{{x}}", {"x": 7}) == "7-7-7"


def test_template_variables_sorted_unique() -> None:
    assert template_variables("{{b}} {{a}} {{b}} {{ c }}") == ["a", "b", "c"]


# field definitions


def test_field_definitions_valid_returns_keys() -> None:
    assert validate_field_definitions([_definition("a"), _definition("b")]) == ["a", "b"]


def test_field_definitions_empty_list_is_accepted() -> None:
    assert validate_field_definitions([]) == []


def test_field_definitions_not_a_list_rejected() -> None:
    with pytest.raises(FieldDefinitionError):
        validate_field_definitions({"key": "a"})


def test_field_definitions_duplicate_key_rejected() -> None:
    with pytest.raises(FieldDefinitionError, match="duplicate"):
        validate_field_definitions([_definition("a"), _definition("a")])


def test_field_definitions_missing_key_rejected() -> None:
    item = _definition("a")
    del item["key"]
    with pytest.raises(FieldDefinitionError, match="key"):
        validate_field_definitions([item])


@pytest.mark.parametrize("bad_key", ["", "   ", 5, None])
def test_field_definitions_bad_key_rejected(bad_key: Any) -> None:
    with pytest.raises(FieldDefinitionError):
        validate_field_definitions([_definition(bad_key)])


@pytest.mark.parametrize("bad_type", [123, "", "   ", None])
def test_field_definitions_bad_type_rejected(bad_type: Any) -> None:
    with pytest.raises(FieldDefinitionError, match="type"):
        validate_field_definitions([_definition("a", type=bad_type)])


def test_field_definitions_required_must_be_bool() -> None:
    with pytest.raises(FieldDefinitionError, match="required"):
        validate_field_definitions([_definition("a", required="yes")])


def test_field_definitions_hint_must_be_string_or_null() -> None:
    assert validate_field_definitions([_definition("a", hint=None)]) == ["a"]
    with pytest.raises(FieldDefinitionError, match="hint"):
        validate_field_definitions([_definition("a", hint=42)])


def test_field_definitions_item_must_be_object() -> None:
    with pytest.raises(FieldDefinitionError):
        validate_field_definitions(["a"])


# output schema


def test_schema_valid_returns_field_keys() -> None:
    assert validate_output_schema(_schema(["a", "b"])) == ["a", "b"]


def test_schema_field_missing_quote_rejected() -> None:
    schema = _schema(["a"], _value_schema(quote=False))
    with pytest.raises(SchemaError, match="quote"):
        validate_output_schema(schema)


def test_schema_field_missing_page_rejected() -> None:
    schema = _schema(["a"], _value_schema(page=False))
    with pytest.raises(SchemaError, match="page"):
        validate_output_schema(schema)


def test_schema_field_with_neither_quote_nor_page_rejected() -> None:
    schema = _schema(["a"], _value_schema(quote=False, page=False))
    with pytest.raises(SchemaError):
        validate_output_schema(schema)


def test_schema_quote_declared_but_not_required_rejected() -> None:
    schema = _schema(["a"], _value_schema(require=False))
    with pytest.raises(SchemaError, match="must require"):
        validate_output_schema(schema)


def test_schema_field_value_not_object_rejected() -> None:
    schema = _schema(["a"])
    schema["properties"]["fields"]["properties"]["a"] = "string"
    with pytest.raises(SchemaError):
        validate_output_schema(schema)


def test_schema_without_fields_rejected() -> None:
    with pytest.raises(SchemaError):
        validate_output_schema({"properties": {}})
    with pytest.raises(SchemaError):
        validate_output_schema("not a schema")


def test_schema_non_object_properties_raises_schema_error() -> None:
    with pytest.raises(SchemaError):
        validate_output_schema({"properties": "oops"})


# key lock and versions


def test_key_lock_removing_active_key_rejected() -> None:
    active = {"field_definitions": [_definition("a"), _definition("b")]}
    with pytest.raises(KeyLockError, match="b"):
        create_version([], active, _data(["a"]))


def test_key_lock_renaming_active_key_rejected() -> None:
    active = {"field_definitions": [_definition("a"), _definition("b")]}
    with pytest.raises(KeyLockError, match="b"):
        create_version([], active, _data(["a", "c"]))


def test_key_lock_adding_new_key_allowed() -> None:
    active = {"field_definitions": [_definition("a")]}
    row = create_version([], active, _data(["a", "new_key"]))
    assert row["version"] == 1
    assert row["field_definitions"][1]["key"] == "new_key"


def test_key_lock_with_no_active_version_allows_anything() -> None:
    assert locked_key_violations(None, [_definition("x")]) == []
    assert locked_key_violations([], [_definition("x")]) == []
    row = create_version([], None, _data(["x"]))
    assert row["field_definitions"][0]["key"] == "x"


def test_key_lock_violations_lists_removed_keys_sorted() -> None:
    active = [_definition("z"), _definition("a"), _definition("m")]
    assert locked_key_violations(active, [_definition("m")]) == ["a", "z"]


def test_empty_field_list_with_object_schema_is_accepted() -> None:
    row = create_version([], None, _data([]))
    assert row["version"] == 1


def test_empty_field_list_with_non_object_schema_rejected() -> None:
    with pytest.raises(SchemaError, match="must be an object"):
        create_version([], None, _data([], output_schema="nope"))


def test_empty_field_list_drops_all_active_keys_and_is_rejected() -> None:
    active = {"field_definitions": [_definition("a")]}
    with pytest.raises(KeyLockError):
        create_version([], active, _data([]))


def test_create_version_increments_number() -> None:
    assert next_version_number([]) == 1
    assert next_version_number([1, 2, 5]) == 6
    row = create_version([{"version": 1}, {"version": 2}], None, _data(["a"]))
    assert row["version"] == 3


def test_create_version_inputs_not_mutated() -> None:
    existing = [{"id": 1, "version": 1, "system_text": "old"}]
    active = {"id": 1, "version": 1, "field_definitions": [_definition("a")]}
    data = _data(["a", "b"])
    snapshot = (copy.deepcopy(existing), copy.deepcopy(active), copy.deepcopy(data))
    row = create_version(existing, active, data)
    assert (existing, active, data) == snapshot
    assert row is not data
    assert row["version"] == 2


def test_create_version_invalid_schema_mismatch_rejected() -> None:
    data = _data(["a"], output_schema=_schema(["a", "b"]))
    with pytest.raises(SchemaError, match="must match"):
        create_version([], None, data)


def test_activate_version_returns_copy_pointing_at_target() -> None:
    prompt = {"id": 9, "active_version_id": 1}
    versions = [{"id": 1, "version": 1}, {"id": 2, "version": 2}]
    updated = activate_version(prompt, versions, 2)
    assert updated["active_version_id"] == 2
    assert prompt["active_version_id"] == 1


def test_activate_unknown_version_fails() -> None:
    prompt = {"id": 9, "active_version_id": 1}
    with pytest.raises(VersionError):
        activate_version(prompt, [{"id": 1, "version": 1}], 4)


def test_rollback_to_older_version_succeeds() -> None:
    prompt = {"id": 9, "active_version_id": 3}
    versions = [{"id": 1, "version": 1}, {"id": 2, "version": 2}, {"id": 3, "version": 3}]
    updated = rollback_version(prompt, versions, 1)
    assert updated["active_version_id"] == 1
    assert prompt["active_version_id"] == 3


def test_rollback_to_newer_version_fails() -> None:
    prompt = {"id": 9, "active_version_id": 2}
    versions = [{"id": 1, "version": 1}, {"id": 2, "version": 2}, {"id": 3, "version": 3}]
    with pytest.raises(VersionError, match="older"):
        rollback_version(prompt, versions, 3)


def test_rollback_to_active_version_fails() -> None:
    prompt = {"id": 9, "active_version_id": 2}
    versions = [{"id": 1, "version": 1}, {"id": 2, "version": 2}]
    with pytest.raises(VersionError):
        rollback_version(prompt, versions, 2)


def test_rollback_to_unknown_version_fails() -> None:
    prompt = {"id": 9, "active_version_id": 2}
    versions = [{"id": 1, "version": 1}, {"id": 2, "version": 2}]
    with pytest.raises(VersionError):
        rollback_version(prompt, versions, 0)


def _array_schema(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": {"fields": {"type": "array", "items": item}}}


def test_schema_fields_array_with_quote_and_page_is_accepted() -> None:
    item = _value_schema()
    item["properties"]["label"] = {"type": "string"}
    assert validate_output_schema(_array_schema(item)) == []


def test_schema_fields_array_items_must_require_quote_and_page() -> None:
    with pytest.raises(SchemaError):
        validate_output_schema(_array_schema(_value_schema(require=False)))
    with pytest.raises(SchemaError):
        validate_output_schema(_array_schema(_value_schema(page=False)))
    with pytest.raises(SchemaError):
        validate_output_schema(_array_schema({"type": "string"}))


def test_create_version_checks_array_fields_without_definitions() -> None:
    bad = _data([], output_schema=_array_schema(_value_schema(require=False)))
    with pytest.raises(SchemaError):
        create_version([], None, bad)
    assert create_version([], None, _data([], output_schema=_array_schema(_value_schema())))["version"] == 1


def _target_definition(**extra: Any) -> dict[str, Any]:
    return {"key": "PASSPORT.Expires", "label": "Expiry date", "type": "date", "required": True} | extra


def test_form_target_is_optional_and_checked_for_shape() -> None:
    from app.ai.registry import FieldDefinitionError, validate_field_definitions

    assert validate_field_definitions([_target_definition()]) == ["PASSPORT.Expires"]
    assert validate_field_definitions([_target_definition(form_target="applicant.passport_expiration")]) == ["PASSPORT.Expires"]
    for bad in ("", " x", 5):
        with pytest.raises(FieldDefinitionError):
            validate_field_definitions([_target_definition(form_target=bad)])


def test_form_target_is_refused_on_an_array_field() -> None:
    from app.ai.registry import FieldDefinitionError, validate_field_definitions

    array = _target_definition(type="array", form_target="applicant.legal_name", items=[{"key": "Applicant", "label": "A", "type": "string", "required": True}])
    with pytest.raises(FieldDefinitionError):
        validate_field_definitions([array])
