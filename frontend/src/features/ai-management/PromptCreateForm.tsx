import { useState } from "react";

import { BUTTON, BUTTON_QUIET, INPUT } from "./fieldStyles";
import { api } from "../../api/client";
import { useCreatePrompt, usePrompts } from "./hooks";
import { starterFields, starterSchema, starterVersion } from "./starter";
import ToolPicker from "./ToolPicker";
import type { FieldDefinition, PromptCreate, PromptDetail, Step } from "./types";

const EFFORTS = ["low", "medium", "high", "xhigh", "max"];

type Props = { onCreated: (key: string) => void; onCancel: () => void };

function Label({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1 text-sm">
      <span className="font-medium">{text}</span>
      {children}
    </label>
  );
}

export default function PromptCreateForm({ onCreated, onCancel }: Props) {
  const step: Step = "read";
  const [category, setCategory] = useState("");
  const [key, setKey] = useState("doc.read.");
  const [title, setTitle] = useState("");
  const [hint, setHint] = useState("");
  const first = starterVersion("", "");
  const [system, setSystem] = useState(first.system_text);
  const [template, setTemplate] = useState(first.user_template);
  const [model, setModel] = useState(first.model);
  const [effort, setEffort] = useState(first.effort);
  const [maxTokens, setMaxTokens] = useState(String(first.max_tokens));
  const [fields, setFields] = useState(JSON.stringify(first.field_definitions, null, 2));
  const [schema, setSchema] = useState(JSON.stringify(first.output_schema, null, 2));
  const [tools, setTools] = useState<string[]>([]);
  const [note, setNote] = useState("First version");
  // Starter text follows the category and title until the person edits the fields or the schema.
  const [edited, setEdited] = useState(false);
  const [source, setSource] = useState("starter");
  const prompts = usePrompts();
  const [error, setError] = useState<string | null>(null);
  const create = useCreatePrompt();

  function applyStarter(nextCategory: string, nextTitle: string) {
    const starter = starterVersion(nextCategory, nextTitle);
    setSystem(starter.system_text);
    setTemplate(starter.user_template);
    setFields(JSON.stringify(starter.field_definitions, null, 2));
    setSchema(JSON.stringify(starter.output_schema, null, 2));
  }

  function changeCategory(value: string) {
    const upper = value.toUpperCase();
    setCategory(upper);
    if (step === "read") setKey(`doc.read.${upper.toLowerCase()}`);
    if (source === "starter" && !edited) {
      const next = starterFields(upper);
      setFields(JSON.stringify(next, null, 2));
      setSchema(JSON.stringify(starterSchema(upper, next), null, 2));
    }
  }

  function changeTitle(value: string) {
    setTitle(value);
    if (source === "starter" && !edited) setSystem(starterVersion(category, value).system_text);
  }

  // Copy every setting of an existing prompt. Its field keys carry its own category, so the new keys are set afterwards.
  async function chooseSource(value: string) {
    setSource(value);
    setEdited(false);
    if (value === "starter") return applyStarter(category, title);
    try {
      const copy = await api<PromptDetail>(`/ai/prompts/${value}`);
      const v = copy.active;
      if (!v) return;
      setSystem(v.system_text);
      setTemplate(v.user_template);
      setModel(v.model);
      setEffort(v.effort);
      setMaxTokens(String(v.max_tokens));
      setFields(JSON.stringify(v.field_definitions, null, 2));
      setSchema(JSON.stringify(v.output_schema, null, 2));
      setTools(v.tools ?? []);
      setEdited(true);
    } catch {
      setError("Could not copy that prompt.");
    }
  }

  function build(): PromptCreate | null {
    let parsedSchema: Record<string, unknown>;
    let parsedFields: FieldDefinition[];
    try {
      parsedSchema = JSON.parse(schema) as Record<string, unknown>;
      parsedFields = JSON.parse(fields) as FieldDefinition[];
    } catch {
      setError("The output schema and field definitions must be valid JSON.");
      return null;
    }
    const tokens = Number(maxTokens);
    if (!Number.isInteger(tokens) || tokens <= 0) {
      setError("Max tokens must be a whole number above zero.");
      return null;
    }
    if (!key.trim() || !title.trim()) {
      setError("Key and title are required.");
      return null;
    }
    if (step === "read" && !category.trim()) {
      setError("Read prompts need a category.");
      return null;
    }
    setError(null);
    return {
      key: key.trim(),
      step,
      category: step === "read" ? category.trim() : null,
      title: title.trim(),
      recognition_hint: hint.trim() || null,
      system_text: system,
      user_template: template,
      model,
      effort,
      max_tokens: tokens,
      output_schema: parsedSchema,
      field_definitions: parsedFields,
      tools,
      note: note.trim() || null,
    };
  }

  function submit() {
    const body = build();
    if (body) create.mutate(body, { onSuccess: (created) => onCreated(created.key) });
  }

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Add prompt</h2>
      <Label text="Start from">
        <select className={INPUT} value={source} onChange={(e) => void chooseSource(e.target.value)}>
          <option value="starter">Starter template (recommended)</option>
          {(prompts.data?.read ?? []).filter((p) => !p.deleted && p.category !== "UNKNOWN").map((p) => (
            <option key={p.key} value={p.key}>Copy of {p.title}</option>
          ))}
        </select>
      </Label>
      <div className="grid gap-3 sm:grid-cols-2">
        <Label text="Document category (uppercase)">
          <input className={INPUT} value={category} onChange={(e) => changeCategory(e.target.value)} />
        </Label>
        <Label text="Key (doc.read.<category>)">
          <input className={`${INPUT} font-mono`} value={key} onChange={(e) => setKey(e.target.value)} />
        </Label>
      </div>
      <Label text="Title">
        <input className={INPUT} value={title} onChange={(e) => changeTitle(e.target.value)} />
      </Label>
      <Label text="Recognition hint (how the classifier spots this document)">
        <input className={INPUT} value={hint} onChange={(e) => setHint(e.target.value)} />
      </Label>
      <Label text="System text">
        <textarea className={`${INPUT} h-32 font-mono`} value={system} onChange={(e) => { setSystem(e.target.value); setEdited(true); }} />
      </Label>
      <Label text="User template">
        <textarea className={`${INPUT} h-24 font-mono`} value={template} onChange={(e) => setTemplate(e.target.value)} />
      </Label>
      <div className="grid gap-3 sm:grid-cols-2">
        <Label text="Model">
          <input className={INPUT} value={model} onChange={(e) => setModel(e.target.value)} />
        </Label>
        <Label text="Effort">
          <select className={INPUT} value={effort} onChange={(e) => setEffort(e.target.value)}>
            {EFFORTS.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </Label>
        <Label text="Max tokens">
          <input className={INPUT} inputMode="numeric" value={maxTokens} onChange={(e) => setMaxTokens(e.target.value)} />
        </Label>
      </div>
      <ToolPicker value={tools} onChange={setTools} />
      <Label text="Field definitions (JSON list of key, label, type, required, hint)">
        <textarea className={`${INPUT} h-32 font-mono`} value={fields} onChange={(e) => { setFields(e.target.value); setEdited(true); }} />
      </Label>
      <Label text="Output schema (JSON, every value needs value, quote and page)">
        <textarea className={`${INPUT} h-48 font-mono`} value={schema} onChange={(e) => { setSchema(e.target.value); setEdited(true); }} />
      </Label>
      <Label text="Change note">
        <input className={INPUT} value={note} onChange={(e) => setNote(e.target.value)} />
      </Label>
      {error && <p role="alert" className="text-sm text-[var(--bad)]">{error}</p>}
      {create.error && <p role="alert" className="text-sm text-[var(--bad)]">Create failed. {create.error.message}</p>}
      <div className="flex gap-2">
        <button type="button" className={BUTTON} disabled={create.isPending} onClick={submit}>
          Create prompt
        </button>
        <button type="button" className={BUTTON_QUIET} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </section>
  );
}
