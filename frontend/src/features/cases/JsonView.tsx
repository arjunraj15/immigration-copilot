import type { ReactNode } from "react";

const TOKEN = /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

// Indented JSON with tinted keys, strings, numbers and literals. Built from spans, never raw HTML.
function tint(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(TOKEN)) {
    const at = match.index ?? 0;
    if (at > last) parts.push(text.slice(last, at));
    const [whole, str, colon, literal] = match;
    const color = str ? (colon ? "text-[#1d4ed8]" : "text-[#047857]") : literal ? "text-[#b45309]" : "text-[#7c3aed]";
    parts.push(
      <span key={at} className={color}>
        {str && colon ? str : whole}
      </span>,
    );
    if (str && colon) parts.push(colon);
    last = at + whole.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export default function JsonView({ value, maxHeight = "70vh" }: { value: unknown; maxHeight?: string }) {
  return (
    <pre style={{ maxHeight }}
      className="overflow-auto whitespace-pre-wrap break-words rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3 font-mono text-xs">
      {tint(JSON.stringify(value, null, 2))}
    </pre>
  );
}
