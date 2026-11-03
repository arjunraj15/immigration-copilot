import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiFile } from "../../api/client";
import Icon from "../../components/Icon";
import { Chip, type Tone } from "../../components/Stamp";
import { usDateTime } from "../../lib/dates";
import { LinkedText } from "../cases/Citation";
import { useDocViewer } from "../cases/docViewer";
import { saveBlob } from "../review/format";
import { outcomeLabel, pageSourceNote, useReadWithAi } from "./readWithAi";
import { useDeleteDocument, useDocuments, type DocumentFilters } from "./useDocuments";

const OUTCOMES = ["PENDING", "READING", "USABLE", "CLAIM_SOURCE", "DUPLICATE", "QUARANTINED", "SUPERSEDED", "INVALID", "NEEDS_HUMAN_REVIEW"];
const ACTION = "inline-flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-xs font-semibold hover:bg-[var(--soft)]";
const PAGE_SIZES = [10, 25, 50, 100];
const OUTCOME_TONE: Record<string, Tone> = {
  USABLE: "ok",
  PENDING: "muted",
  READING: "ai",
  CLAIM_SOURCE: "ai",
  DUPLICATE: "warn",
  SUPERSEDED: "warn",
  NEEDS_HUMAN_REVIEW: "warn",
  QUARANTINED: "bad",
  INVALID: "bad",
};

function formatSize(bytes: number): string {
  return bytes >= 1_000_000 ? `${(bytes / 1_000_000).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1000))} KB`;
}

// US format, for example 10/07/2026, 2:30 PM. See lib/dates.ts.
const formatWhen = usDateTime;

// Wait for a pause in typing before asking the server.
function useDebounced(value: string): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value.trim()), 250);
    return () => clearTimeout(timer);
  }, [value]);
  return settled;
}

// Pages to show around the current one, with gaps shown as null.
function pageNumbers(current: number, last: number): (number | null)[] {
  const wanted = new Set([1, last, current - 1, current, current + 1].filter((n) => n >= 1 && n <= last));
  const sorted = [...wanted].sort((a, b) => a - b);
  return sorted.flatMap((n, i) => (i > 0 && n - sorted[i - 1] > 1 ? [null, n] : [n]));
}

