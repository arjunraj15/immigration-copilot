"""Pydantic request and response models for the /api/ai routes."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Step(StrEnum):
    CLASSIFY = "classify"
    READ = "read"
    OTHER = "other"


class ItemDefinition(BaseModel):
    """A sub-field of an array field. It cannot hold items itself, so nesting stops at one level."""

    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    type: str
    required: bool = False
    hint: str | None = None


class FieldDefinition(BaseModel):
    key: str
    label: str
    type: str
    required: bool = False
    hint: str | None = None
    # The form target this field fills, such as applicant.passport_expiration. Empty means the field is only used to validate.
    form_target: str | None = None
    items: list[ItemDefinition] | None = None


class VersionCreate(BaseModel):
    system_text: str
    user_template: str
    model: str
    effort: str
    max_tokens: int = Field(gt=0)
    # Left out, the server builds it from field_definitions, so the schema always matches the fields.
    output_schema: dict[str, Any] | None = None
    field_definitions: list[FieldDefinition]
    tools: list[str] = []
    note: str | None = None


class VersionOut(VersionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prompt_id: int
    version: int
    created_by: str
    created_at: datetime


class PromptCreate(VersionCreate):
    key: str = Field(pattern=r"^doc(\.[a-z0-9_]+)+$", max_length=120)
    step: Step
    category: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$", max_length=80)
    title: str = Field(min_length=1, max_length=200)
    recognition_hint: str | None = None


class OutputSchemaRequest(BaseModel):
    category: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=80)
    field_definitions: list[FieldDefinition]


class FormFieldCreate(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    value_type: Literal["string", "date", "number"] = "string"


class FormFieldOut(BaseModel):
    target: str
    label: str
    section: str


class PromptRename(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    recognition_hint: str | None = None


class ActivateRequest(BaseModel):
    version: int


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prompt_key: str
    version: int
    model: str
    case_id: str | None = None
    input_hash: str
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: int | None
    stop_reason: str | None
    status: str
    rendered_prompt: str | None = None
    input_text: str | None = None
    raw_output: str | None = None
    created_at: datetime


class PromptSummary(BaseModel):
    key: str
    enabled: bool = True
    deleted: bool = False
    protected: bool = False
    step: Step
    category: str | None
    title: str
    recognition_hint: str | None
    origin: str = "BUILT_IN"
    active_version: int | None
    last_run: RunOut | None = None


class PromptListOut(BaseModel):
    classify: list[PromptSummary] = []
    read: list[PromptSummary] = []
    other: list[PromptSummary] = []


class PromptDetail(PromptSummary):
    active: VersionOut | None = None
    field_definitions: list[FieldDefinition] = []
    tools: list[str] = []


class ToolInfo(BaseModel):
    name: str
    description: str


class TestRequest(BaseModel):
    text: str | None = None
    upload_id: int | None = None
    prompt_key: str | None = None
    override: VersionCreate | None = None


class TestResult(BaseModel):
    category: str | None
    language: str | None
    legible: bool | None
    injection_flag: bool | None
    fields: list[dict[str, Any]]
    prompt_run_ids: list[int]


class ResolveRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    category: str
    note: str | None = Field(default=None, max_length=500)


class ReviewRow(BaseModel):
    upload_id: str
    case_id: str
    original_filename: str
    kind: str  # "missed" when the AI could not type it, "quarantined" when it was set aside
    category: str | None
    category_label: str | None
    reason: str | None
    reason_code: str | None = None
    legible: bool
    injection_flag: bool
    page_count: int | None
    read_at: datetime


class ReviewCounts(BaseModel):
    missed: int
    quarantined: int


class TraceOut(BaseModel):
    run_id: int
    hidden: bool = False
    saved: bool = False
    prompt: str | None = None
    input_text: str | None = None
    calls: list[dict[str, Any]] = []
    raw_output: str | None = None
    error: str | None = None


class PromptHealth(BaseModel):
    runs: int
    failed: int
    ok_pct: int | None
    median_latency_ms: int | None
    spark: list[int]


class DayStat(BaseModel):
    day: str
    runs: int
    failed: int


class AiStats(BaseModel):
    prompts: int
    enabled: int
    runs: int
    runs_prev: int
    failed: int
    failed_prev: int
    days: list[DayStat]
    by_prompt: dict[str, PromptHealth]


class ReviewPage(BaseModel):
    items: list[ReviewRow]
    total: int
    page: int
    page_size: int
    counts: ReviewCounts


class DraftField(BaseModel):
    """A suggested field. quote, page and verified are the evidence for the suggestion and are not stored in the prompt."""

    key: str = ""
    label: str = Field(min_length=1, max_length=120)
    type: str = "string"
    required: bool = False
    hint: str = ""
    quote: str = ""
    page: int = 0
    verified: bool = False
    from_image: bool = False
    form_target: str | None = None  # the form field this value fills, empty means validate only
    new_form_field: bool = False  # true when no form field fits and an additional client field is made on create


class TypeDraft(BaseModel):
    status: str
    error: str | None = None
    matches_existing: str | None = None
    matches_reason: str | None = None
    category: str = ""
    title: str = ""
    recognition_hint: str = ""
    system_text: str = ""
    injection_flag: bool = False
    fields: list[DraftField] = []
    prompt_run_id: int | None = None
    model: str = ""
    effort: str = ""
    max_tokens: int = 0


class CreateTypeRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    category: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=80)
    title: str = Field(min_length=1, max_length=200)
    recognition_hint: str = Field(min_length=1)
    system_text: str = Field(min_length=1)
    fields: list[DraftField] = Field(min_length=1, max_length=30)


class CreateTypeOut(BaseModel):
    key: str
    category: str
    reread: str
