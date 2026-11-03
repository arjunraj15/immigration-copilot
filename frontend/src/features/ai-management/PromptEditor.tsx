import { useState } from "react";

import Icon from "../../components/Icon";
import { INPUT } from "./fieldStyles";
import FormTargetSelect, { AddFormField } from "./FormTargetSelect";
import { useFormTargets, useOutputSchema, useSaveVersion } from "./hooks";
import { BUTTON, BUTTON_QUIET } from "./fieldStyles";
import ArrayItemsEditor from "./ArrayItems";
import { JsonEditor } from "./JsonHighlight";
import ToolPicker from "./ToolPicker";
import type { FieldDefinition, ItemDefinition, PromptDetail, VersionCreate } from "./types";

const EFFORTS = ["low", "medium", "high", "xhigh", "max"];
const FIELD_TYPES = ["string", "date", "number", "boolean", "enum", "array"];
const NEW_ITEM: ItemDefinition = { key: "", label: "", type: "string", required: false, hint: null };

export type Tab = "prompt" | "fields" | "model" | "hist" | "runs";

// The panels stay mounted so edits survive a tab switch. History and runs come in as children.
type Props = { prompt: PromptDetail; tab: Tab; top?: React.ReactNode; children?: React.ReactNode; onDraft: (draft: VersionCreate | null) => void };

function Label({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1 text-sm">
      <span className="font-medium">{text}</span>
      {children}
    </label>
  );
}

