"""Routes for AI management under /api/ai. Thin wrappers over the registry."""

from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.ai import doc_tools, doctype_agent, form_fields, reader, registry, trace as run_trace
from app.ai.client import STATUS_OK
from app.ai.models import Prompt, PromptRun, PromptVersion
from app.ai.schemas import (
    ActivateRequest,
    OutputSchemaRequest,
    AiStats,
    CreateTypeOut,
    CreateTypeRequest,
    FormFieldCreate,
    FormFieldOut,
    DayStat,
    PromptCreate,
    PromptHealth,
    PromptDetail,
    PromptListOut,
    PromptRename,
    PromptSummary,
    ResolveRequest,
    ReviewCounts,
    ReviewRow,
    ReviewPage,
    RunOut,
    Step,
    TestRequest,
    TraceOut,
    TypeDraft,
    TestResult,
    ToolInfo,
    VersionCreate,
    VersionOut,
)
from app.cases import repository
from app.cases.documents import CATEGORY_TITLE, category_label, owner_column
from app.cases.uploads import require_upload_access
from app.core import audit
from app.core.contracts import AuditAction
from app.core.security import Actor, get_actor, parse_actor
from app.db.session import SessionLocal, get_db
from app.facts import engine, sources

router = APIRouter(prefix="/api/ai", tags=["ai"])

_STEPS = ("classify", "read", "other")
_PROTECTED = ("doc.classify", "doc.read.generic")
_NO_RENAME = ("doc.classify",)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message


async def api_error_handler(_request: Any, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})


def _get_prompt(db: Session, key: str, include_deleted: bool = False) -> Prompt:
    prompt = db.scalar(select(Prompt).where(Prompt.key == key))
    if prompt is None or (prompt.deleted_at is not None and not include_deleted):
        raise ApiError(404, "PROMPT_NOT_FOUND", f"No prompt with key {key}")
    return prompt


def _versions(db: Session, prompt: Prompt) -> list[PromptVersion]:
    stmt = select(PromptVersion).where(PromptVersion.prompt_id == prompt.id).order_by(PromptVersion.version.desc())
    return list(db.scalars(stmt))


def _last_run(db: Session, key: str) -> PromptRun | None:
    stmt = select(PromptRun).where(PromptRun.prompt_key == key).order_by(PromptRun.id.desc()).limit(1)
    return db.scalar(stmt)


def _summary(db: Session, prompt: Prompt, active: PromptVersion | None) -> dict[str, Any]:
    last = _last_run(db, prompt.key)
    return {
        "key": prompt.key,
        "enabled": prompt.enabled,
        "deleted": prompt.deleted_at is not None,
        "protected": prompt.key in _PROTECTED,
        "step": prompt.step,
        "category": prompt.category,
        "title": prompt.title,
        "recognition_hint": prompt.recognition_hint,
        "origin": prompt.origin,
        "active_version": active.version if active else None,
        "last_run": RunOut.model_validate(last) if last else None,
    }


def _active(db: Session, prompt: Prompt) -> PromptVersion | None:
    if prompt.active_version_id is None:
        return None
    return db.get(PromptVersion, prompt.active_version_id)


def _as_dict(row: PromptVersion) -> dict[str, Any]:
    return VersionOut.model_validate(row).model_dump()


@router.get("/prompts", response_model=PromptListOut)
def list_prompts(include_deleted: bool = False, db: Session = Depends(get_db)) -> PromptListOut:
    grouped: dict[str, list[PromptSummary]] = {step: [] for step in _STEPS}
    for prompt in db.scalars(select(Prompt).order_by(Prompt.key)):
        if prompt.deleted_at is not None and not include_deleted:
            continue
        item = PromptSummary(**_summary(db, prompt, _active(db, prompt)))
        grouped.setdefault(prompt.step, []).append(item)
    return PromptListOut(**grouped)


WINDOW_DAYS = 7


