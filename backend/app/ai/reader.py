"""read_document: classify, route pages by category, read in parallel, verify quotes.

Every dependency (upload loading, prompt lookup, the Claude call, the cache) is
injectable so tests can run without a database or network.
"""

import hashlib
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Mapping, MutableMapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select

from app.ai.client import STATUS_ERROR, STATUS_OK, CallResult, ClaudeCall, run_prompt
from app.ai.doc_tools import DocTools
from app.ai.envelope import build_envelope
from app.ai.models import Prompt, PromptVersion
from app.core.contracts import DocumentRead, ReadField, ReadItem, ReadStatus
from app.core.errors import AppError
from app.db.session import SessionLocal

CLASSIFY_KEY = "doc.classify"
GENERIC_KEY = "doc.read.generic"
UNKNOWN = "UNKNOWN"
REVIEW = "REVIEW_REQUIRED"

Pages = list[tuple[int, str]]


# Stands in for the text of a scanned page. The page image goes with the call, inside the same page marker.
IMAGE_PAGE_TEXT = "[Scanned page with no text layer. Read the attached image of this page number.]"


@dataclass
class LoadedUpload:
    """pages holds every page sent. Pages listed in images are scanned, so their text is only a stand-in."""

    sha256: str
    pages: Pages
    images: dict[int, bytes] = field(default_factory=dict)
    category: str | None = None  # set when code already knows the type, so the classify call is skipped


@dataclass
class ReaderDeps:
    load_upload: Callable[[int], LoadedUpload]
    get_version: Callable[[str], Mapping[str, Any] | None]
    categories: Callable[[], str]
    call: ClaudeCall | None = None
    cache: MutableMapping[tuple, CallResult] = field(default_factory=dict)
    as_of: Callable[[], date] | None = None  # the review date. When set, read prompts may call the date tools


_CACHE: MutableMapping[tuple, CallResult] = {}


def _db_get_version(key: str) -> Mapping[str, Any] | None:
    with SessionLocal() as db:
        prompt = db.scalar(select(Prompt).where(Prompt.key == key))
        if prompt is None or prompt.active_version_id is None:
            return None
        if not prompt.enabled or prompt.deleted_at is not None:
            return None
        row = db.get(PromptVersion, prompt.active_version_id)
        if row is None:
            return None
        data = {c.name: getattr(row, c.name) for c in PromptVersion.__table__.columns}
        data["prompt_key"] = key
        return data


def _db_categories() -> str:
    with SessionLocal() as db:
        rows = db.execute(
            select(Prompt.category, Prompt.recognition_hint).where(
                Prompt.step == "read", Prompt.category.is_not(None),
                Prompt.enabled.is_(True), Prompt.deleted_at.is_(None),
            )
        ).all()
    return "\n".join(f"- {c}: {h or ''}".rstrip() for c, h in rows)


def _no_loader(upload_id: int) -> LoadedUpload:
    raise NotImplementedError("The Upload track must supply a loader for page text and sha256")


def default_deps(load_upload: Callable[[int], LoadedUpload] = _no_loader,
                 as_of: Callable[[], date] | None = None) -> ReaderDeps:
    return ReaderDeps(load_upload, _db_get_version, _db_categories, cache=_CACHE, as_of=as_of)


def _tools(version: Mapping[str, Any], as_of: Callable[[], date] | None) -> DocTools | None:
    """The date tools this prompt version lists. None when it lists none or no review date is known."""
    return DocTools.for_version(version, as_of()) if as_of and version.get("tools") else None


