import { BUTTON_QUIET, INPUT } from "./fieldStyles";
import type { ItemDefinition } from "./types";

const ITEM_TYPES = ["string", "date", "number", "boolean", "enum"];
const EMPTY_ITEM: ItemDefinition = { key: "", label: "", type: "string", required: false, hint: null };

type Props = {
  items: ItemDefinition[];
  lockedKeys: Set<string>;
  onChange: (items: ItemDefinition[]) => void;
};

// Output schema entry for an array field: { value: [ { ...item keys, quote, page } ] }.
export function arrayFieldSchema(items: ItemDefinition[]): Record<string, unknown> {
  const text = { type: "string" };
  const properties: Record<string, unknown> = { quote: text, page: { type: "integer" } };
  items.forEach((item) => {
    properties[item.key] = text;
  });
  const required = [...items.filter((i) => i.required).map((i) => i.key), "quote", "page"];
  return {
    type: "object",
    additionalProperties: false,
    required: ["value"],
    properties: { value: { type: "array", items: { type: "object", additionalProperties: false, required, properties } } },
  };
}

export default function ArrayItemsEditor({ items, lockedKeys, onChange }: Props) {
  function update(index: number, patch: Partial<ItemDefinition>) {
    onChange(items.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  return (
    <div className="ml-4 space-y-1.5 border-l border-[var(--line)] pl-3">
      <p className="text-xs text-[var(--muted)]">
        Item fields. Every row also gets its own quote and page. Items are one level only, so an item cannot be an array.
      </p>
      {items.map((item, index) => {
        const locked = lockedKeys.has(item.key);
        return (
          <div key={index} className="grid gap-1.5 sm:grid-cols-[1.2fr_1.2fr_0.8fr_auto_1.4fr_auto]">
            <input aria-label="Item key" className={`${INPUT} font-mono`} value={item.key} readOnly={locked} onChange={(e) => update(index, { key: e.target.value })} />
            <input aria-label="Item label" className={INPUT} value={item.label} onChange={(e) => update(index, { label: e.target.value })} />
            <select aria-label="Item type" className={INPUT} value={item.type} onChange={(e) => update(index, { type: e.target.value })}>
              {ITEM_TYPES.map((type) => (
                <option key={type}>{type}</option>
              ))}
            </select>
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={item.required} onChange={(e) => update(index, { required: e.target.checked })} />
              Required
            </label>
            <input aria-label="Item hint" className={INPUT} placeholder="Hint" value={item.hint ?? ""} onChange={(e) => update(index, { hint: e.target.value || null })} />
            {locked ? (
              <span className="self-center text-xs text-[var(--muted)]">Locked</span>
            ) : (
              <button type="button" className={BUTTON_QUIET} onClick={() => onChange(items.filter((_, i) => i !== index))}>
                Remove
              </button>
            )}
          </div>
        );
      })}
      <div className="flex gap-2">
        <button type="button" className={BUTTON_QUIET} onClick={() => onChange([...items, EMPTY_ITEM])}>
          Add item field
        </button>
      </div>
    </div>
  );
}