@router.get("/stats", response_model=AiStats)
def stats(db: Session = Depends(get_db)) -> AiStats:
    """Run health for the last 7 days against the 7 before, for the KPI tiles, the chart and the prompt list."""
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=WINDOW_DAYS - 1 - i) for i in range(WINDOW_DAYS)]
    since = datetime.combine(days[0] - timedelta(days=WINDOW_DAYS), datetime.min.time(), timezone.utc)
    rows = db.execute(
        select(PromptRun.prompt_key, PromptRun.status, PromptRun.latency_ms, PromptRun.created_at).where(PromptRun.created_at >= since)
    ).all()
    per_day = {d: DayStat(day=d.isoformat(), runs=0, failed=0) for d in days}
    prev = {"runs": 0, "failed": 0}
    latencies: dict[str, list[int]] = {}
    health: dict[str, dict[str, Any]] = {}
    for key, status, latency, created in rows:
        failed = status != STATUS_OK
        day = created.astimezone(timezone.utc).date()
        if day not in per_day:
            prev["runs"] += 1
            prev["failed"] += failed
            continue
        per_day[day].runs += 1
        per_day[day].failed += failed
        item = health.setdefault(key, {"runs": 0, "failed": 0, "spark": [0] * WINDOW_DAYS})
        item["runs"] += 1
        item["failed"] += failed
        item["spark"][days.index(day)] += 1
        if latency is not None:
            latencies.setdefault(key, []).append(latency)
    by_prompt = {
        key: PromptHealth(
            **item,
            ok_pct=round(100 * (item["runs"] - item["failed"]) / item["runs"]),
            median_latency_ms=int(median(latencies[key])) if key in latencies else None,
        )
        for key, item in health.items()
    }
    prompts = list(db.scalars(select(Prompt).where(Prompt.deleted_at.is_(None))))
    return AiStats(
        prompts=len(prompts), enabled=sum(p.enabled for p in prompts),
        runs=sum(d.runs for d in per_day.values()), runs_prev=prev["runs"],
        failed=sum(d.failed for d in per_day.values()), failed_prev=prev["failed"],
        days=list(per_day.values()), by_prompt=by_prompt,
    )  # fmt: skip


def _check_new_prompt(db: Session, body: PromptCreate) -> None:
    existing = db.scalar(select(Prompt).where(Prompt.key == body.key))
    if existing is not None and existing.deleted_at is not None:
        raise ApiError(409, "PROMPT_DELETED", f"Prompt {body.key} was deleted. Restore it instead")
    if existing is not None:
        raise ApiError(409, "PROMPT_EXISTS", f"A prompt with key {body.key} already exists")
    if body.step != Step.READ:
        raise ApiError(422, "DOCUMENT_TYPE_ONLY", "Only document type (read) prompts can be added. There is one classify prompt")
    if body.category is None:
        raise ApiError(422, "CATEGORY_REQUIRED", "Read prompts need a category")
    if body.category.upper() == "UNKNOWN":
        raise ApiError(422, "CATEGORY_RESERVED", "UNKNOWN is reserved for the unknown fallback prompt")
    if body.key != f"doc.read.{body.category.lower()}":
        raise ApiError(422, "KEY_CATEGORY_MISMATCH", f"Key must be doc.read.{body.category.lower()}")


def _form_targets(db: Session) -> list[dict[str, str]]:
    return form_fields.targets(db)


def _check_form_targets(db: Session, field_definitions: list[Any]) -> None:
    known = {item["target"] for item in _form_targets(db)}
    for item in field_definitions:
        target = item.get("form_target") if isinstance(item, dict) else getattr(item, "form_target", None)
        if target is not None and target not in known:
            raise ApiError(422, "UNKNOWN_FORM_TARGET", f"{target} is not a field of the form. Pick one from /ai/form-targets or leave it empty")