// Every document uploaded to the user's own cases, one page at a time, filtered by client, case and outcome.
export default function DocumentsPage() {
  const [client, setClient] = useState("");
  const [caseId, setCaseId] = useState("");
  const [outcome, setOutcome] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const filters: DocumentFilters = { client: useDebounced(client), case: useDebounced(caseId), outcome, page, pageSize };
  const docs = useDocuments(filters);
  const open = useDocViewer();
  const readAgain = useReadWithAi();
  const [saveError, setSaveError] = useState<string | null>(null);
  const remove = useDeleteDocument();
  // The row being deleted and the reason typed so far. The audit trail keeps the reason.
  const [deleting, setDeleting] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const confirmDelete = (caseId: string, uploadId: string) =>
    remove.mutate({ caseId, uploadId, reason: reason.trim() }, { onSuccess: () => { setDeleting(null); setReason(""); } });
  // The file route checks case access, so a refused download shows its message here.
  const download = (uploadId: string) => {
    setSaveError(null);
    apiFile(`/uploads/${encodeURIComponent(uploadId)}/file`)
      .then(({ blob, fileName }) => saveBlob(blob, fileName ?? uploadId))
      .catch((error: Error) => setSaveError(error.message));
  };

  // A new filter or page size starts again at the first page.
  useEffect(() => setPage(1), [filters.client, filters.case, outcome, pageSize]);

  const total = docs.data?.total ?? 0;
  const last = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  const field = "rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2";

  return (
    <main className="p-4">
      <section className="rounded-2xl bg-[var(--surface)] p-5" aria-label="Documents">
        <h1 className="text-2xl font-bold">Documents</h1>
        <p className="mb-4 text-[var(--muted)]">Every file uploaded to your cases. Filter by client or case.</p>

        <div className="mb-4 flex flex-wrap items-center gap-3">
          <input className={`${field} w-64`} placeholder="Client name" aria-label="Filter by client" value={client} onChange={(e) => setClient(e.target.value)} />
          <input className={`${field} w-48`} placeholder="Case, for example CASE-0005" aria-label="Filter by case" value={caseId} onChange={(e) => setCaseId(e.target.value)} />
          <select className={field} aria-label="Filter by outcome" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="">All outcomes</option>
            {OUTCOMES.map((item) => (
              <option key={item} value={item}>
                {outcomeLabel(item)}
              </option>
            ))}
          </select>
          {(client || caseId || outcome) && (
            <button
              type="button"
              className="rounded-xl border border-[var(--line)] px-3 py-2 font-semibold hover:bg-[var(--soft)]"
              onClick={() => {
                setClient("");
                setCaseId("");
                setOutcome("");
              }}
            >
              Clear filters
            </button>
          )}
        </div>

        {docs.isError && (
          <p className="mb-3 text-[var(--bad)]" role="alert">
            Could not load documents: {docs.error.message}
          </p>
        )}

        {saveError && (
          <p className="mb-3 text-[var(--bad)]" role="alert">
            {saveError}
          </p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-[var(--soft)] text-left text-sm text-[var(--ink)]">
                {([["Document", "documents"], ["Case and client", "user"], ["Type", "tag"], ["Outcome", "check"], ["Size", "size"], ["Uploaded", "clock"], ["Actions", "arrow"]] as const).map(([title, icon]) => (
                  <th key={title} scope="col" className="px-3.5 py-2.5 font-semibold">
                    <Icon name={icon} className="mr-1.5 inline h-3.5 w-3.5 align-[-2px]" />
                    {title}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {docs.isPending && (
                <tr>
                  <td colSpan={7} className="px-3.5 py-6 text-center text-[var(--muted)]">
                    Loading documents...
                  </td>
                </tr>
              )}
              {docs.data?.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-3.5 py-6 text-center text-[var(--muted)]">
                    No documents match these filters.
                  </td>
                </tr>
              )}
              {docs.data?.items.map((row) => (
                <tr key={row.upload_id} className="border-t border-[var(--line)] align-top hover:bg-[var(--soft)]">
                  <td className="px-3.5 py-3">
                    <button type="button" onClick={() => open(row.upload_id)} className="block break-all text-left font-bold hover:underline" aria-label={`View ${row.original_filename}`}>
                      {row.original_filename}
                    </button>
                    <small className="font-mono text-[var(--muted)]">{row.upload_id}</small>
                  </td>
                  <td className="px-3.5 py-3">
                    <Link to={`/cases/${row.case_id}`} className="font-semibold hover:underline">
                      {row.client_name}
                    </Link>
                    <small className="block font-mono text-[var(--muted)]">{row.case_id}</small>
                  </td>
                  <td className="px-3.5 py-3">{row.category_label ? <Chip tone="ai">{row.category_label}</Chip> : <span className="text-[var(--muted)]">Not read yet</span>}</td>
                  <td className="px-3.5 py-3">
                    <Chip tone={OUTCOME_TONE[row.outcome] ?? "muted"}>{outcomeLabel(row.outcome)}</Chip>
                    {row.outcome_reason && <small className="mt-1 block text-[var(--muted)]"><LinkedText text={row.outcome_reason} /></small>}
                    {readAgain.data?.upload_id === row.upload_id && pageSourceNote(readAgain.data) && (
                      <small className="mt-1 block text-[var(--muted)]">{pageSourceNote(readAgain.data)}</small>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3.5 py-3">{formatSize(row.file_size_bytes)}</td>
                  <td className="whitespace-nowrap px-3.5 py-3">
                    {formatWhen(row.uploaded_at)}
                    <small className="block text-[var(--muted)]">by {row.uploader_role.toLowerCase()}</small>
                  </td>
                  <td className="whitespace-nowrap px-3.5 py-3">
                    <button type="button" onClick={() => open(row.upload_id)} className={ACTION} aria-label={`View ${row.original_filename}`}>
                      <Icon name="view" /> View
                    </button>
                    <button type="button" onClick={() => download(row.upload_id)} className={`${ACTION} ml-1.5`} aria-label={`Download ${row.original_filename}`}>
                      <Icon name="download" /> Download
                    </button>
                    {(row.outcome === "NEEDS_HUMAN_REVIEW" || (row.outcome === "PENDING" && row.outcome_reason)) && (
                      <>
                        <button
                          type="button"
                          onClick={() => readAgain.mutate(row.upload_id)}
                          disabled={readAgain.isPending}
                          className={`${ACTION} ml-1.5 disabled:opacity-50`}
                          aria-label={`Read ${row.original_filename} with AI`}
                        >
                          <Icon name="ai" /> {readAgain.isPending && readAgain.variables === row.upload_id ? "Reading..." : "Read with AI"}
                        </button>
                        {readAgain.isError && readAgain.variables === row.upload_id && (
                          <small className="mt-1 block text-[var(--bad)]" role="alert">
                            {readAgain.error.message}
                          </small>
                        )}
                      </>
                    )}
                    <button
                      type="button"
                      onClick={() => { setDeleting(row.upload_id); setReason(""); remove.reset(); }}
                      className={`${ACTION} ml-1.5 border-[var(--bad)] text-[var(--bad)]`}
                      aria-label={`Delete ${row.original_filename}`}
                    >
                      <Icon name="trash" /> Delete
                    </button>
                    {deleting === row.upload_id && (
                      <form
                        className="mt-2 flex flex-wrap items-center gap-2 whitespace-normal"
                        onSubmit={(e) => { e.preventDefault(); confirmDelete(row.case_id, row.upload_id); }}
                      >
                        <input
                          autoFocus
                          className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-xs"
                          placeholder="Why delete? The audit trail keeps this"
                          aria-label={`Reason for deleting ${row.original_filename}`}
                          maxLength={500}
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                        />
                        <button type="submit" disabled={reason.trim().length < 3 || remove.isPending} className={`${ACTION} border-[var(--bad)] text-[var(--bad)] disabled:opacity-50`}>
                          {remove.isPending ? "Deleting..." : "Confirm delete"}
                        </button>
                        <button type="button" onClick={() => setDeleting(null)} className={ACTION}>
                          Cancel
                        </button>
                        {remove.isError && (
                          <small className="w-full text-[var(--bad)]" role="alert">
                            {remove.error.message}
                          </small>
                        )}
                      </form>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <nav className="mt-4 flex flex-wrap items-center gap-3" aria-label="Pages">
          <span className="text-sm text-[var(--muted)]">
            {from} to {to} of {total}
          </span>
          <label className="ml-auto flex items-center gap-2 text-sm text-[var(--muted)]">
            Rows
            <select className={field} value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}>
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
          <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded-xl border border-[var(--line)] px-3 py-2 font-semibold disabled:opacity-40">
            Previous
          </button>
          {pageNumbers(page, last).map((n, i) =>
            n === null ? (
              <span key={`gap-${i}`} aria-hidden className="text-[var(--muted)]">
                ...
              </span>
            ) : (
              <button
                key={n}
                type="button"
                aria-current={n === page ? "page" : undefined}
                onClick={() => setPage(n)}
                className={`rounded-xl border px-3 py-2 font-semibold ${n === page ? "border-[var(--accent)] bg-[var(--accent)] text-white" : "border-[var(--line)] hover:bg-[var(--soft)]"}`}
              >
                {n}
              </button>
            ),
          )}
          <button type="button" disabled={page >= last} onClick={() => setPage(page + 1)} className="rounded-xl border border-[var(--line)] px-3 py-2 font-semibold disabled:opacity-40">
            Next
          </button>
        </nav>
      </section>
    </main>
  );
}
