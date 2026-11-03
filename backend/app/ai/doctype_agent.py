"""Draft a new document type from one file no type fits.

Claude reads the extracted text and proposes a type. Code then builds the field keys, checks every quote against the
page text and builds the output schema. Nothing is stored here. A person reviews the draft and creates the type."""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ai import form_fields, reader, registry
from app.ai.client import STATUS_OK, CallResult, run_prompt
from app.ai.envelope import build_envelope
from app.ai.models import Prompt, PromptVersion
from app.core.errors import AppError
from app.ingest import service as ingest

DRAFT_KEY = "doc.type.draft"
RESERVED = (reader.UNKNOWN, reader.REVIEW)
FIELD_TYPES = ("string", "date", "number")
CATEGORY_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
MAX_FIELDS = 30
Call = Callable[[Mapping[str, Any], Mapping[str, Any]], CallResult]


@dataclass
class Draft:
    status: str = "NEEDS_REVIEW"
    error: str | None = None
    matches_existing: str | None = None
    matches_reason: str | None = None
    category: str = ""
    title: str = ""
    recognition_hint: str = ""
    system_text: str = ""
    injection_flag: bool = False
    fields: list[dict[str, Any]] = field(default_factory=list)
    prompt_run_id: int | None = None
    model: str = ""
    effort: str = ""
    max_tokens: int = 0


def normalise_category(raw: str) -> str:
    """NATIONAL ID card becomes NATIONAL_ID_CARD. Anything that does not start with a letter gets a DOC_ prefix."""
    name = re.sub(r"[^A-Z0-9]+", "_", str(raw).upper()).strip("_")
    return name if name[:1].isalpha() else f"DOC_{name}".strip("_")


def category_error(category: str, existing: set[str]) -> str | None:
    if not CATEGORY_NAME.match(category) or len(category) > 80:
        return "The name must use capital letters, digits and underscores and start with a letter"
    if category in RESERVED:
        return f"{category} is reserved"
    if category in existing:
        return f"{category} is already a document type"
    return None


def unused_category(category: str, existing: set[str]) -> str:
    """The category itself, or the first free numbered variant of it."""
    if category not in existing:
        return category
    number = 2
    while f"{category}_{number}" in existing:
        number += 1
    return f"{category}_{number}"


NEW_TARGET = "NEW"


def _target_of(raw_target: Any, label: str, known: set[str]) -> tuple[str | None, bool]:
    """The form target of a field and whether a new additional client field is needed. Code decides, so an unknown target
    from the model is dropped. NEW reuses an additional field that already has the same name."""
    if raw_target in known:
        return str(raw_target), False
    if raw_target != NEW_TARGET:
        return None, False
    same = form_fields.target_for(label)
    return (same, False) if same in known else (None, True)


def build_fields(category: str, raw_fields: list[Any], pages: Mapping[int, str], image_pages: set[int],
                 known_targets: set[str] | None = None) -> list[dict[str, Any]]:  # fmt: skip
    """One field per distinct label. The key is built here, never taken from the model. A quote counts only when code finds it."""
    known = known_targets or set()
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for raw in raw_fields[:MAX_FIELDS]:
        if not isinstance(raw, dict):
            continue
        label = " ".join(str(raw.get("label") or "").split())
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        page = raw.get("page") if isinstance(raw.get("page"), int) else 0
        quote = str(raw.get("quote") or "")
        kind = raw.get("type") if raw.get("type") in FIELD_TYPES else "string"
        target, is_new = _target_of(raw.get("form_target"), label, known)
        result.append({
            "key": f"{category}.{label}", "label": label, "type": kind, "required": bool(raw.get("required")),
            "hint": str(raw.get("hint") or ""), "quote": quote, "page": page,
            "from_image": page in image_pages,
            "verified": page not in image_pages and reader.verify_quote(quote, page, pages),
            "form_target": target, "new_form_field": is_new,
        })  # fmt: skip
    return result


