// Shapes mirror backend/app/ai/schemas.py.
export type Step = "classify" | "read" | "other";

// A sub-field of an array field. Items cannot hold items, so nesting stops at one level.
export type ItemDefinition = {
  key: string;
  label: string;
  type: string;
  required: boolean;
  hint: string | null;
};

export type FieldDefinition = ItemDefinition & {
  // The form field this extracted field fills. Empty or missing means it is only used to validate.
  form_target?: string | null;
  items?: ItemDefinition[] | null;
};

// A form field an extracted field can fill. Served by GET /ai/form-targets.
export type FormTarget = { target: string; label: string; section: string };
export type NewFormField = { label: string; value_type: "string" | "date" | "number" };

export type VersionCreate = {
  system_text: string;
  user_template: string;
  model: string;
  effort: string;
  max_tokens: number;
  // Left out, the server builds it from the field definitions.
  output_schema?: Record<string, unknown> | null;
  field_definitions: FieldDefinition[];
  tools: string[];
  note: string | null;
};

// A read only helper the model may call while it reads a document. Served by GET /ai/tools.
export type ToolInfo = { name: string; description: string };

export type VersionOut = VersionCreate & {
  id: number;
  prompt_id: number;
  version: number;
  created_by: string;
  created_at: string;
};

export type RunOut = {
  id: number;
  prompt_key: string;
  version: number;
  model: string;
  tokens_in: number | null;
  tokens_out: number | null;
  latency_ms: number | null;
  stop_reason: string | null;
  status: string;
  created_at: string;
};

export type PromptCreate = VersionCreate & {
  key: string;
  step: Step;
  category: string | null;
  title: string;
  recognition_hint: string | null;
};

export type PromptSummary = {
  key: string;
  enabled: boolean;
  deleted: boolean;
  protected: boolean;
  step: Step;
  category: string | null;
  title: string;
  recognition_hint: string | null;
  origin: "BUILT_IN" | "ADDITIONAL";
  active_version: number | null;
  last_run: RunOut | null;
};

export type PromptList = Record<Step, PromptSummary[]>;

export type PromptDetail = PromptSummary & {
  active: VersionOut | null;
  field_definitions: FieldDefinition[];
  tools: string[];
};

export type TestRequest = {
  text: string | null;
  upload_id: number | null;
  prompt_key: string | null;
  override: VersionCreate | null;
};

// One row of an array field, with its own quote and page. verified comes from the server.
export type TestItem = {
  values: Record<string, string | null>;
  quote: string;
  page: number;
  verified: boolean;
};

export type TestField = {
  key?: string;
  value?: unknown;
  quote?: string | null;
  page?: number | null;
  verified?: boolean;
  items?: TestItem[] | null;
  [name: string]: unknown;
};

export type TestResult = {
  category: string | null;
  language: string | null;
  legible: boolean | null;
  injection_flag: boolean | null;
  fields: TestField[];
  prompt_run_ids: number[];
};

export type ReviewKind = "all" | "missed" | "quarantined";

// missed: the AI could not type the document. quarantined: it was set aside, for example it belongs to another client.
export type ReviewRow = {
  upload_id: string;
  case_id: string;
  original_filename: string;
  kind: Exclude<ReviewKind, "all">;
  category: string | null;
  category_label: string | null;
  reason: string | null;
  reason_code: string | null;
  legible: boolean;
  injection_flag: boolean;
  page_count: number | null;
  read_at: string;
};

export type ReviewPage = {
  items: ReviewRow[];
  total: number;
  page: number;
  page_size: number;
  counts: { missed: number; quarantined: number };
};

export type SampleUpload = { id: number; filename: string };

export type PromptHealth = {
  runs: number;
  failed: number;
  ok_pct: number | null;
  median_latency_ms: number | null;
  spark: number[];
};

export type AiStats = {
  prompts: number;
  enabled: number;
  runs: number;
  runs_prev: number;
  failed: number;
  failed_prev: number;
  days: { day: string; runs: number; failed: number }[];
  by_prompt: Record<string, PromptHealth>;
};

// The expanded trace of one run. hidden means it belongs to another person's case.
export type TraceOut = {
  run_id: number;
  hidden: boolean;
  saved: boolean;
  prompt: string | null;
  input_text: string | null;
  calls: Record<string, unknown>[];
  raw_output: string | null;
  error: string | null;
};

// A field the document type agent suggests. The quote and page are the evidence, verified is decided by code.
export type DraftField = {
  key: string;
  label: string;
  type: "string" | "date" | "number";
  required: boolean;
  hint: string;
  quote: string;
  page: number;
  verified: boolean;
  from_image: boolean;
  // The form field this value fills. A new additional client field is made on create when new_form_field is true.
  form_target?: string | null;
  new_form_field?: boolean;
};

export type TypeDraft = {
  status: "OK" | "NEEDS_REVIEW";
  error: string | null;
  matches_existing: string | null;
  matches_reason: string | null;
  category: string;
  title: string;
  recognition_hint: string;
  system_text: string;
  injection_flag: boolean;
  fields: DraftField[];
};

export type CreateTypeBody = Pick<TypeDraft, "category" | "title" | "recognition_hint" | "system_text" | "fields">;
