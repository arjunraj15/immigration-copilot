import { useState } from "react";

import Icon from "../../components/Icon";
import { usDateTime } from "../../lib/dates";
import { usePromptRuns, useRunTrace } from "./hooks";
import { JsonView } from "./JsonHighlight";
import type { RunOut } from "./types";

const OK = "bg-[var(--ok-soft)] text-[var(--ok)]";
const BAD = "bg-[var(--bad-soft)] text-[var(--bad)]";

// The trace is stored compressed and only fetched, expanded, when the row is opened.
function Trace({ id }: { id: number }) {
  const { data, isLoading, error } = useRunTrace(id, true);
  if (isLoading) return <p className="text-sm text-[var(--muted)]">Loading trace</p>;
  if (error || !data) return <p className="text-sm text-[var(--bad)]">Could not load the trace.</p>;
  if (data.hidden) return <p className="text-sm text-[var(--muted)]">This run belongs to another person's case, so its trace is not shown.</p>;
  if (!data.saved) return <p className="text-sm text-[var(--muted)]">No trace was saved for this run.</p>;
  const { run_id: _id, hidden: _hidden, saved: _saved, ...body } = data;
  return <JsonView className="max-h-96 rounded bg-[var(--soft)] p-2" text={JSON.stringify(body, null, 2)} />;
}

function Row({ run }: { run: RunOut }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr className="cursor-pointer border-t border-[var(--line)] hover:bg-[var(--soft)]" onClick={() => setOpen(!open)}>
        <td className="py-1.5">
          <button type="button" aria-expanded={open} aria-label={`Trace of run ${run.id}`} className="inline-flex items-center gap-1.5 text-left">
            <Icon name="arrow" className={`h-3 w-3 transition-transform ${open ? "rotate-90" : ""}`} />
            {usDateTime(run.created_at)}
          </button>
        </td>
        <td className="font-mono text-xs">v{run.version}</td>
        <td>
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${run.status === "ok" ? OK : BAD}`}>
            {run.status === "ok" || !run.stop_reason ? run.status : run.stop_reason}
          </span>
        </td>
        <td>{run.tokens_out ?? "-"}</td>
        <td>{run.latency_ms == null ? "-" : `${(run.latency_ms / 1000).toFixed(1)}s`}</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={5} className="pb-2">
            <Trace id={run.id} />
          </td>
        </tr>
      )}
    </>
  );
}

export default function RecentRuns({ promptKey }: { promptKey: string }) {
  const { data, isLoading, error } = usePromptRuns(promptKey);
  if (isLoading) return <p className="text-sm text-[var(--muted)]">Loading runs</p>;
  if (error || !data) return <p className="text-sm text-[var(--bad)]">Could not load runs.</p>;
  if (data.length === 0) return <p className="py-4 text-center text-sm text-[var(--muted)]">No runs yet.</p>;
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-xs text-[var(--muted)]">
        <tr><th className="py-1">When</th><th>Version</th><th>Status</th><th>Tokens out</th><th>Latency</th></tr>
      </thead>
      <tbody>
        {data.map((run) => (
          <Row key={run.id} run={run} />
        ))}
      </tbody>
    </table>
  );
}