def field_definitions(fields: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The registry shape of a field list. Quotes and pages are draft evidence and are not stored in the prompt."""
    return [
        {"key": f["key"], "label": f["label"], "type": f["type"], "required": bool(f["required"]), "hint": f.get("hint") or ""}
        | ({"form_target": f["form_target"]} if f.get("form_target") else {})
        for f in fields
    ]


def existing_categories(db: Session) -> set[str]:
    """Every category that has a read prompt, including disabled and deleted ones, because the key stays taken."""
    return {c for c in db.scalars(select(Prompt.category).where(Prompt.step == "read", Prompt.category.is_not(None)))}


def reference_version(db: Session) -> dict[str, Any] | None:
    """The settings a new read prompt copies: the template, model, effort, token limit and tools of a working read type."""
    row = db.execute(
        select(PromptVersion).join(Prompt, Prompt.active_version_id == PromptVersion.id).where(
            Prompt.step == "read", Prompt.category.is_not(None), Prompt.category != reader.UNKNOWN,
            Prompt.enabled.is_(True), Prompt.deleted_at.is_(None), Prompt.origin == "BUILT_IN",
            PromptVersion.field_definitions != [],
        ).order_by(Prompt.key).limit(1)
    ).scalar()
    if row is None:
        return None
    return {"user_template": row.user_template, "model": row.model, "effort": row.effort, "max_tokens": row.max_tokens, "tools": list(row.tools or [])}


def _candidates(db: Session, upload_id: str) -> str:
    """Labels the generic read already found, as a hint. Values are left out."""
    extracted = db.execute(
        text("SELECT extracted FROM document_reads WHERE upload_id = :u AND category = 'UNKNOWN' AND extracted IS NOT NULL ORDER BY read_at DESC, id DESC LIMIT 1"),
        {"u": upload_id},
    ).scalar()
    fields = (extracted or {}).get("fields") if isinstance(extracted, dict) else None
    labels = [str(k).split(".", 1)[-1] for k in (fields or {})]
    return "\n".join(f"- {label}" for label in labels) or "None."


def _target_list(targets: list[dict[str, str]]) -> str:
    return "\n".join(f"- {t['target']}: {t['label']} ({t['section']})" for t in targets)


def _default_call(version: Mapping[str, Any], variables: Mapping[str, Any], case_id: str | None) -> CallResult:
    return run_prompt(DRAFT_KEY, version, variables, input_text="", case_id=case_id)


def draft_type(db: Session, upload_id: str, *, call: Call | None = None) -> Draft:
    """Read the file and return a draft. On a refusal, an error or an unreadable file the draft says so and has no fields."""
    case_id = db.scalar(text("SELECT case_id FROM uploads WHERE upload_id = :u"), {"u": upload_id})
    if case_id is None:
        raise AppError("UPLOAD_NOT_FOUND", f"No upload {upload_id}", 404)
    loaded = ingest.load_pages(db, upload_id)
    if loaded is None or not loaded.pages:
        return Draft(error="The file could not be read. A person must set its type")
    version = reader.default_deps().get_version(DRAFT_KEY)
    if version is None:
        return Draft(error="The draft prompt is not available. Turn on doc.type.draft in the AI section")
    variables: dict[str, Any] = {
        "document_text": build_envelope(loaded.pages), "categories": reader.default_deps().categories(),
        "candidates": _candidates(db, upload_id), "form_targets": _target_list(form_fields.targets(db)),
    }
    if loaded.images:
        variables["images"] = sorted(loaded.images.items())
    send = call or (lambda v, x: _default_call(v, x, case_id))
    result = send(version, variables)
    if _blank(result):
        result = send(version, variables)
    if result.status != STATUS_OK or not isinstance(result.data, dict):
        return Draft(error="The AI could not draft a type. Fill it in by hand", prompt_run_id=result.run_id)
    if _blank(result):
        return Draft(error="The AI returned an empty draft. Try again or fill it in by hand", prompt_run_id=result.run_id)
    return _from_result(db, result, loaded)


def _blank(result: CallResult) -> bool:
    """True when a readable file came back with no category and no fields. The model sometimes answers the schema with empty
    values, so the draft is asked for once more."""
    data = result.data
    return (result.status == STATUS_OK and isinstance(data, dict) and data.get("legible") is not False
            and not str(data.get("category") or "").strip() and not data.get("fields"))  # fmt: skip


def _from_result(db: Session, result: CallResult, loaded: reader.LoadedUpload) -> Draft:
    data = result.data or {}
    existing = existing_categories(db)
    draft = Draft(prompt_run_id=result.run_id, injection_flag=bool(data.get("injection_flag")))
    if data.get("legible") is False:
        draft.error = "The text is too poor to draft a type"
        return draft
    match = normalise_category(data.get("matches_existing") or "")
    if match and match in existing and match not in RESERVED:
        draft.matches_existing, draft.matches_reason = match, str(data.get("matches_reason") or "")
    category = unused_category(normalise_category(data.get("category") or "") or "NEW_DOCUMENT", existing | set(RESERVED))
    image_pages = set(loaded.images)
    text_pages = {n: t for n, t in loaded.pages if n not in image_pages}
    ref = reference_version(db) or {}
    draft.status, draft.category = "OK", category
    draft.title = str(data.get("title") or category).strip()[:200]
    draft.recognition_hint = str(data.get("recognition_hint") or "").strip()
    draft.system_text = str(data.get("system_text") or "").strip()
    known = {t["target"] for t in form_fields.targets(db)}
    draft.fields = build_fields(category, data.get("fields") or [], text_pages, image_pages, known)
    draft.model, draft.effort, draft.max_tokens = ref.get("model", ""), ref.get("effort", ""), ref.get("max_tokens", 0)
    return draft


def build_prompt_data(db: Session, category: str, system_text: str, fields: list[Mapping[str, Any]], created_by: str) -> dict[str, Any]:
    """Everything a new read prompt version needs. The schema is built from the fields, so a client schema is never used."""
    ref = reference_version(db)
    if ref is None:
        raise AppError("NO_REFERENCE_PROMPT", "No working document type to copy the read settings from", 409)
    definitions = field_definitions(fields)
    return {
        **ref, "system_text": system_text, "field_definitions": definitions,
        "output_schema": registry.schema_from_fields(category, definitions),
        "note": "Created from an uploaded file with the document type agent", "created_by": created_by,
    }