def _with_schema(data: dict[str, Any], category: str | None) -> dict[str, Any]:
    """Fill in the output schema from the field definitions when the caller left it out."""
    if data.get("output_schema") is not None:
        return data
    if not category or not data.get("field_definitions"):
        raise ApiError(422, "SCHEMA_REQUIRED", "Send an output schema, or a category and field definitions to build it from")
    return data | {"output_schema": registry.build_output_schema(category, data["field_definitions"])}


@router.post("/output-schema")
def preview_output_schema(body: OutputSchemaRequest) -> dict[str, Any]:
    """The schema a document type gets from its field definitions. The editor shows it, and saving stores the same one."""
    return registry.build_output_schema(body.category, [d.model_dump() for d in body.field_definitions])


@router.get("/form-targets")
def list_form_targets(db: Session = Depends(get_db)) -> list[dict[str, str]]:
    return _form_targets(db)


@router.post("/form-fields", response_model=FormFieldOut, status_code=201)
def add_form_field(
    body: FormFieldCreate,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Add an additional client field. It shows in the Fills form field picker and as a row of the Form draft."""
    try:
        field = form_fields.add_field(db, actor, body.label, body.value_type)
    except form_fields.FormFieldError as exc:
        raise ApiError(exc.status, exc.code, exc.message) from exc
    engine.invalidate(db)
    db.commit()
    return {"target": field.target, "label": field.label, "section": sources.ADDITIONAL_SECTION}


@router.get("/tools", response_model=list[ToolInfo])
def list_tools() -> list[dict[str, str]]:
    """The read only date tools a prompt version may switch on."""
    return doc_tools.catalog()


@router.post("/prompts", response_model=PromptDetail, status_code=201)
def create_prompt(
    body: PromptCreate,
    x_actor: str = Header(default="unknown"),
    db: Session = Depends(get_db),
) -> PromptDetail:
    _check_new_prompt(db, body)
    _check_form_targets(db, body.field_definitions)
    data = _with_schema(body.model_dump(exclude={"key", "step", "category", "title", "recognition_hint"}), body.category)
    try:
        row = registry.create_version([], None, data | {"created_by": x_actor})
    except registry.RegistryError as exc:
        raise ApiError(422, "INVALID_PROMPT_VERSION", str(exc)) from exc
    prompt = Prompt(
        key=body.key, step=body.step.value, category=body.category,
        title=body.title, recognition_hint=body.recognition_hint,
    )
    db.add(prompt)
    db.flush()
    version = PromptVersion(prompt_id=prompt.id, **row)
    db.add(version)
    db.flush()
    prompt.active_version_id = version.id
    engine.invalidate(db)
    db.commit()
    return get_prompt(body.key, db)


@router.get("/prompts/{key}", response_model=PromptDetail)
def get_prompt(key: str, db: Session = Depends(get_db)) -> PromptDetail:
    prompt = _get_prompt(db, key)
    active = _active(db, prompt)
    detail = _summary(db, prompt, active)
    if active is not None:
        detail["active"] = VersionOut.model_validate(active)
        detail["field_definitions"] = active.field_definitions
        detail["tools"] = active.tools
    return PromptDetail(**detail)


@router.patch("/prompts/{key}", response_model=PromptDetail)
def rename_prompt(key: str, body: PromptRename, db: Session = Depends(get_db)) -> PromptDetail:
    prompt = _get_prompt(db, key)
    if key in _NO_RENAME:
        raise ApiError(409, "PROMPT_PROTECTED", f"Prompt {key} is required and cannot be renamed")
    prompt.title = body.title
    if body.recognition_hint is not None:
        prompt.recognition_hint = body.recognition_hint
    db.commit()
    return get_prompt(key, db)


@router.get("/prompts/{key}/versions", response_model=list[VersionOut])
def list_versions(key: str, db: Session = Depends(get_db)) -> list[PromptVersion]:
    return _versions(db, _get_prompt(db, key))


@router.post("/prompts/{key}/versions", response_model=VersionOut, status_code=201)
def create_version(
    key: str,
    body: VersionCreate,
    x_actor: str = Header(default="unknown"),
    db: Session = Depends(get_db),
) -> PromptVersion:
    prompt = _get_prompt(db, key)
    _check_form_targets(db, body.field_definitions)
    versions = _versions(db, prompt)
    active = _active(db, prompt)
    data = _with_schema(body.model_dump(), prompt.category) | {"created_by": x_actor}
    try:
        row = registry.create_version(
            [{"version": v.version} for v in versions], _as_dict(active) if active else None, data
        )
    except registry.KeyLockError as exc:
        raise ApiError(409, "KEY_LOCKED", str(exc)) from exc
    except registry.RegistryError as exc:
        raise ApiError(422, "INVALID_PROMPT_VERSION", str(exc)) from exc
    version = PromptVersion(prompt_id=prompt.id, **row)
    db.add(version)
    db.commit()
    return version


def _change_state(db: Session, key: str, protect: bool, include_deleted: bool = False) -> Prompt:
    prompt = _get_prompt(db, key, include_deleted)
    if protect and key in _PROTECTED:
        raise ApiError(409, "PROMPT_PROTECTED", f"Prompt {key} is required and cannot be disabled or deleted")
    return prompt


@router.post("/prompts/{key}/disable", response_model=PromptDetail)
def disable_prompt(key: str, db: Session = Depends(get_db)) -> PromptDetail:
    _change_state(db, key, True).enabled = False
    engine.invalidate(db)
    db.commit()
    return get_prompt(key, db)


@router.post("/prompts/{key}/enable", response_model=PromptDetail)
def enable_prompt(key: str, db: Session = Depends(get_db)) -> PromptDetail:
    _change_state(db, key, False).enabled = True
    engine.invalidate(db)
    db.commit()
    return get_prompt(key, db)


@router.delete("/prompts/{key}", status_code=204)
def delete_prompt(key: str, db: Session = Depends(get_db)) -> None:
    _change_state(db, key, True).deleted_at = func.now()
    engine.invalidate(db)
    db.commit()


@router.post("/prompts/{key}/restore", response_model=PromptDetail)
def restore_prompt(key: str, db: Session = Depends(get_db)) -> PromptDetail:
    _change_state(db, key, False, include_deleted=True).deleted_at = None
    engine.invalidate(db)
    db.commit()
    return get_prompt(key, db)


@router.post("/prompts/{key}/activate", response_model=PromptDetail)
def activate(key: str, body: ActivateRequest, db: Session = Depends(get_db)) -> PromptDetail:
    prompt = _get_prompt(db, key)
    versions = [{"id": v.id, "version": v.version} for v in _versions(db, prompt)]
    try:
        updated = registry.activate_version({}, versions, body.version)
    except registry.VersionError as exc:
        raise ApiError(404, "VERSION_NOT_FOUND", str(exc)) from exc
    prompt.active_version_id = updated["active_version_id"]
    engine.invalidate(db)
    db.commit()
    return get_prompt(key, db)


@router.post("/test", response_model=TestResult)
def test_prompt(
    body: TestRequest, x_actor: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)
) -> TestResult:
    if body.text is None and body.upload_id is None:
        raise ApiError(422, "TEST_INPUT_REQUIRED", "Send text or upload_id")
    if body.upload_id is not None:
        row = db.execute(text("SELECT case_id, upload_id FROM uploads WHERE id = :i"), {"i": body.upload_id}).mappings().first()
        if row is not None:
            require_upload_access(db, parse_actor(x_actor), row["case_id"], row["upload_id"])
    override = body.override.model_dump() if body.override else None
    if override is not None and body.prompt_key:
        override = _with_schema(override, _get_prompt(db, body.prompt_key).category)
    try:
        result = reader.test_document(
            reader.default_deps(as_of=lambda: repository.get_as_of(db)), text=body.text, upload_id=body.upload_id,
            prompt_key=body.prompt_key, override=override,
        )
    except NotImplementedError as exc:
        raise ApiError(501, "UPLOADS_UNAVAILABLE", "Upload loading is not available yet, paste text instead") from exc
    return TestResult(**result)


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    x_actor: Annotated[str | None, Header()] = None,
    prompt_key: str | None = None,
    case_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[RunOut]:
    stmt = select(PromptRun).order_by(PromptRun.id.desc()).limit(limit)
    if prompt_key:
        stmt = stmt.where(PromptRun.prompt_key == prompt_key)
    if case_id:
        stmt = stmt.where(PromptRun.case_id == case_id)
    mine: set[str] = set()
    if x_actor:
        actor = parse_actor(x_actor)
        mine = set(db.scalars(text(f"SELECT c.case_id FROM cases c WHERE {owner_column(actor.role)} = :a"), {"a": actor.label}))
    # Text of a run on someone else's case is not shown.
    hidden = {"rendered_prompt": None, "input_text": None, "raw_output": None}
    return [
        RunOut.model_validate(run) if run.case_id is None or run.case_id in mine else RunOut.model_validate(run).model_copy(update=hidden)
        for run in db.scalars(stmt)
    ]


@router.get("/runs/{run_id}/trace", response_model=TraceOut)
def run_trace_detail(run_id: int, x_actor: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)) -> TraceOut:
    """The saved trace of one run, expanded. Text of a run on someone else's case is not shown."""
    run = db.get(PromptRun, run_id)
    if run is None:
        raise ApiError(404, "RUN_NOT_FOUND", f"No run {run_id}")
    if run.case_id is not None:
        actor = parse_actor(x_actor) if x_actor else None
        owned = actor is not None and db.scalar(
            text(f"SELECT 1 FROM cases c WHERE c.case_id = :c AND {owner_column(actor.role)} = :a"), {"c": run.case_id, "a": actor.label}
        )
        if not owned:
            return TraceOut(run_id=run.id, hidden=True)
    saved = run_trace.unpack(run.trace) if run.trace else {}
    return TraceOut(
        run_id=run.id, prompt=run.rendered_prompt, input_text=run.input_text, calls=saved.get("calls", []),
        raw_output=run.raw_output, error=saved.get("error"), saved=run.trace is not None,
    )  # fmt: skip


# One row per upload that needs a person: the latest read could not type it (missed) or it was set aside (quarantined).
_REVIEW_BASE = """
WITH latest AS (SELECT DISTINCT ON (upload_id) * FROM document_reads ORDER BY upload_id, read_at DESC, id DESC),
review AS (
    SELECT u.upload_id, u.case_id, u.original_filename, COALESCE(r.category, u.category) AS category, {title} AS category_title,
           CASE WHEN u.outcome = 'QUARANTINED' THEN 'quarantined' ELSE 'missed' END AS kind,
           COALESCE(NULLIF(r.reason, ''), u.outcome_reason) AS reason, u.reason_code,
           COALESCE(r.legible, true) AS legible, COALESCE(r.injection_flag, false) AS injection_flag, r.page_count,
           COALESCE(r.read_at, u.uploaded_at) AS read_at
    FROM uploads u
    JOIN cases c ON c.case_id = u.case_id
    LEFT JOIN latest r ON r.upload_id = u.upload_id
    WHERE u.deleted_at IS NULL AND {owner} = :actor AND c.case_id NOT IN (SELECT case_id FROM case_workflows WHERE status IN ('DRAFT', 'DELETED'))
      AND (u.outcome = 'QUARANTINED' OR r.category IN ('UNKNOWN', 'REVIEW_REQUIRED'))
)
"""
_REVIEW_KINDS = ("all", "missed", "quarantined")
MAX_REVIEW_PAGE_SIZE = 50


def _like(term: str) -> str:
    return "%" + term.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


@router.get("/review", response_model=ReviewPage)
def list_review(
    actor: Annotated[Actor, Depends(get_actor)],
    kind: str = "all",
    q: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=MAX_REVIEW_PAGE_SIZE),
    db: Session = Depends(get_db),
) -> ReviewPage:
    """Uploads on the actor's own cases that need a person, newest first, one page at a time."""
    if kind not in _REVIEW_KINDS:
        raise ApiError(422, "BAD_KIND", "kind must be all, missed or quarantined")
    base = _REVIEW_BASE.format(owner=owner_column(actor.role), title=CATEGORY_TITLE.replace("u.category", "COALESCE(r.category, u.category)"))
    params: dict[str, Any] = {"actor": actor.label}
    where = []
    if q.strip():
        where.append("(lower(original_filename) LIKE :q ESCAPE '\\' OR lower(case_id) LIKE :q ESCAPE '\\')")
        params["q"] = _like(q)
    counts = {k: n for k, n in db.execute(text(base + f"SELECT kind, count(*) FROM review {'WHERE ' + where[0] if where else ''} GROUP BY kind"), params)}
    if kind != "all":
        where.append("kind = :kind")
        params["kind"] = kind
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = db.execute(text(base + f"SELECT count(*) FROM review {clause}"), params).scalar_one()
    rows = db.execute(
        text(base + f"SELECT * FROM review {clause} ORDER BY read_at DESC, upload_id LIMIT :limit OFFSET :offset"),
        params | {"limit": page_size, "offset": (page - 1) * page_size},
    ).mappings().all()
    items = [ReviewRow(**{k: v for k, v in r.items() if k != "category_title"}, category_label=category_label(r["category"], r["category_title"])) for r in rows]
    return ReviewPage(items=items, total=total, page=page, page_size=page_size,
                      counts=ReviewCounts(missed=counts.get("missed", 0), quarantined=counts.get("quarantined", 0)))  # fmt: skip


