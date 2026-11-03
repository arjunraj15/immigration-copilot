"""Pure prompt registry logic.

Everything here works on plain dicts and lists. No database session, no
imports from models or schemas. The caller loads rows, passes them in and
persists whatever comes back.
"""

import re
from typing import Any, Iterable, Mapping

from app.ai.doc_tools import unknown_tools

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_REQUIRED_VALUE_PROPS = ("quote", "page")
_ARRAY = "array"
_NESTED_SCHEMA_TYPES = ("array", "object")


class RegistryError(ValueError):
    """Base error for registry rule violations."""


class MissingVariableError(RegistryError):
    pass


class SchemaError(RegistryError):
    pass


class FieldDefinitionError(RegistryError):
    pass


class ToolError(RegistryError):
    pass


class KeyLockError(RegistryError):
    pass


class VersionError(RegistryError):
    pass


def render_template(template: str, variables: Mapping[str, Any]) -> str:
    """Replace {{var}} placeholders in a single pass.

    Values are inserted as plain text and never expanded again. Missing
    variables raise MissingVariableError naming all of them.
    """
    missing = sorted({m for m in _PLACEHOLDER.findall(template) if m not in variables})
    if missing:
        raise MissingVariableError("Missing template variables: " + ", ".join(missing))
    return _PLACEHOLDER.sub(lambda m: str(variables[m.group(1)]), template)


def template_variables(template: str) -> list[str]:
    """Return the sorted placeholder names used by a template."""
    return sorted(set(_PLACEHOLDER.findall(template)))


def validate_field_definitions(field_definitions: Any) -> list[str]:
    """Check the list of {key, label, type, required, hint, form_target}. Returns the keys."""
    if not isinstance(field_definitions, list):
        raise FieldDefinitionError("field_definitions must be a list")
    keys: list[str] = []
    for index, item in enumerate(field_definitions):
        keys.append(_check_definition(index, item, keys))
    return keys


def _check_definition(index: int, item: Any, seen: list[str]) -> str:
    where = f"field_definitions[{index}]"
    key = _check_base_definition(where, item, seen)
    target = item.get("form_target")
    if target is not None and (not isinstance(target, str) or not target.strip() or target != target.strip()):
        raise FieldDefinitionError(f"{where}.form_target must be a non-empty string or left out")
    if target is not None and item["type"] == _ARRAY:
        raise FieldDefinitionError(f"{where}.form_target is not allowed on an array field")
    if item["type"] == _ARRAY:
        _check_item_definitions(where, item.get("items"))
    elif item.get("items") is not None:
        raise FieldDefinitionError(f"{where}.items is only allowed when type is array")
    return key


def _check_base_definition(where: str, item: Any, seen: list[str]) -> str:
    if not isinstance(item, dict):
        raise FieldDefinitionError(f"{where} must be an object")
    key = item.get("key")
    if not isinstance(key, str) or not key.strip() or key != key.strip():
        raise FieldDefinitionError(f"{where}.key must be a non-empty string without leading or trailing spaces")
    if key in seen:
        raise FieldDefinitionError(f"{where}.key is a duplicate: {key}")
    for name in ("label", "type"):
        if not isinstance(item.get(name), str) or not item[name].strip():
            raise FieldDefinitionError(f"{where}.{name} must be a non-empty string")
    if not isinstance(item.get("required"), bool):
        raise FieldDefinitionError(f"{where}.required must be true or false")
    if "hint" in item and item["hint"] is not None and not isinstance(item["hint"], str):
        raise FieldDefinitionError(f"{where}.hint must be a string")
    return key


def _check_item_definitions(where: str, items: Any) -> None:
    """An array field needs a non-empty list of scalar sub-fields. Only one level of nesting is allowed."""
    if not isinstance(items, list) or not items:
        raise FieldDefinitionError(f"{where}.items must be a non-empty list of sub-field definitions")
    seen: list[str] = []
    for index, sub in enumerate(items):
        sub_where = f"{where}.items[{index}]"
        key = _check_base_definition(sub_where, sub, seen)
        if sub["type"] == _ARRAY or sub.get("items") is not None:
            raise FieldDefinitionError(f"{sub_where} cannot be an array. Only one level of nesting is allowed")
        if key in _REQUIRED_VALUE_PROPS:
            raise FieldDefinitionError(f"{sub_where}.key cannot be '{key}', it is added to every item")
        seen.append(key)


_SCALAR_JSON_TYPES = {"number": "number", "boolean": "boolean"}