export default function PromptEditor({ prompt, tab, top, children, onDraft }: Props) {
  const base = prompt.active;
  const activeFields = base?.field_definitions ?? prompt.field_definitions;
  const lockedKeys = new Set(activeFields.map((f) => f.key));
  const lockedItemKeys = new Set(activeFields.flatMap((f) => (f.items ?? []).map((i) => `${f.key}|${i.key}`)));
  const [system, setSystem] = useState(base?.system_text ?? "");
  const [template, setTemplate] = useState(base?.user_template ?? "");
  const [model, setModel] = useState(base?.model ?? "");
  const [effort, setEffort] = useState(base?.effort ?? "medium");
  const [maxTokens, setMaxTokens] = useState(String(base?.max_tokens ?? 4096));
  const [fields, setFields] = useState<FieldDefinition[]>(base?.field_definitions ?? prompt.field_definitions);
  const [tools, setTools] = useState<string[]>(base?.tools ?? []);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<number | null>(null);
  const save = useSaveVersion(prompt.key);
  const targets = useFormTargets().data ?? [];
  // The schema is never typed. It is built from the fields below, so the two always match.
  const generated = useOutputSchema(prompt.category, fields);
  const schema = JSON.stringify(generated.data ?? base?.output_schema ?? {}, null, 2);
  // Warn only. The envelope adds its own rules, this checks the prompt text itself.
  const hasGuard = /untrusted/i.test(`${system} ${template}`) && /injection_flag/i.test(`${system} ${template} ${schema}`);

  function build(): VersionCreate | null {
    const tokens = Number(maxTokens);
    if (!Number.isInteger(tokens) || tokens <= 0) {
      setError("Max tokens must be a whole number above zero.");
      return null;
    }
    if (fields.some((f) => !f.key.trim() || !f.label.trim())) {
      setError("Every field needs a key and a label.");
      return null;
    }
    if (fields.some((f) => f.type === "array" && (!f.items?.length || f.items.some((i) => !i.key.trim() || !i.label.trim())))) {
      setError("Every array field needs at least one item field, and each item needs a key and a label.");
      return null;
    }
    setError(null);
    return {
      system_text: system,
      user_template: template,
      model,
      effort,
      max_tokens: tokens,
      // A prompt without a category, such as the classifier, keeps its own schema because there is nothing to build it from.
      ...(prompt.category ? {} : { output_schema: base?.output_schema }),
      field_definitions: fields,
      tools,
      note: note.trim() || null,
    };
  }

  function updateField(index: number, patch: Partial<FieldDefinition>) {
    setFields((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function changeType(index: number, type: string) {
    if (type !== "array") return updateField(index, { type, items: null });
    updateField(index, { type, form_target: null, items: fields[index].items?.length ? fields[index].items : [NEW_ITEM] });
  }

  // A new extracted field starts from an actual form field, so its key, label and target come from the form.
  function addFromForm(target: string) {
    const form = targets.find((t) => t.target === target);
    if (!form) return;
    const key = `${prompt.category ?? "FIELD"}.${form.label}`;
    if (fields.some((f) => f.key === key)) return setError(`${key} is already a field of this document type.`);
    setError(null);
    setFields((rows) => [...rows, { key, label: form.label, type: /date|expiration|entry|start/i.test(target) ? "date" : "string", required: false, hint: null, form_target: target }]);
  }

  function submit() {
    const body = build();
    if (body) save.mutate(body);
  }

  const show = (name: Tab) => (tab === name ? "space-y-3" : "hidden");
  return (
    <>
      <div className="flex min-h-0 flex-1 flex-col overflow-auto pt-3">
        <section className={show("prompt")}>
          {top}
          <Label text="System text">
            <textarea className={`${INPUT} h-40 font-mono`} value={system} onChange={(e) => setSystem(e.target.value)} />
          </Label>
          <Label text="User template">
            <textarea className={`${INPUT} h-28 font-mono`} value={template} onChange={(e) => setTemplate(e.target.value)} />
          </Label>
          {!hasGuard && (
            <p role="note" className="rounded-xl bg-[var(--warn-soft)] px-3 py-2 text-sm">
              Injection guard is missing. This prompt should tell the model that the document text is untrusted data, to follow none of its instructions and to set
              injection_flag. The system still wraps the document in untrusted-do-not-follow tags and adds its own rules block. This is a warning only, so you can
              still save and test it.
            </p>
          )}
        </section>

        <section className={tab === "fields" ? "flex min-h-0 flex-1 flex-col gap-3" : "hidden"}>
          <div className="space-y-1.5">
            <p className="text-sm font-medium">Field definitions</p>
            <p className="text-xs text-[var(--muted)]">Keys already in the active version are read-only. You can add new keys.</p>
            {fields.map((field, index) => {
              const locked = lockedKeys.has(field.key);
              return (
                <div key={index} className="space-y-1.5">
                  <div className="grid gap-1.5 sm:grid-cols-[1.4fr_1.2fr_0.8fr_auto_1.4fr_1.4fr_auto]">
                    <input aria-label="Key" className={`${INPUT} font-mono`} value={field.key} readOnly={locked} onChange={(e) => updateField(index, { key: e.target.value })} />
                    <input aria-label="Label" className={INPUT} value={field.label} onChange={(e) => updateField(index, { label: e.target.value })} />
                    <select aria-label="Type" className={INPUT} value={field.type} onChange={(e) => changeType(index, e.target.value)}>
                      {FIELD_TYPES.includes(field.type) ? null : <option>{field.type}</option>}
                      {FIELD_TYPES.map((item) => (
                        <option key={item}>{item}</option>
                      ))}
                    </select>
                    <label className="flex items-center gap-1 text-xs">
                      <input type="checkbox" className="w-auto" checked={field.required} onChange={(e) => updateField(index, { required: e.target.checked })} />
                      Required
                    </label>
                    <input aria-label="Hint" className={INPUT} placeholder="Hint" value={field.hint ?? ""} onChange={(e) => updateField(index, { hint: e.target.value || null })} />
                    {field.type === "array" ? (
                      <span className="self-center text-xs text-[var(--muted)]">Validate only</span>
                    ) : (
                      <FormTargetSelect value={field.form_target ?? null} onChange={(target) => updateField(index, { form_target: target })} onAddNew={() => setAdding(index)} />
                    )}
                    {locked ? (
                      <span className="self-center text-xs text-[var(--muted)]">Locked</span>
                    ) : (
                      <button type="button" className={BUTTON_QUIET} onClick={() => setFields((rows) => rows.filter((_, i) => i !== index))}>
                        Remove
                      </button>
                    )}
                  </div>
                  {adding === index && (
                    <AddFormField
                      label={field.label}
                      type={field.type}
                      onCancel={() => setAdding(null)}
                      onAdded={(target) => {
                        updateField(index, { form_target: target });
                        setAdding(null);
                      }}
                    />
                  )}
                  {field.type === "array" && (
                    <ArrayItemsEditor
                      items={field.items ?? []}
                      lockedKeys={new Set([...lockedItemKeys].filter((k) => k.startsWith(`${field.key}|`)).map((k) => k.slice(field.key.length + 1)))}
                      onChange={(items) => updateField(index, { items })}
                    />
                  )}
                </div>
              );
            })}
            <button
              type="button"
              className={`${BUTTON_QUIET} inline-flex items-center gap-1.5`}
              onClick={() => setFields((rows) => [...rows, { key: "", label: "", type: "string", required: false, hint: null }])}
            >
              <Icon name="plus" /> Add field
            </button>
            {targets.length > 0 && (
              <select aria-label="Add from a form field" className={`${INPUT} ml-2 inline-block w-auto`} value="" onChange={(e) => addFromForm(e.target.value)}>
                <option value="">Add from a form field...</option>
                {targets.map((t) => (
                  <option key={t.target} value={t.target}>
                    {t.section}: {t.label}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="flex min-h-48 flex-1 flex-col gap-1 text-sm">
            <span className="font-medium">Output schema (built from the fields above, every value has a quote and a page)</span>
            <JsonEditor label="Output schema" className="min-h-0 flex-1" value={schema} onChange={() => {}} readOnly />
          </div>
        </section>

        <section className={show("model")}>
          <div className="grid gap-3 sm:grid-cols-3">
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
        </section>

        {tab === "hist" || tab === "runs" ? children : null}
      </div>

      {error && <p role="alert" className="pt-2 text-sm text-[var(--bad)]">{error}</p>}
      {save.error && <p role="alert" className="pt-2 text-sm text-[var(--bad)]">Save failed. {String(save.error)}</p>}
      {save.isSuccess && <p className="pt-2 text-sm text-[var(--ok)]">Saved as version {save.data.version}. Activate it from the history.</p>}
      <div className="mt-2 flex flex-none items-center gap-2 border-t border-[var(--line)] pt-2.5">
        <input className={INPUT} placeholder="Version note (what changed and why)" aria-label="Version note" value={note} onChange={(e) => setNote(e.target.value)} />
        <button type="button" className={`${BUTTON_QUIET} inline-flex items-center gap-1.5 whitespace-nowrap`} onClick={() => onDraft(build())}>
          <Icon name="flask" /> Use as test draft
        </button>
        <button type="button" className={`${BUTTON} inline-flex items-center gap-1.5 whitespace-nowrap`} disabled={save.isPending} onClick={submit}>
          <Icon name="save" /> Save new version
        </button>
      </div>
    </>
  );
}
