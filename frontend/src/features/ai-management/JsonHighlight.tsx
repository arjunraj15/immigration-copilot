import { useRef } from "react";

const TOKEN = /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

// Regex based, so half typed JSON still gets colored.
function tokens(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(TOKEN)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    const [whole, str, colon, word] = m;
    const color = str ? (colon ? "var(--ai)" : "var(--ok)") : word ? "var(--bad)" : "var(--warn)";
    out.push(
      <span key={at} style={{ color }}>
        {str && colon ? str : whole}
      </span>,
    );
    if (str && colon) out.push(colon);
    last = at + whole.length;
  }
  out.push(text.slice(last));
  return out;
}

const MONO = "font-mono text-xs leading-normal whitespace-pre";

export function JsonView({ text, className = "" }: { text: string; className?: string }) {
  return <pre className={`${MONO} overflow-auto ${className}`}>{tokens(text)}</pre>;
}

// A textarea over a colored copy of its own text. The textarea text is transparent, so only the caret and selection show.
export function JsonEditor({ value, onChange, label, className = "", readOnly = false }: { value: string; onChange: (v: string) => void; label: string; className?: string; readOnly?: boolean }) {
  const layer = useRef<HTMLPreElement>(null);
  const sync = (e: React.UIEvent<HTMLTextAreaElement>) => {
    if (!layer.current) return;
    layer.current.scrollTop = e.currentTarget.scrollTop;
    layer.current.scrollLeft = e.currentTarget.scrollLeft;
  };
  const box = `${MONO} absolute inset-0 m-0 rounded border border-transparent px-2 py-1.5`;
  return (
    <div className={`relative ${className}`}>
      <pre ref={layer} aria-hidden="true" className={`${box} overflow-hidden bg-[var(--surface)]`}>
        {tokens(value)}
        {"\n"}
      </pre>
      <textarea
        aria-label={label}
        spellCheck={false}
        readOnly={readOnly}
        wrap="off"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onScroll={sync}
        className={`${box} resize-none overflow-auto !border-[var(--line)] bg-transparent text-transparent caret-[var(--ink)]`}
      />
    </div>
  );
}
