import { useEffect, useState } from "react";

import { GhostButton } from "../../components/Stamp";
import { saveBlob } from "../review/format";
import JsonView from "./JsonView";

const TEXT_CAP = 500_000;

// A blob URL that is revoked when the file changes or the viewer closes.
function useObjectUrl(blob: Blob, enabled: boolean): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled) return;
    const next = URL.createObjectURL(blob);
    setUrl(next);
    return () => {
      URL.revokeObjectURL(next);
      setUrl(null);
    };
  }, [blob, enabled]);
  return url;
}

function useCappedText(blob: Blob, enabled: boolean): string | null {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    blob.slice(0, TEXT_CAP).text().then((value) => live && setText(value));
    return () => {
      live = false;
      setText(null);
    };
  }, [blob, enabled]);
  return text;
}

type Kind = "pdf" | "image" | "json" | "jsonl" | "text" | "other";

function fileKind(type: string, name: string): Kind {
  const lower = name.toLowerCase();
  if (type === "application/pdf") return "pdf";
  if (type.startsWith("image/")) return "image";
  if (lower.endsWith(".jsonl") || type === "application/x-ndjson") return "jsonl";
  if (lower.endsWith(".json") || type === "application/json" || type === "text/json") return "json";
  return type === "text/plain" ? "text" : "other";
}

function parse(text: string): { ok: true; value: unknown } | { ok: false } {
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch {
    return { ok: false };
  }
}

function Plain({ text }: { text: string }) {
  return <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap break-words rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3 font-mono text-xs">{text}</pre>;
}

function JsonLines({ text }: { text: string }) {
  const lines = text.split("\n").filter((line) => line.trim() !== "");
  return (
    <div className="grid gap-2">
      {lines.map((line, index) => {
        const result = parse(line);
        return result.ok ? (
          <JsonView key={index} value={result.value} />
        ) : (
          <div key={index}>
            <small className="font-semibold text-[var(--bad)]">Line {index + 1} is not valid JSON</small>
            <Plain text={line} />
          </div>
        );
      })}
    </div>
  );
}

function TextBody({ blob, kind }: { blob: Blob; kind: "json" | "jsonl" | "text" }) {
  const text = useCappedText(blob, true);
  if (text === null) return <p className="text-[var(--muted)]">Loading...</p>;
  const parsed = kind === "json" ? parse(text) : null;
  return (
    <>
      {blob.size > TEXT_CAP && <p className="mb-2 text-sm text-[var(--muted)]">Showing the first 500 KB of {Math.round(blob.size / 1000)} KB.</p>}
      {kind === "jsonl" ? <JsonLines text={text} /> : parsed?.ok ? <JsonView value={parsed.value} /> : <Plain text={text} />}
    </>
  );
}

// Shows a stored file by its type. Unknown types get a download button instead.
export default function FileViewer({ blob, name }: { blob: Blob; name: string }) {
  const kind = fileKind(blob.type, name);
  const url = useObjectUrl(blob, kind === "pdf" || kind === "image");
  // The viewer's own toolbar and thumbnail panel are hidden so the page itself gets the room. Fit to width keeps the text readable.
  if (kind === "pdf") return url && <iframe title={name} src={`${url}#toolbar=0&navpanes=0&view=FitH`} className="h-[75vh] w-full rounded-xl border border-[var(--line)] bg-white" />;
  if (kind === "image") return url && <img src={url} alt={name} className="max-h-[75vh] max-w-full rounded-xl border border-[var(--line)] bg-white" />;
  if (kind === "other") {
    return (
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4">
        <b className="break-all">{name}</b>
        <p className="mb-3 text-sm text-[var(--muted)]">{Math.max(1, Math.round(blob.size / 1000))} KB. This file type cannot be shown here.</p>
        <GhostButton onClick={() => saveBlob(blob, name)}>Download</GhostButton>
      </div>
    );
  }
  return <TextBody blob={blob} kind={kind} />;
}