@router.post("/review/{upload_id}/resolve", response_model=ReviewRow | None)
def resolve_review(
    upload_id: str,
    body: ResolveRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Session = Depends(get_db),
) -> None:
    """A person sets the type of an upload the classifier could not type. The same category twice changes nothing."""
    upload = db.execute(
        text("SELECT case_id, category FROM uploads WHERE upload_id = :u AND deleted_at IS NULL FOR UPDATE"), {"u": upload_id}
    ).mappings().first()  # fmt: skip
    if upload is None:
        raise ApiError(404, "UPLOAD_NOT_FOUND", f"No upload {upload_id}")
    require_upload_access(db, actor, upload["case_id"], upload_id)
    category = body.category.upper()
    allowed = db.scalar(
        select(Prompt.id).where(
            Prompt.step == "read", Prompt.category == category, Prompt.category != reader.UNKNOWN,
            Prompt.enabled, Prompt.deleted_at.is_(None),
        )
    )
    if allowed is None:
        raise ApiError(422, "CATEGORY_NOT_AVAILABLE", f"{body.category} is not an enabled document type")
    last = db.execute(
        text("SELECT category, status, page_count FROM document_reads WHERE upload_id = :u ORDER BY read_at DESC, id DESC LIMIT 1"),
        {"u": upload_id},
    ).mappings().first()  # fmt: skip
    if last and last["status"] == "READ" and last["category"] == category and upload["category"] == category:
        return
    reason = f"Set by {actor.label}" + (f". {body.note}" if body.note else "")
    db.execute(text("UPDATE uploads SET category = :c, updated_at = now() WHERE upload_id = :u"), {"c": category, "u": upload_id})
    db.execute(
        text("INSERT INTO document_reads (upload_id, category, status, page_count, reason) VALUES (:u, :c, 'READ', :p, :r)"),
        {"u": upload_id, "c": category, "p": last["page_count"] if last else None, "r": reason},
    )
    audit.record(
        db, actor=actor, action=AuditAction.DOCUMENT_TYPE_SET, case_id=upload["case_id"], target_type="upload",
        target_id=upload_id, before_state={"category": upload["category"]}, after_state={"category": category},
    )  # fmt: skip
    db.commit()

    engine.recompute(db, upload["case_id"])