def normalise(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", str(text)).split())


def verify_quote(quote: str, page: int, pages: Mapping[int, str]) -> bool:
    """True when the whitespace-normalised quote is a substring of that page's text."""
    needle = normalise(quote)
    return bool(needle) and page in pages and needle in normalise(pages[page])


def _verify_item(raw: Mapping[str, Any], pages: Mapping[int, str]) -> ReadItem:
    quote, page = str(raw.get("quote") or ""), raw.get("page")
    values = {k: None if v is None else str(v) for k, v in raw.items() if k not in ("quote", "page")}
    return ReadItem(
        values=values,
        quote=quote,
        page=page if isinstance(page, int) else 0,
        verified=isinstance(page, int) and verify_quote(quote, page, pages),
    )


def _verify_array(rows: list[Any], pages: Mapping[int, str]) -> ReadField:
    """Verify every row on its own. A row with a bad quote is kept and flagged."""
    items = [_verify_item(row, pages) for row in rows if isinstance(row, dict)]
    return ReadField(items=items, verified=all(i.verified for i in items))


def verify_fields(raw_fields: Mapping[str, Any], pages: Mapping[int, str]) -> dict[str, ReadField]:
    """Keep every returned value but mark it unverified when its quote is not in the page text."""
    result: dict[str, ReadField] = {}
    for key, item in raw_fields.items():
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("value"), list):
            result[key] = _verify_array(item["value"], pages)
            continue
        quote, page = str(item.get("quote") or ""), item.get("page")
        value = item.get("value")
        result[key] = ReadField(
            value=None if value is None else str(value),
            quote=quote,
            page=page if isinstance(page, int) else 0,
            verified=isinstance(page, int) and verify_quote(quote, page, pages),
        )
    return result


def generic_fields_to_dict(items: Any) -> dict[str, Any]:
    """Turn the generic read's fields array into a dict keyed UNKNOWN.<label>. A repeated label gets a number."""
    if isinstance(items, dict):
        return items
    result: dict[str, Any] = {}
    for item in items if isinstance(items, list) else []:
        label = normalise(item.get("label") or "") if isinstance(item, dict) else ""
        if not label:
            continue
        key, n = f"{UNKNOWN}.{label}", 1
        while key in result:
            n += 1
            key = f"{UNKNOWN}.{label} {n}"
        result[key] = {k: item.get(k) for k in ("value", "quote", "page")}
    return result


class ModelUnavailable(AppError):
    """The model service itself failed, for example a spent usage limit or an outage. This is not a finding about the file,
    so nothing is settled: the upload stays unread and can be read again when the service is back."""

    def __init__(self) -> None:
        super().__init__("AI_UNAVAILABLE", "The AI service is not available right now. The file was saved and not read yet. Try again later.", 503)


def _invoke(deps: ReaderDeps, key: str, version: Mapping[str, Any], variables: Mapping[str, Any],
            text: str, sha: str, pages: Pages) -> CallResult:
    image_hashes = tuple(hashlib.sha256(png).hexdigest() for _, png in variables.get("images") or [])
    cache_key = (sha, key, version["version"], tuple(p for p, _ in pages), image_hashes)
    cached = deps.cache.get(cache_key)
    if cached is not None:
        return cached
    call = deps.call or (lambda v, vars_: run_prompt(key, v, vars_, input_text=text, tools=_tools(v, deps.as_of)))
    result = call(version, variables)
    if result.status == STATUS_ERROR:
        raise ModelUnavailable
    if result.status == STATUS_OK:
        deps.cache[cache_key] = result
    return result


def _review(category: str = UNKNOWN, language: str | None = None, legible: bool = True,
            injection: bool = False, run_id: int | None = None) -> DocumentRead:
    return DocumentRead(category=category, language=language, legible=legible,
                        injection_flag=injection, prompt_run_id=run_id,
                        status=ReadStatus.REVIEW_REQUIRED)


def _group_pages(classified: Mapping[str, Any], pages: Pages) -> dict[str, Pages]:
    """Group legible pages by category. Pages the model did not list become UNKNOWN."""
    by_page = {e.get("page"): e for e in classified.get("pages", []) if isinstance(e, dict)}
    groups: dict[str, Pages] = defaultdict(list)
    for number, text in pages:
        entry = by_page.get(number, {})
        if entry.get("legible", True) is False:
            continue
        groups[str(entry.get("category") or UNKNOWN).upper()].append((number, text))
    return dict(groups)