def _value_schema(definition: Mapping[str, Any]) -> dict[str, Any]:
    """One extracted field as {value, quote, page}. An array field holds one object per row, each with its own quote and page."""
    if definition.get("type") == _ARRAY:
        item_props: dict[str, Any] = {name: {"type": "string"} if name != "page" else {"type": "integer"} for name in _REQUIRED_VALUE_PROPS}
        for item in definition.get("items") or []:
            item_props[item["key"]] = {"type": _SCALAR_JSON_TYPES.get(item["type"], "string")}
        required = [i["key"] for i in definition.get("items") or [] if i.get("required")] + list(_REQUIRED_VALUE_PROPS)
        row = {"type": "object", "additionalProperties": False, "required": required, "properties": item_props}
        return {"type": "object", "additionalProperties": False, "required": ["value"], "properties": {"value": {"type": _ARRAY, "items": row}}}
    value_type = _SCALAR_JSON_TYPES.get(definition.get("type"), "string")
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["value", *_REQUIRED_VALUE_PROPS],
        "properties": {"value": {"type": value_type}, "quote": {"type": "string"}, "page": {"type": "integer"}},
    }


def build_output_schema(category: str, field_definitions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The output schema of a document type, derived from its field definitions so the two can never drift apart.
    Required fields are always returned. Optional ones may be left out. Every value carries a quote and a page."""
    definitions = list(field_definitions)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["category", "language", "legible", "injection_flag", "fields"],
        "properties": {
            "category": {"type": "string", "enum": [category]},
            "language": {"type": "string"},
            "legible": {"type": "boolean"},
            "injection_flag": {"type": "boolean"},
            "fields": {
                "type": "object",
                "additionalProperties": False,
                "required": [d["key"] for d in definitions if d.get("required")],
                "properties": {d["key"]: _value_schema(d) for d in definitions},
            },
        },
    }


def validate_output_schema(output_schema: Any) -> list[str]:
    """Reject a schema whose field value objects lack quote and page.

    Expects schema.properties.fields.properties.<key> to be an object schema
    that declares quote and page in both properties and required. The generic
    read instead uses a fields array whose items declare quote and page, and
    returns no keys because its keys come from the document labels.
    Returns the field keys found.
    """
    if not isinstance(output_schema, dict):
        raise SchemaError("output_schema must be an object")
    top = output_schema.get("properties")
    if not isinstance(top, dict):
        raise SchemaError("output_schema must define properties")
    fields = top.get("fields")
    if not isinstance(fields, dict):
        raise SchemaError("output_schema must define properties.fields")
    if fields.get("type") == "array":
        _check_value_schema("items", fields.get("items"))
        return []
    props = fields.get("properties")
    if not isinstance(props, dict):
        raise SchemaError("properties.fields must define properties")
    for key, value_schema in props.items():
        _check_value_schema(key, value_schema)
    return list(props)


def _has_array_fields(output_schema: Mapping[str, Any]) -> bool:
    props = output_schema.get("properties")
    fields = props.get("fields") if isinstance(props, dict) else None
    return isinstance(fields, dict) and fields.get("type") == "array"


def _check_value_schema(key: str, value_schema: Any) -> None:
    if not isinstance(value_schema, dict):
        raise SchemaError(f"Field {key} must be an object schema")
    declared = value_schema.get("properties")
    required = value_schema.get("required")
    declared = declared if isinstance(declared, dict) else {}
    required = required if isinstance(required, list) else []
    if _is_array_value(declared):
        _check_array_value(key, declared, required)
        return
    for name in _REQUIRED_VALUE_PROPS:
        if name not in declared:
            raise SchemaError(f"Field {key} is missing '{name}'")
        if name not in required:
            raise SchemaError(f"Field {key} must require '{name}'")


def _is_array_value(declared: Mapping[str, Any]) -> bool:
    value = declared.get("value")
    return isinstance(value, dict) and value.get("type") == _ARRAY


def _check_array_value(key: str, declared: Mapping[str, Any], required: list[Any]) -> None:
    """An array field is {value: [item, ...]}. Every item must declare and require quote and page."""
    if "value" not in required:
        raise SchemaError(f"Field {key} must require 'value'")
    item = declared["value"].get("items")
    if not isinstance(item, dict):
        raise SchemaError(f"Field {key} array must define items")
    for name, sub in (item.get("properties") or {}).items():
        if isinstance(sub, dict) and (sub.get("type") in _NESTED_SCHEMA_TYPES or "items" in sub or "properties" in sub):
            raise SchemaError(f"Field {key} item '{name}' is nested. Only one level of nesting is allowed")
    _check_value_schema(f"{key} item", item)


def array_item_keys(output_schema: Mapping[str, Any]) -> dict[str, set[str]]:
    """Map each array field key in a validated schema to its item sub-keys, without quote and page."""
    props = output_schema["properties"]["fields"].get("properties") or {}
    result: dict[str, set[str]] = {}
    for key, value_schema in props.items():
        declared = value_schema.get("properties") or {}
        if _is_array_value(declared):
            sub = declared["value"]["items"].get("properties") or {}
            result[key] = set(sub) - set(_REQUIRED_VALUE_PROPS)
    return result


def definition_item_keys(definitions: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    """Map each array field key in the definitions to its item sub-keys."""
    return {d["key"]: {s["key"] for s in d["items"]} for d in definitions if d.get("type") == _ARRAY}


def _lockable_names(definitions: Iterable[Mapping[str, Any]]) -> set[str]:
    """Field keys plus array item keys written as <field>[].<item>."""
    names: set[str] = set()
    for d in definitions:
        names.add(d["key"])
        names.update(f"{d['key']}[].{s['key']}" for s in d.get("items") or [])
    return names


def locked_key_violations(
    active_definitions: Iterable[Mapping[str, Any]] | None,
    new_definitions: Iterable[Mapping[str, Any]],
) -> list[str]:
    """Keys in the active version that the new version removes or renames. Array item keys are included."""
    if not active_definitions:
        return []
    return sorted(_lockable_names(active_definitions) - _lockable_names(new_definitions))


def next_version_number(existing_versions: Iterable[int]) -> int:
    """Auto-increment per prompt. First version is 1."""
    return max(existing_versions, default=0) + 1


def create_version(
    existing_versions: list[Mapping[str, Any]],
    active_version: Mapping[str, Any] | None,
    data: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the next insert-only version row as a new dict.

    existing_versions are all versions of this prompt, each with a 'version'
    number. active_version is the currently active one or None. data holds
    the editable fields: system_text, user_template, model, effort,
    max_tokens, output_schema, field_definitions, note, created_by.
    Nothing passed in is modified.
    """
    definitions = data.get("field_definitions")
    new_keys = validate_field_definitions(definitions)
    if new_keys:
        schema_keys = validate_output_schema(data.get("output_schema"))
        if set(schema_keys) != set(new_keys):
            raise SchemaError("output_schema fields must match field_definitions keys")
        if array_item_keys(data["output_schema"]) != definition_item_keys(definitions):
            raise SchemaError("output_schema array items must match field_definitions items keys")
    elif not isinstance(data.get("output_schema"), dict):
        raise SchemaError("output_schema must be an object")
    elif _has_array_fields(data["output_schema"]):
        validate_output_schema(data["output_schema"])
    removed = locked_key_violations(
        (active_version or {}).get("field_definitions"), definitions
    )
    if removed:
        raise KeyLockError("Keys in the active version cannot be removed or renamed: " + ", ".join(removed))
    tools = data.get("tools") or []
    if bad := unknown_tools(tools):
        raise ToolError("Unknown tools: " + ", ".join(bad))
    row = dict(data)
    row["tools"] = list(dict.fromkeys(tools))
    row["version"] = next_version_number(v["version"] for v in existing_versions)
    return row


def activate_version(
    prompt: Mapping[str, Any],
    versions: Iterable[Mapping[str, Any]],
    version: int,
) -> dict[str, Any]:
    """Return a copy of the prompt pointing at the given version number.

    Works for both a forward activation and a rollback. Versions are never
    edited or deleted.
    """
    target = next((v for v in versions if v["version"] == version), None)
    if target is None:
        raise VersionError(f"Version {version} does not exist")
    updated = dict(prompt)
    updated["active_version_id"] = target["id"]
    return updated


def rollback_version(
    prompt: Mapping[str, Any],
    versions: list[Mapping[str, Any]],
    version: int,
) -> dict[str, Any]:
    """Activate an earlier version. The target must be older than the active one."""
    active = next((v for v in versions if v["id"] == prompt.get("active_version_id")), None)
    if active is not None and version >= active["version"]:
        raise VersionError("Rollback target must be older than the active version")
    return activate_version(prompt, versions, version)


def _value_schema(definition: Mapping[str, Any]) -> dict[str, Any]:
    """One field value object. Every value carries its quote and page. Numbers stay text so they are copied as written."""
    if definition.get("type") == _ARRAY:
        item_props = {s["key"]: {"type": "string"} for s in definition["items"]}
        item_props |= {"quote": {"type": "string"}, "page": {"type": "integer"}}
        item = {"type": "object", "additionalProperties": False, "required": list(item_props), "properties": item_props}
        value: dict[str, Any] = {"type": "array", "items": item}
    else:
        value = {"type": "string"}
    props = {"value": value, "quote": {"type": "string"}, "page": {"type": "integer"}}
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def schema_from_fields(category: str, field_definitions: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Build the output schema of a read prompt from its field definitions, in the shape the seeded read prompts use.

    The required list holds the fields marked required, so the schema and the definitions always agree.
    """
    keys = validate_field_definitions(list(field_definitions))
    props = {d["key"]: _value_schema(d) for d in field_definitions}
    required = [d["key"] for d in field_definitions if d["required"]]
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["category", "language", "legible", "injection_flag", "fields"],
        "properties": {
            "category": {"type": "string", "enum": [category]},
            "language": {"type": "string"},
            "legible": {"type": "boolean"},
            "injection_flag": {"type": "boolean"},
            "fields": {"type": "object", "additionalProperties": False, "required": required, "properties": props},
        },
    }
    if set(validate_output_schema(schema)) != set(keys):
        raise SchemaError("output_schema fields must match field_definitions keys")
    return schema
