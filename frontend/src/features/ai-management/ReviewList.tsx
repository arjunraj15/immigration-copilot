import Icon from "../../components/Icon";
import { useDocViewer } from "../cases/docViewer";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useQueryClient } from "@tanstack/react-query";

import Pagination from "../home/Pagination";
import { pageSourceNote, useReadWithAi } from "../documents/readWithAi";
import { usDateTime } from "../../lib/dates";
import { useDocuments } from "../documents/useDocuments";
import { BUTTON, INPUT } from "./fieldStyles";
import { usePrompts, useResolveReview, useReview } from "./hooks";
import type { ReviewKind, ReviewRow } from "./types";

// US format, for example 10/07/2026, 2:30 PM. See lib/dates.ts.
const formatWhen = usDateTime;

function reasonOf(row: { reason: string | null; legible: boolean; injection_flag: boolean }): string {
  const notes = [row.reason, row.legible ? null : "Not legible", row.injection_flag ? "Instructions found in the text" : null];
  return notes.filter(Boolean).join(". ") || "No reason stored";
}

// A person picks the document type. The server records who set it and the row leaves the list.
function SetType({ uploadId }: { uploadId: string }) {
  const prompts = usePrompts();
  const resolve = useResolveReview();
  const [category, setCategory] = useState("");
  const types = (prompts.data?.read ?? []).filter((p) => p.enabled && !p.deleted && p.category && p.category !== "UNKNOWN");
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <select className="h-9 w-44 rounded border border-[var(--line)] bg-[var(--surface)] px-2 text-sm" aria-label="Document type" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">Choose type</option>
          {types.map((p) => (
            <option key={p.key} value={p.category ?? ""}>
              {p.title}
            </option>
          ))}
        </select>
        <button type="button" className={`${BUTTON} h-9 whitespace-nowrap`} disabled={!category || resolve.isPending} onClick={() => resolve.mutate({ uploadId, category })}>
          Set type
        </button>
      </div>
      {resolve.error && <p role="alert" className="text-sm text-[var(--bad)]">{resolve.error.message}</p>}
    </div>
  );
}

const PAGE_SIZE = 10;

// Wait for a pause in typing before asking the server.
function useDebounced(value: string): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value.trim()), 250);
    return () => clearTimeout(timer);
  }, [value]);
  return settled;
}

const KIND_LABEL = { missed: "Missed by AI", quarantined: "Quarantined" } as const;

function KindPill({ kind }: { kind: ReviewRow["kind"] }) {
  const tone = kind === "quarantined" ? "bg-[var(--bad-soft)] text-[var(--bad)]" : "bg-[var(--warn-soft)] text-[var(--warn)]";
  return <span className={`inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${tone}`}>{KIND_LABEL[kind]}</span>;
}