def _describe_field(item: Mapping[str, Any]) -> str:
    flag = "required" if item.get("required") else "optional"
    hint = f" {item['hint']}" if item.get("hint") else ""
    line = f"- {item['key']} ({item.get('type')}, {flag}): {item.get('label')}.{hint}"
    if item.get("type") != "array":
        return line
    subs = ", ".join(f"{s['key']} ({s.get('type')}, {'required' if s.get('required') else 'optional'}): {s.get('label')}"
                     for s in item.get("items") or [])
    return f"{line}\n  Return value as a list with one object per row. Each object has {subs}, plus its own quote and page."


def format_field_definitions(definitions: Any) -> str:
    """Render a version's field_definitions as one line per field for the {{field_definitions}} variable."""
    return "\n".join(_describe_field(item) for item in definitions or [])


def _page_summary(classified: Mapping[str, Any]) -> tuple[str | None, bool, bool]:
    """Derive language, legible and injection_flag for the upload from the per-page classify entries."""
    entries = [e for e in classified.get("pages", []) if isinstance(e, dict)]
    languages = [e["language"] for e in entries if e.get("language")]
    language = max(set(languages), key=languages.count) if languages else None
    legible = any(e.get("legible", True) for e in entries)
    return language, legible, any(e.get("injection_flag", False) for e in entries)


def _page_images(group: Pages, images: Mapping[int, bytes]) -> list[tuple[int, bytes]]:
    return [(n, images[n]) for n, _ in group if n in images]


def _read_group(deps: ReaderDeps, category: str, group: Pages, sha: str,
                images: Mapping[int, bytes] | None = None) -> tuple[str, Pages, CallResult | None]:  # fmt: skip
    if category == REVIEW:
        return category, group, None
    version = deps.get_version(f"doc.read.{category.lower()}") if category != UNKNOWN else None
    key = f"doc.read.{category.lower()}" if version else GENERIC_KEY
    version = version or deps.get_version(GENERIC_KEY)
    if version is None:
        return category, group, None
    variables = {
        "document_text": build_envelope(group),
        "category": category,
        "field_definitions": format_field_definitions(version.get("field_definitions")),
    }
    if images := _page_images(group, images or {}):
        variables["images"] = images
    text = "\n".join(t for _, t in group)
    return category, group, _invoke(deps, key, version, variables, text, sha, group)


def _mark_image_fields(fields: dict[str, ReadField], image_pages: set[int]) -> None:
    """A value read from a page image has no quote in our own text, so it can never be verified."""
    for item in fields.values():
        for row in item.items or []:
            row.from_image = row.page in image_pages
            row.verified = row.verified and not row.from_image
        item.from_image = item.page in image_pages or any(r.from_image for r in item.items or [])
        item.verified = item.verified and not item.from_image


def _build_read(category: str, group: Pages, result: CallResult | None, language: str | None,
                images: Mapping[int, bytes]) -> DocumentRead:  # fmt: skip
    if result is None or result.status != STATUS_OK or result.data is None:
        return _review(category, language, run_id=result.run_id if result else None)
    data = result.data
    if data.get("legible", True) is False:
        return _review(category, data.get("language") or language, legible=False,
                       injection=bool(data.get("injection_flag", False)), run_id=result.run_id)
    text_pages = {n: t for n, t in group if n not in images}
    fields = verify_fields(generic_fields_to_dict(data.get("fields") or {}), text_pages)
    image_pages = {n for n, _ in group if n in images}
    _mark_image_fields(fields, image_pages)
    return DocumentRead(
        category=category,
        language=data.get("language") or language,
        legible=True,
        injection_flag=bool(data.get("injection_flag", False)),
        fields=fields,
        prompt_run_id=result.run_id,
        image_pages=sorted(image_pages),
    )


def _classify(deps: ReaderDeps, loaded: LoadedUpload) -> CallResult | None:
    version = deps.get_version(CLASSIFY_KEY)
    if version is None:
        return None
    variables: dict[str, Any] = {"document_text": build_envelope(loaded.pages), "categories": deps.categories()}
    if loaded.images:
        variables["images"] = sorted(loaded.images.items())
    text = "\n".join(t for _, t in loaded.pages)
    return _invoke(deps, CLASSIFY_KEY, version, variables, text, loaded.sha256, loaded.pages)