def _upload_for_actor(db: Session, actor: Actor, upload_id: str) -> str:
    case_id = db.scalar(text("SELECT case_id FROM uploads WHERE upload_id = :u"), {"u": upload_id})
    if case_id is None:
        raise ApiError(404, "UPLOAD_NOT_FOUND", f"No upload {upload_id}")
    require_upload_access(db, actor, case_id, upload_id)
    return case_id


@router.post("/review/{upload_id}/draft-type", response_model=TypeDraft)
def draft_type(upload_id: str, actor: Annotated[Actor, Depends(get_actor)], db: Session = Depends(get_db)) -> TypeDraft:
    """The AI reads the file and drafts a new document type. Nothing is saved until the person creates the type."""
    _upload_for_actor(db, actor, upload_id)
    return TypeDraft(**doctype_agent.draft_type(db, upload_id).__dict__)


def _reread(actor: Actor, upload_id: str) -> None:
    from app.ingest import service

    with SessionLocal() as session:
        service.read_upload(session, actor, upload_id, force=True)


def _make_new_form_fields(db: Session, actor: Actor, fields: list[dict[str, Any]]) -> None:
    """Make the additional client fields that drafted fields ask for and point those fields at them. A name that already
    exists is reused."""
    known = {t["target"] for t in _form_targets(db)}
    for item in fields:
        if not item.get("new_form_field") or item.get("form_target"):
            continue
        target = form_fields.target_for(item["label"])
        if target not in known:
            try:
                target = form_fields.add_field(db, actor, item["label"], item["type"]).target
            except form_fields.FormFieldError as exc:
                raise ApiError(exc.status, exc.code, exc.message) from exc
            known.add(target)
        item["form_target"] = target


