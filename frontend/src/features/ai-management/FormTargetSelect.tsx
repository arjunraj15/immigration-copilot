import { useState } from "react";

import { BUTTON, BUTTON_QUIET, INPUT } from "./fieldStyles";
import { useAddFormField, useFormTargets } from "./hooks";
import type { NewFormField } from "./types";

const ADD = "__add__";
const NEW = "__new__";
const ADDITIONAL = "Additional client fields";

type SelectProps = {
  value: string | null;
  // A drafted field that needs a field the form does not have yet. It is shown as New and made when the type is created.
  pendingNew?: string | null;
  onChange: (target: string | null) => void;
  onAddNew: () => void;
};

// The form fields an extracted value can fill, grouped by form section. Additional client fields come last, with the add option.
export default function FormTargetSelect({ value, pendingNew, onChange, onAddNew }: SelectProps) {
  const targets = useFormTargets().data ?? [];
  const sections = [...new Set(targets.map((t) => t.section))].filter((s) => s !== ADDITIONAL);
  const extras = targets.filter((t) => t.section === ADDITIONAL);
  const unknown = !!value && !targets.some((t) => t.target === value);
  return (
    <select
      aria-label="Fills form field"
      title="The form field this value fills. Validate only means it is checked but never fills a form field."
      className={INPUT}
      value={pendingNew ? NEW : (value ?? "")}
      onChange={(e) => {
        if (e.target.value === ADD) return onAddNew();
        if (e.target.value !== NEW) onChange(e.target.value || null);
      }}
    >
      <option value="">Validate only</option>
      {unknown && <option value={value ?? ""}>{value}</option>}
      {sections.map((section) => (
        <optgroup key={section} label={section}>
          {targets.filter((t) => t.section === section).map((t) => (
            <option key={t.target} value={t.target}>{t.label}</option>
          ))}
        </optgroup>
      ))}
      <optgroup label={ADDITIONAL}>
        {extras.map((t) => (
          <option key={t.target} value={t.target}>{t.label}</option>
        ))}
        {pendingNew && <option value={NEW}>New: {pendingNew}</option>}
        <option value={ADD}>+ Add new field...</option>
      </optgroup>
    </select>
  );
}

type FormProps = { label: string; type: string; onAdded: (target: string) => void; onCancel: () => void };

// The small form behind + Add new field. The label and type start from the extracted field it is made for.
export function AddFormField({ label, type, onAdded, onCancel }: FormProps) {
  const add = useAddFormField();
  const [name, setName] = useState(label);
  const [kind, setKind] = useState<NewFormField["value_type"]>(type === "date" || type === "number" ? type : "string");
  const submit = () => add.mutate({ label: name, value_type: kind }, { onSuccess: (field) => onAdded(field.target) });
  return (
    <div role="group" aria-label="Add an additional client field" className="flex flex-wrap items-end gap-2 rounded-xl border border-[var(--line)] bg-[var(--soft)] p-2">
      <label className="block min-w-48 flex-1 text-xs font-medium">
        New form field name
        <input className={INPUT} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="block text-xs font-medium">
        Type
        <select className={INPUT} value={kind} onChange={(e) => setKind(e.target.value as NewFormField["value_type"])}>
          <option value="string">Text</option>
          <option value="date">Date</option>
          <option value="number">Number</option>
        </select>
      </label>
      <button type="button" className={BUTTON} disabled={!name.trim() || add.isPending} onClick={submit}>
        {add.isPending ? "Adding..." : "Add field"}
      </button>
      <button type="button" className={BUTTON_QUIET} onClick={onCancel}>Cancel</button>
      {add.error && <p role="alert" className="w-full text-xs text-[var(--bad)]">{add.error.message}</p>}
      <p className="w-full text-xs text-[var(--muted)]">It joins the Additional client fields section of the Form draft for every case.</p>
    </div>
  );
}
