import { useState } from "react";

import Icon from "../../components/Icon";
import { JsonView } from "./JsonHighlight";
import { INPUT } from "./fieldStyles";
import { useRunTest, useSamples, useTestRuns } from "./hooks";
import type { PromptHealth, TestField, TestItem, VersionCreate } from "./types";

type Props = { promptKey: string; draft: VersionCreate | null; health: PromptHealth | undefined; onClearDraft: () => void };

function normalize(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLowerCase();
}

// Quote check runs in the browser against the source text shown on screen.
function quoteStatus(quote: string | null | undefined, source: string): "found" | "missing" | "none" {
  if (!quote) return "none";
  return normalize(source).includes(normalize(quote)) ? "found" : "missing";
}

const PILL: Record<string, { text: string; style: string }> = {
  found: { text: "Quote found in source", style: "bg-[var(--ok-soft)] text-[var(--ok)]" },
  missing: { text: "Quote not in source", style: "bg-[var(--bad-soft)] text-[var(--bad)]" },
  none: { text: "No quote given", style: "bg-[var(--warn-soft)] text-[var(--warn)]" },
};

export default function TestPanel({ promptKey, draft, health, onClearDraft }: Props) {
  const [text, setText] = useState("");
  const [uploadId, setUploadId] = useState("");
  const [useOverride, setUseOverride] = useState(false);
  const samples = useSamples();
  const run = useRunTest();
  const result = run.data;
  const canRun = text.trim() !== "" || uploadId !== "";
  const overrideOn = useOverride && draft !== null;

  function submit() {
    run.mutate({
      text: text.trim() || null,
      upload_id: !text.trim() && uploadId ? Number(uploadId) : null,
      prompt_key: promptKey,
      override: overrideOn ? draft : null,
    });
  }

  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 text-base font-semibold">
        <Icon name="flask" className="h-[22px] w-[22px]" /> Live test
        <span className="rounded-full bg-[var(--ai-soft)] px-2 py-px text-xs font-semibold text-[var(--ai)]">{overrideOn ? "draft, unsaved" : "active version"}</span>
      </h2>
      <div className="grid grid-cols-3 gap-1.5">
        {[
          [health?.median_latency_ms == null ? "-" : `${(health.median_latency_ms / 1000).toFixed(1)}s`, "median latency"],
          [health?.ok_pct == null ? "-" : `${health.ok_pct}%`, "runs ok"],
          [String(health?.runs ?? 0), "runs, 7 days"],
        ].map(([value, label]) => (
          <div key={label} className="rounded-[10px] bg-[var(--soft)] px-2.5 py-1.5">
            <b className="block text-[17px]">{value}</b>
            <span className="text-xs text-[var(--muted)]">{label}</span>
          </div>
        ))}
      </div>
      <label className="block space-y-1 text-sm">
        <span className="text-xs font-semibold text-[var(--muted)]">Sample input</span>
        <select className={INPUT} value={uploadId} onChange={(e) => setUploadId(e.target.value)} disabled={!samples.data}>
          <option value="">{samples.data ? "None, paste text below" : "No samples available"}</option>
          {(samples.data ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {item.filename}
            </option>
          ))}
        </select>
      </label>
      <textarea className={`${INPUT} h-24 font-mono`} value={text} onChange={(e) => setText(e.target.value)} placeholder="Or paste document text here" aria-label="Source text" />
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="w-auto" checked={useOverride} disabled={!draft} onChange={(e) => setUseOverride(e.target.checked)} />
        Run the draft, not the active version
        {draft && (
          <button type="button" className="ml-auto text-xs underline" onClick={onClearDraft}>
            Discard draft
          </button>
        )}
      </label>
      {!draft && <p className="text-xs text-[var(--muted)]">Choose "Use as test draft" in the editor first. A test changes no saved state.</p>}
      <button type="button" className="flex w-full items-center justify-center gap-1.5 rounded-[10px] bg-[var(--ai)] px-3.5 py-[7px] font-semibold text-white hover:brightness-110 disabled:opacity-50" disabled={!canRun || run.isPending} onClick={submit}>
        <Icon name="play" /> {run.isPending ? "Running test" : "Run test"}
      </button>

      {run.error && <p role="alert" className="text-sm text-[var(--bad)]">Test failed. {String(run.error)}</p>}
      {!result && !run.error && <p className="rounded-[10px] bg-[#0f1830] p-2.5 font-mono text-xs leading-normal text-[#d8e2ff]">Press Run test. The result shows here, next to the editor.</p>}

      {result && (
        <div className="space-y-2">
          <dl className="flex flex-wrap gap-x-4 gap-y-1 rounded-[10px] bg-[var(--soft)] px-3 py-2 text-sm">
            <div><dt className="inline text-[var(--muted)]">Category </dt><dd className="inline font-mono">{result.category ?? "unknown"}</dd></div>
            <div><dt className="inline text-[var(--muted)]">Language </dt><dd className="inline font-mono">{result.language ?? "unknown"}</dd></div>
            <div><dt className="inline text-[var(--muted)]">Legible </dt><dd className="inline">{result.legible === null ? "unknown" : result.legible ? "Yes" : "No"}</dd></div>
            <div><dt className="inline text-[var(--muted)]">Injection flag </dt><dd className="inline">{result.injection_flag === null ? "unknown" : result.injection_flag ? "Raised" : "None"}</dd></div>
            <RunStats ids={result.prompt_run_ids} />
          </dl>
          <p className="text-sm font-medium">Extracted fields</p>
          <ul className="space-y-1.5">
            {result.fields.map((field, index) => {
              const checkable = text.trim() !== "";
              if (field.items) return <ArrayField key={index} field={field} source={text} checkable={checkable} />;
              const pill = PILL[checkable ? quoteStatus(field.quote, text) : "none"];
              return (
                <li key={index} className="rounded border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm">
                  <p className="font-mono">{String(field.key ?? "field")}: {JSON.stringify(field.value)}</p>
                  {field.quote && <p className="text-xs text-[var(--muted)]">"{field.quote}"{field.page != null ? `, page ${field.page}` : ""}</p>}
                  <span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-xs ${pill.style}`}>
                    {checkable ? pill.text : "Paste text to check quotes"}
                  </span>
                </li>
              );
            })}
          </ul>
          <details>
            <summary className="cursor-pointer text-sm font-medium">Raw JSON</summary>
            <JsonView className="mt-1 max-h-64 rounded bg-[var(--soft)] p-2" text={JSON.stringify(result, null, 2)} />
          </details>
          <details>
            <summary className="cursor-pointer text-sm font-medium">Source text</summary>
            <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap rounded border border-[var(--line)] bg-[var(--surface)] p-2 text-xs">
              {text || "Sample upload text is read on the server."}
            </pre>
          </details>
        </div>
      )}
    </section>
  );
}

function RunStats({ ids }: { ids: number[] }) {
  const { data } = useTestRuns(ids);
  const runs = data ?? [];
  const tokensIn = runs.reduce((sum, run) => sum + (run.tokens_in ?? 0), 0);
  const tokensOut = runs.reduce((sum, run) => sum + (run.tokens_out ?? 0), 0);
  const latency = runs.reduce((sum, run) => sum + (run.latency_ms ?? 0), 0);
  return (
    <>
      <div><dt className="inline text-[var(--muted)]">Tokens </dt><dd className="inline font-mono">{runs.length ? `${tokensIn} in, ${tokensOut} out` : "pending"}</dd></div>
      <div><dt className="inline text-[var(--muted)]">Latency </dt><dd className="inline font-mono">{runs.length ? `${latency} ms` : "pending"}</dd></div>
    </>
  );
}

// Server check: verified is true when the item quote was found on its page. Browser check needs pasted text.
function ItemRow({ item, source, checkable }: { item: TestItem; source: string; checkable: boolean }) {
  const server = item.verified ? PILL.found : PILL.missing;
  const browser = PILL[checkable ? quoteStatus(item.quote, source) : "none"];
  return (
    <li className="rounded border border-[var(--line)] px-2 py-1.5">
      <p className="font-mono text-xs">{Object.entries(item.values).map(([name, value]) => `${name}: ${value ?? "null"}`).join(", ")}</p>
      <p className="text-xs text-[var(--muted)]">"{item.quote}", page {item.page}</p>
      <span className={`mt-1 mr-1 inline-block rounded-full px-2 py-0.5 text-xs ${server.style}`}>
        {item.verified ? "Verified on page" : "Not verified, kept for review"}
      </span>
      <span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-xs ${browser.style}`}>
        {checkable ? browser.text : "Paste text to check in browser"}
      </span>
    </li>
  );
}

function ArrayField({ field, source, checkable }: { field: TestField; source: string; checkable: boolean }) {
  const items = field.items ?? [];
  return (
    <li className="rounded border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm">
      <p className="font-mono">{String(field.key ?? "field")}: {items.length} {items.length === 1 ? "row" : "rows"}</p>
      {items.length === 0 && <p className="text-xs text-[var(--muted)]">No rows returned.</p>}
      <ul className="mt-1 space-y-1">
        {items.map((item, index) => (
          <ItemRow key={index} item={item} source={source} checkable={checkable} />
        ))}
      </ul>
    </li>
  );
}