@router.post("/review/{upload_id}/create-type", response_model=CreateTypeOut, status_code=201)
def create_type(
    upload_id: str,
    body: CreateTypeRequest,
    tasks: BackgroundTasks,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Session = Depends(get_db),
) -> CreateTypeOut:
    """Create and activate the document type, then read the source upload again. Only that upload is read again."""
    _upload_for_actor(db, actor, upload_id)
    if error := doctype_agent.category_error(body.category, doctype_agent.existing_categories(db)):
        raise ApiError(409 if "already" in error else 422, "CATEGORY_NOT_AVAILABLE", error)
    key = f"doc.read.{body.category.lower()}"
    fields = [{**f.model_dump(), "key": f"{body.category}.{f.label}"} for f in body.fields]
    _make_new_form_fields(db, actor, fields)
    _check_form_targets(db, fields)
    try:
        data = doctype_agent.build_prompt_data(db, body.category, body.system_text, fields, actor.label)
        row = registry.create_version([], None, data)
    except registry.RegistryError as exc:
        raise ApiError(422, "INVALID_PROMPT_VERSION", str(exc)) from exc
    prompt = Prompt(key=key, step=Step.READ.value, category=body.category, title=body.title, recognition_hint=body.recognition_hint, origin="ADDITIONAL")
    db.add(prompt)
    db.flush()
    version = PromptVersion(prompt_id=prompt.id, **row)
    db.add(version)
    db.flush()
    prompt.active_version_id = version.id
    ids = {"target_type": "prompt", "target_id": key, "details": {"upload_id": upload_id, "fields": len(fields)}}
    audit.record(db, actor=actor, action=AuditAction.DOCUMENT_TYPE_CREATED, after_state={"category": body.category, "origin": "ADDITIONAL"}, **ids)
    audit.record(db, actor=actor, action=AuditAction.PROMPT_VERSION_CREATED, after_state={"version": 1}, **ids)
    audit.record(db, actor=actor, action=AuditAction.PROMPT_VERSION_ACTIVATED, after_state={"version": 1}, **ids)
    engine.invalidate(db)
    db.commit()
    tasks.add_task(_reread, actor, upload_id)
    return CreateTypeOut(key=key, category=body.category, reread="QUEUED")