def _image_owner_names(classified: Mapping[str, Any], images: Mapping[int, bytes]) -> list[str]:
    """Owner names the classifier returned for scanned pages. The caller compares them with the case client."""
    return [str(o["value"]) for e in classified.get("pages", []) if isinstance(e, dict) and e.get("page") in images
            for o in e.get("owner_names") or [] if isinstance(o, dict) and o.get("value")]


def read_document(upload_id: int, deps: ReaderDeps | None = None) -> list[DocumentRead]:
    """Classify an upload and read each category group. One DocumentRead per category.

    Illegible or failed steps give REVIEW_REQUIRED with no fields. Nothing is inferred.
    """
    deps = deps or default_deps()
    loaded = deps.load_upload(upload_id)
    if loaded.category:
        info, classify_run = {"pages": [{"page": n, "category": loaded.category, "legible": True} for n, _ in loaded.pages]}, None
    else:
        classified = _classify(deps, loaded)
        if classified is None or classified.status != STATUS_OK or classified.data is None:
            return [_review(run_id=classified.run_id if classified else None)]
        info, classify_run = classified.data, classified.run_id
    language, legible, injection = _page_summary(info)
    groups = _group_pages(info, loaded.pages) if legible else {}
    if not groups:
        return [_review(language=language, legible=False, injection=injection, run_id=classify_run)]
    with ThreadPoolExecutor(max_workers=len(groups)) as pool:
        futures = [pool.submit(_read_group, deps, c, g, loaded.sha256, loaded.images) for c, g in groups.items()]
        reads = [_build_read(c, g, r, language, loaded.images) for c, g, r in (f.result() for f in futures)]
    names = _image_owner_names(info, loaded.images)
    for read in reads:
        read.injection_flag = read.injection_flag or injection
        read.image_owner_names = names
    if any(r.injection_flag for r in reads):
        for read in reads:
            read.injection_flag = True
    return reads


def test_document(deps: ReaderDeps, *, text: str | None = None, upload_id: int | None = None,
                  prompt_key: str | None = None, override: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Side-effect-free dry run for the test panel. Returns the TestResult shape.

    Runs classify and read on pasted text (or a loaded upload), optionally replacing the active
    version of prompt_key with an unsaved override. The result cache is a throwaway dict, so
    nothing is cached. Only prompt_runs rows are written, which supply tokens and latency.
    """
    if text is not None:
        loaded = LoadedUpload("test", [(i, t) for i, t in enumerate(text.split("\f"), 1)])
    else:
        loaded = deps.load_upload(upload_id)
    run_ids: list[int] = []
    base = deps.call or (lambda v, vars_: run_prompt(v.get("prompt_key", "test"), v, vars_, input_text=text or "",
                                                     tools=_tools(v, deps.as_of)))

    def recording(version: Mapping[str, Any], variables: Mapping[str, Any]) -> CallResult:
        result = base(version, variables)
        if result.run_id is not None:
            run_ids.append(result.run_id)
        return result

    def get_version(key: str) -> Mapping[str, Any] | None:
        if override is not None and key == prompt_key:
            return {**override, "version": 0, "prompt_key": key}
        return deps.get_version(key)

    test_deps = ReaderDeps(lambda _id: loaded, get_version, deps.categories, call=recording, cache={}, as_of=deps.as_of)
    reads = read_document(0, test_deps)
    fields = [{"key": k, **f.model_dump()} for r in reads for k, f in r.fields.items()]
    first = reads[0]
    return {
        "category": ", ".join(sorted({r.category for r in reads})),
        "language": first.language,
        "legible": all(r.legible for r in reads),
        "injection_flag": any(r.injection_flag for r in reads),
        "fields": fields,
        "prompt_run_ids": run_ids,
    }
