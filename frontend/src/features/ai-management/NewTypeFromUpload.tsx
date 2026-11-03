import { useState } from "react";

import Icon from "../../components/Icon";
import { useDocViewer } from "../cases/docViewer";
import { BUTTON, BUTTON_QUIET, INPUT } from "./fieldStyles";
import FormTargetSelect from "./FormTargetSelect";
import { useCreateType, useDraftType } from "./hooks";
import type { DraftField, TypeDraft } from "./types";

type Props = { uploadId: string; onClose: () => void; onOpenType: (key: string) => void };

const BLANK_FIELD: DraftField = { key: "", label: "", type: "string", required: false, hint: "", quote: "", page: 0, verified: false, from_image: false, form_target: null, new_form_field: false };
const BLANK: Pick<TypeDraft, "category" | "title" | "recognition_hint" | "system_text" | "fields"> = {
  category: "",
  title: "",
  recognition_hint: "",
  system_text: "",
  fields: [{ ...BLANK_FIELD }],
};

const STEPS = [
  { title: "The AI reads the file", body: "It suggests a name, how to recognise the type, read instructions and the fields to extract." },
  { title: "It maps fields to the form", body: "Each field can fill a Form draft input, or become a new additional client field." },
  { title: "You review and create", body: "Edit anything, then create the type. The file is read again and leaves the review queue." },
];

