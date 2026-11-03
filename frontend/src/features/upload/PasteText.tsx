import { useState } from "react";

// Pasted text becomes a text document, so a call note or message goes through the same upload as a file.
const KINDS = [
  { value: "zoom-notes", label: "Zoom call notes" },
  { value: "whatsapp-message", label: "WhatsApp message" },
  { value: "email-message", label: "Email" },
];

export default function PasteText({ onAdd }: { onAdd: (file: File) => void }) {
  const [kind, setKind] = useState(KINDS[0].value);
  const [text, setText] = useState("");
  const [count, setCount] = useState(0);
  const add = () => {
    const name = count === 0 ? `${kind}.txt` : `${kind}-${count + 1}.txt`;
    onAdd(new File([text.trim()], name, { type: "text/plain" }));
    setCount(count + 1);
    setText("");
  };
  return (
    <details className="mt-3 rounded-2xl border border-[var(--line)] p-3">
      <summary className="cursor-pointer font-semibold">Paste text from a call or message</summary>
      <p className="mt-2 text-sm text-[var(--muted)]">It is added as a document. What it says is read as a claim, never as a fact.</p>
      <select
        aria-label="Kind of text"
        value={kind}
        onChange={(event) => {
          setKind(event.target.value);
          setCount(0);
        }}
        className="mt-2 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5 font-semibold"
      >
        {KINDS.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>
      <textarea
        aria-label="Pasted text"
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={4}
        placeholder="Paste the text here"
        className="mt-2 w-full rounded-xl border border-[var(--line)] px-3 py-2"
      />
      <button
        type="button"
        disabled={!text.trim()}
        onClick={add}
        className="mt-2 rounded-lg border-2 border-[var(--accent)] bg-[var(--surface)] px-3.5 py-1.5 text-sm font-semibold text-[var(--accent)] hover:bg-[var(--soft)] disabled:opacity-40"
      >
        Add as document
      </button>
    </details>
  );
}
