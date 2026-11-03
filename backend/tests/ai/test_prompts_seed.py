"""Static checks on the shipped prompts/*.yaml files."""

from pathlib import Path

import pytest
import yaml

from app.ai import registry, seed

APP_DIR = Path(seed.__file__).resolve().parents[1]
FILES = sorted(seed.PROMPTS_DIR.glob("*.yaml"))
CLASSIFY_VARS = {"categories", "document_text"}
READ_VARS = {"document_text", "category", "field_definitions"}


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_every_prompt_file_is_counted():
    assert len(FILES) >= 11


def test_keys_are_unique():
    keys = [load(p)["key"] for p in FILES]
    assert len(set(keys)) == len(FILES)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_yaml_is_valid_for_the_registry(path):
    data = load(path)
    for name in ("key", "step", "title", "system_text", "user_template", "model", "effort", "max_tokens",
                 "output_schema", "field_definitions"):
        assert data.get(name) not in (None, ""), name or "empty"
    assert data["step"] in ("classify", "read", "other")
    assert data["max_tokens"] > 0
    row = registry.create_version([], None, {k: data.get(k) for k in seed._VERSION_FIELDS} | {"created_by": "t"})
    assert row["version"] == 1


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_only_variables_the_reader_supplies(path):
    data = load(path)
    if data["step"] == "other":
        return  # Analysis prompts supply their own variables.
    allowed = CLASSIFY_VARS if data["step"] == "classify" else READ_VARS
    used = set(registry.template_variables(data["system_text"])) | set(registry.template_variables(data["user_template"]))
    assert used <= allowed, used - allowed
    assert "document_text" in registry.template_variables(data["user_template"])


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_templates_render_with_reader_variables(path):
    data = load(path)
    if data["step"] == "other":
        return
    variables = {"categories": "c", "document_text": "d", "category": "X", "field_definitions": "f"}
    registry.render_template(data["system_text"], variables)
    registry.render_template(data["user_template"], variables)


def value_schemas(schema):
    """Yield every object schema that holds a value, quote and page."""
    if isinstance(schema, dict):
        props = schema.get("properties")
        if isinstance(props, dict) and "quote" in props:
            yield schema
        for child in schema.values():
            yield from value_schemas(child)
    elif isinstance(schema, list):
        for child in schema:
            yield from value_schemas(child)


@pytest.mark.parametrize("path", [p for p in FILES if load(p)["step"] == "read"], ids=lambda p: p.name)
def test_every_read_schema_requires_quote_and_page(path):
    data = load(path)
    fields = data["output_schema"]["properties"]["fields"]
    if data["field_definitions"]:
        keys = registry.validate_output_schema(data["output_schema"])
        assert sorted(keys) == sorted(d["key"] for d in data["field_definitions"])
        assert keys
        for key in keys:
            schema = fields["properties"][key]
            item = schema["properties"]["value"].get("items") if schema["properties"]["value"]["type"] == "array" else schema
            assert {"quote", "page"} <= set(item["required"])
        return
    assert fields["type"] == "array"
    assert registry.validate_output_schema(data["output_schema"]) == []
    value = fields["items"]
    assert fields.get("additionalProperties") is None
    assert value["additionalProperties"] is False
    assert {"label"} <= set(value["required"])
    assert {"value", "quote", "page"} <= set(value["required"])
    assert {"quote", "page"} <= set(value["properties"])


def test_classify_owner_names_require_quote_and_page():
    schemas = list(value_schemas(load(seed.PROMPTS_DIR / "classify.yaml")["output_schema"]))
    assert schemas
    for schema in schemas:
        assert {"quote", "page"} <= set(schema["required"])


def test_read_prompts_match_category_and_key():
    for path in FILES:
        data = load(path)
        if data["step"] == "read":
            assert data["key"] == f"doc.read.{data['category'].lower()}" or data["key"] == "doc.read.generic"


def test_no_hardcoded_prompt_text_in_python_modules():
    needles = []
    for path in FILES:
        data = load(path)
        for text in (data["system_text"], data["user_template"]):
            needles += [line.strip() for line in text.splitlines() if len(line.strip()) >= 40]
    sources = {p: p.read_text(encoding="utf-8") for p in APP_DIR.rglob("*.py")}
    hits = [(p.name, n[:50]) for p, src in sources.items() for n in needles if n in src]
    assert hits == []


@pytest.mark.parametrize("path", [p for p in FILES if load(p)["step"] == "read" and load(p)["field_definitions"]],
                         ids=lambda p: p.name)
def test_required_definitions_are_in_the_fields_required_list(path):
    data = load(path)
    fields = data["output_schema"]["properties"]["fields"]
    wanted = {d["key"] for d in data["field_definitions"] if d["required"]}
    assert wanted
    assert set(fields["required"]) == wanted


def test_a_seed_prompt_has_a_real_array_field():
    data = load(seed.PROMPTS_DIR / "read_passport.yaml")
    arrays = [d for d in data["field_definitions"] if d["type"] == "array"]
    assert arrays
    assert registry.array_item_keys(data["output_schema"]) == registry.definition_item_keys(arrays)
    assert not any(d["required"] for d in arrays)