function EvidenceChip({ field }: { field: DraftField }) {
  if (!field.quote) return <span className="rounded-full bg-[var(--soft)] px-2 py-0.5 text-xs font-semibold text-[var(--muted)]">No quote. Added by hand</span>;
  const tone = field.verified ? "bg-[var(--ok-soft)] text-[var(--ok)]" : "bg-[var(--warn-soft)] text-[var(--warn)]";
  const word = field.verified ? "Quote found" : field.from_image ? "Read from image" : "Quote not found";
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${tone}`} title={field.quote}>
      {word}, page {field.page}
    </span>
  );
}

function FieldRow({ field, onChange, onRemove }: { field: DraftField; onChange: (next: DraftField) => void; onRemove: () => void }) {
  return (
    <tr className="border-t border-[var(--line)] align-top">
      <td className="px-2 py-2">
        <input className={INPUT} aria-label="Field label" value={field.label} maxLength={120} onChange={(e) => onChange({ ...field, label: e.target.value })} />
        <div className="mt-1"><EvidenceChip field={field} /></div>
      </td>
      <td className="px-2 py-2">
        <select className={INPUT} aria-label="Field type" value={field.type} onChange={(e) => onChange({ ...field, type: e.target.value as DraftField["type"] })}>
          <option value="string">Text</option>
          <option value="date">Date</option>
          <option value="number">Number</option>
        </select>
      </td>
      <td className="px-2 py-2 text-center">
        <input type="checkbox" aria-label="Required" checked={field.required} onChange={(e) => onChange({ ...field, required: e.target.checked })} />
      </td>
      <td className="px-2 py-2">
        <input className={INPUT} aria-label="Hint for the reader" value={field.hint} onChange={(e) => onChange({ ...field, hint: e.target.value })} />
      </td>
      <td className="px-2 py-2">
        <FormTargetSelect
          value={field.form_target ?? null}
          pendingNew={field.new_form_field ? field.label.trim() || "new field" : null}
          onChange={(target) => onChange({ ...field, form_target: target, new_form_field: false })}
          onAddNew={() => onChange({ ...field, form_target: null, new_form_field: true })}
        />
        {field.new_form_field && <p className="mt-1 text-xs text-[var(--muted)]">Made as an additional client field when the type is created.</p>}
      </td>
      <td className="px-2 py-2">
        <button type="button" className={BUTTON_QUIET} aria-label={`Remove ${field.label || "field"}`} onClick={onRemove}>
          <Icon name="trash" />
        </button>
      </td>
    </tr>
  );
}

// Draft a document type from one unclassified file. The AI suggests, the person edits and creates.
export default function NewTypeFromUpload({ uploadId, onClose, onOpenType }: Props) {
  const open = useDocViewer();
  const draftType = useDraftType();
  const create = useCreateType(uploadId);
  const [form, setForm] = useState<typeof BLANK | null>(null);
  const [draft, setDraft] = useState<TypeDraft | null>(null);
  const set = <K extends keyof typeof BLANK>(key: K, value: (typeof BLANK)[K]) => setForm((f) => (f ? { ...f, [key]: value } : f));
  const ask = () =>
    draftType.mutate(uploadId, {
      onSuccess: (result) => {
        setDraft(result);
        if (result.status === "OK") setForm({ category: result.category, title: result.title, recognition_hint: result.recognition_hint, system_text: result.system_text, fields: result.fields });
      },
    });
  const fields = form?.fields.filter((f) => f.label.trim()) ?? [];
  const ready = !!form && !!form.category && !!form.title.trim() && !!form.recognition_hint.trim() && !!form.system_text.trim() && fields.length > 0;
  const submit = () => form && create.mutate({ ...form, fields });

  if (create.data) {
    return (
      <div className="space-y-3" role="status">
        <p className="font-semibold">
          <Icon name="check" className="mr-1.5 inline h-4 w-4 align-[-3px]" />
          Document type {create.data.category} is created and active. The file is being read again, so it leaves the review queue once it is typed.
        </p>
        <div className="flex gap-2">
          <button type="button" className={BUTTON} onClick={() => onOpenType(create.data.key)}>Open the new type</button>
          <button type="button" className={BUTTON_QUIET} onClick={onClose}>Back to review queue</button>
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={`${BUTTON_QUIET} inline-flex items-center gap-1.5`} onClick={onClose}>
          <Icon name="arrow" className="h-4 w-4 rotate-180" /> Back to review queue
        </button>
        <button type="button" className={BUTTON_QUIET} onClick={() => open(uploadId)}>View document</button>
        <h2 className="text-lg font-bold">Add as new document type</h2>
      </div>
      {!form && (
        <div className="mx-auto max-w-2xl space-y-5 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-6">
          <div className="space-y-1">
            <h3 className="text-base font-bold">Teach the system a new document type</h3>
            <p className="text-sm text-[var(--muted)]">This file did not match any known type. The AI can draft the type for you, and you stay in control of what is created.</p>
          </div>
          <ol className="space-y-3">
            {STEPS.map((step, i) => (
              <li key={step.title} className="flex gap-3">
                <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-[var(--soft)] text-xs font-bold" aria-hidden="true">{i + 1}</span>
                <div className="text-sm">
                  <p className="font-semibold">{step.title}</p>
                  <p className="text-[var(--muted)]">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="flex flex-wrap items-center gap-2 border-t border-[var(--line)] pt-4">
            <button type="button" className={`${BUTTON} inline-flex items-center gap-1.5`} disabled={draftType.isPending} onClick={ask}>
              <Icon name="ai" /> {draftType.isPending ? "Reading the file..." : "Draft with AI"}
            </button>
            <button type="button" className={BUTTON_QUIET} disabled={draftType.isPending} onClick={() => setForm({ ...BLANK, fields: [{ ...BLANK_FIELD }] })}>Fill in by hand</button>
            {draftType.isPending && <span role="status" className="text-sm text-[var(--muted)]">This can take a few seconds.</span>}
          </div>
          {draftType.error && <p role="alert" className="text-sm text-[var(--bad)]">{draftType.error.message}</p>}
          {draft?.status === "NEEDS_REVIEW" && <p role="alert" className="text-sm text-[var(--warn)]">Needs human review. {draft.error}</p>}
        </div>
      )}
      {draft?.matches_existing && (
        <p role="status" className="rounded-xl bg-[var(--warn-soft)] px-3 py-2 text-sm text-[var(--warn)]">
          This looks like the existing type {draft.matches_existing}. {draft.matches_reason} Go back and use Set type if that is right.
        </p>
      )}
      {draft?.injection_flag && <p role="alert" className="rounded-xl bg-[var(--bad-soft)] px-3 py-2 text-sm text-[var(--bad)]">The file holds instructions addressed to the AI. They were ignored. Check the draft with care.</p>}
      {form && (
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="block text-sm">Type name<input className={`${INPUT} font-mono`} value={form.category} maxLength={80} onChange={(e) => set("category", e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "_"))} /></label>
            <label className="block text-sm">Title<input className={INPUT} value={form.title} maxLength={200} onChange={(e) => set("title", e.target.value)} /></label>
          </div>
          <label className="block text-sm">How to recognise it<textarea className={INPUT} rows={2} value={form.recognition_hint} onChange={(e) => set("recognition_hint", e.target.value)} /></label>
          <label className="block text-sm">Read instructions<textarea className={`${INPUT} font-mono`} rows={8} value={form.system_text} onChange={(e) => set("system_text", e.target.value)} /></label>
          <div className="overflow-x-auto rounded-xl border border-[var(--line)]">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="bg-[var(--soft)] text-left">
                  {["Field", "Type", "Required", "Hint", "Fills form field", ""].map((title) => <th key={title} scope="col" className="px-2 py-2 font-semibold">{title}</th>)}
                </tr>
              </thead>
              <tbody>
                {form.fields.map((f, i) => (
                  <FieldRow key={i} field={f} onChange={(next) => set("fields", form.fields.map((x, j) => (j === i ? next : x)))} onRemove={() => set("fields", form.fields.filter((_, j) => j !== i))} />
                ))}
              </tbody>
            </table>
          </div>
          <button type="button" className={`${BUTTON_QUIET} inline-flex items-center gap-1.5`} onClick={() => set("fields", [...form.fields, { ...BLANK_FIELD }])}>
            <Icon name="plus" /> Add field
          </button>
          <div className="flex items-center gap-3">
            <button type="submit" className={BUTTON} disabled={!ready || create.isPending}>{create.isPending ? "Creating..." : "Create type and read document again"}</button>
            {!ready && <span className="text-sm text-[var(--muted)]">Needs a name, title, hint, instructions and at least one field.</span>}
          </div>
          {create.error && <p role="alert" className="text-sm text-[var(--bad)]">{create.error.message}</p>}
        </form>
      )}
    </div>
  );
}
