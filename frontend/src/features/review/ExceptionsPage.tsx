import { useEffect, useState } from "react";

import ExceptionsTable, { TYPE_LABEL } from "./ExceptionsTable";
import { useExceptions } from "./useExceptions";

// Wait for a pause in typing before asking the server.
function useDebounced(value: string): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value.trim()), 250);
    return () => clearTimeout(timer);
  }, [value]);
  return settled;
}

const chip = (active: boolean) =>
  `rounded-full border px-3 py-1 text-sm font-semibold ${active ? "border-[var(--accent)] bg-[var(--accent)] text-white" : "border-[var(--line)] bg-[var(--surface)] hover:bg-[var(--soft)]"}`;

// Every defect, conflict and flagged file on the user's own cases, worked out by the server, most severe first.
export default function ExceptionsPage() {
  const [type, setType] = useState("");
  const [search, setSearch] = useState("");
  const list = useExceptions(type, useDebounced(search));
  const counts = list.data?.counts ?? {};
  const all = Object.values(counts).reduce((sum, n) => sum + n, 0);
  const kinds = Object.keys(counts).sort((a, b) => (TYPE_LABEL[a] ?? a).localeCompare(TYPE_LABEL[b] ?? b));

  return (
    <main className="p-4">
      <section className="rounded-2xl bg-[var(--surface)] p-5" aria-label="Exceptions">
        <h1 className="text-2xl font-bold">Exceptions</h1>
        <p className="mb-4 text-[var(--muted)]">Document problems, conflicts and flagged files on your cases. Open a case to fix one.</p>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <input
            className="w-72 rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2"
            placeholder="Case id or client name"
            aria-label="Search exceptions"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter by type">
          <button type="button" aria-pressed={type === ""} className={chip(type === "")} onClick={() => setType("")}>{`All (${all})`}</button>
          {kinds.map((kind) => (
            <button key={kind} type="button" aria-pressed={type === kind} className={chip(type === kind)} onClick={() => setType(type === kind ? "" : kind)}>
              {`${TYPE_LABEL[kind] ?? kind} (${counts[kind]})`}
            </button>
          ))}
          {type && !counts[type] && <button type="button" aria-pressed className={chip(true)} onClick={() => setType("")}>{`${TYPE_LABEL[type] ?? type} (0)`}</button>}
        </div>
        {list.isPending && <p className="py-6 text-center text-[var(--muted)]">Loading exceptions...</p>}
        {list.isError && <p className="py-6 text-center text-[var(--bad)]" role="alert">Could not load exceptions: {list.error.message}</p>}
        {list.data && list.data.items.length === 0 && <p className="py-6 text-center text-[var(--muted)]">{search || type ? "No exceptions match these filters." : "No exceptions on your cases."}</p>}
        {list.data && list.data.items.length > 0 && <ExceptionsTable items={list.data.items} />}
      </section>
    </main>
  );
}
