import { useTools } from "./hooks";

type Props = { value: string[]; onChange: (names: string[]) => void };

// Read only date helpers. A prompt with none ticked makes one model call. Any tool adds a second call for the final answer.
export default function ToolPicker({ value, onChange }: Props) {
  const { data, isLoading, error } = useTools();
  const toggle = (name: string) => onChange(value.includes(name) ? value.filter((n) => n !== name) : [...value, name]);
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium">Tools the model may call</legend>
      <p className="text-xs text-[var(--muted)]">
        Read only date helpers. Leave all off for a single model call. Any tool adds a second call for the final answer, so tick only what this document type needs.
      </p>
      {isLoading && <p className="text-sm text-[var(--muted)]">Loading tools</p>}
      {error && <p role="alert" className="text-sm text-[var(--bad)]">Could not load the tool list.</p>}
      <ul className="grid gap-1.5 sm:grid-cols-2">
        {(data ?? []).map((tool) => (
          <li key={tool.name}>
            <label className="flex h-full items-start gap-2 rounded-xl border border-[var(--line)] px-3 py-2 text-sm hover:bg-[var(--soft)]">
              <input type="checkbox" className="mt-1" checked={value.includes(tool.name)} onChange={() => toggle(tool.name)} />
              <span>
                <span className="block font-mono text-xs font-semibold">{tool.name}</span>
                <span className="block text-xs text-[var(--muted)]">{tool.description}</span>
              </span>
            </label>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}