// Documents that need a person: the AI could not type them, or they were set aside. Paged on the server.
export default function ReviewList({ onAddType }: { onAddType: (uploadId: string) => void }) {
  const [kind, setKind] = useState<ReviewKind>("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const q = useDebounced(search);
  const { data, isLoading, error } = useReview({ kind, q, page, pageSize: PAGE_SIZE });
  const open = useDocViewer();
  const readAgain = useReadWithAi();
  // A new filter starts again at the first page.
  useEffect(() => setPage(1), [kind, q]);
  // While files are being read the documents query polls itself. Each change in the count reloads this list.
  const client = useQueryClient();
  const reading = useDocuments({ case: "", client: "", outcome: "READING", page: 1, pageSize: 1 }).data?.total;
  useEffect(() => {
    if (reading !== undefined) void client.invalidateQueries({ queryKey: ["ai", "review"] });
  }, [reading, client]);
  if (isLoading) return <p className="text-sm text-[var(--muted)]">Loading review list</p>;
  if (error || !data) return <p className="text-sm text-[var(--bad)]">Could not load the review list.</p>;
  const counts = { all: data.counts.missed + data.counts.quarantined, ...data.counts };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-0.5 rounded-xl bg-[var(--soft)] p-1" role="tablist" aria-label="Kind of document">
          {(["all", "missed", "quarantined"] as const).map((id) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={kind === id}
              onClick={() => setKind(id)}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1 text-sm ${kind === id ? "bg-[var(--surface)] font-semibold shadow-sm" : "text-[var(--muted)]"}`}
            >
              {id === "all" ? "All" : KIND_LABEL[id]}
              <span className="rounded-full bg-[var(--line)] px-1.5 text-xs font-bold text-[var(--muted)]">{counts[id]}</span>
            </button>
          ))}
        </div>
        <input className={`${INPUT} ml-auto max-w-xs`} type="search" aria-label="Search by file name or case" placeholder="Search file or case" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      {data.items.length === 0 ? (
        <p className="text-sm text-[var(--muted)]">
          <Icon name="check" className="mr-1.5 h-4 w-4 align-[-3px]" />
          {q || kind !== "all" ? "No documents match this filter." : "No documents are waiting for review."}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-[var(--line)]">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-[var(--soft)] text-left text-sm text-[var(--ink)]">
                {([["File", "documents"], ["Case", "user"], ["Status", "flag"], ["Type", "tag"], ["Reason", "exceptions"], ["Read", "clock"], ["Action", "arrow"]] as const).map(([title, icon]) => (
                  <th key={title} scope="col" className="whitespace-nowrap px-3 py-2 font-semibold">
                    <Icon name={icon} className="mr-1.5 inline h-3.5 w-3.5 align-[-2px]" />
                    {title}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => (
                <tr key={row.upload_id} className="border-t border-[var(--line)] align-top">
                  <td className="px-3 py-2.5">
                    <button type="button" onClick={() => open(row.upload_id)} className="break-all text-left font-bold hover:underline" aria-label={`View ${row.original_filename}`}>
                      {row.original_filename}
                    </button>
                    {row.page_count !== null && <small className="block text-[var(--muted)]">{row.page_count} pages</small>}
                  </td>
                  <td className="px-3 py-2.5 font-mono">
                    <Link to={`/cases/${row.case_id}`} className="hover:underline">{row.case_id}</Link>
                  </td>
                  <td className="px-3 py-2.5"><KindPill kind={row.kind} /></td>
                  <td className="px-3 py-2.5">{row.category_label ?? "Not typed"}</td>
                  <td className="px-3 py-2.5">
                    {reasonOf(row)}
                    {readAgain.data?.upload_id === row.upload_id && pageSourceNote(readAgain.data) && (
                      <small className="block text-[var(--muted)]">{pageSourceNote(readAgain.data)}</small>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5">{formatWhen(row.read_at)}</td>
                  <td className="px-3 py-2.5">
                    {row.kind === "missed" ? (
                      <div className="flex items-start gap-2">
                        <SetType uploadId={row.upload_id} />
                        <button type="button" className={`${BUTTON} inline-flex h-9 items-center gap-1.5 whitespace-nowrap`} disabled={readAgain.isPending} onClick={() => readAgain.mutate(row.upload_id)} aria-label={`Read ${row.original_filename} with AI`}>
                          <Icon name="ai" /> {readAgain.isPending && readAgain.variables === row.upload_id ? "Reading..." : "Read with AI"}
                        </button>
                        <button type="button" className={`${BUTTON} inline-flex h-9 items-center gap-1.5 whitespace-nowrap`} onClick={() => onAddType(row.upload_id)} aria-label={`Add ${row.original_filename} as a new document type`}>
                          <Icon name="plus" /> Add as new document type
                        </button>
                        {readAgain.isError && readAgain.variables === row.upload_id && (
                          <p role="alert" className="text-sm text-[var(--bad)]">
                            {readAgain.error.message}
                          </p>
                        )}
                      </div>
                    ) : (
                      <Link to={`/cases/${row.case_id}`} className={`${BUTTON} inline-flex h-9 items-center gap-1.5 whitespace-nowrap`}>
                        <Icon name="view" /> Open case
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} label="Review pages" showSingle />
        </div>
      )}
    </div>
  );
}
