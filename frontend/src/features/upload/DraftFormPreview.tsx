import { useQuery } from "@tanstack/react-query";

import { Chip, type Tone } from "../../components/Stamp";
import Citation from "../cases/Citation";
import { fetchDraft, FORM_SECTIONS, type DraftStatus } from "./draftForm";

const STATUS_TONE: Record<DraftStatus, Tone> = { PROPOSED: "ok", HELD_FOR_REVIEW: "warn", NOT_AVAILABLE: "muted" };

// Review-only worksheet filled from the uploaded documents. Values, statuses and citations all come from the server.
export default function DraftFormPreview({ fileNames }: { fileNames: string[] }) {
  const draft = useQuery({ queryKey: ["draft-preview", fileNames], queryFn: () => fetchDraft(fileNames) });
  const rows = new Map((draft.data ?? []).map((row) => [row.target, row]));

  return (
    <section className="mt-4 rounded-2xl border border-[var(--line)]" aria-label="Draft form">
      <header className="flex flex-wrap items-center gap-3 border-b border-[var(--line)] px-4 py-3">
        <b className="text-lg">Draft form</b>
        <Chip tone="bad">DRAFT - NOT FOR FILING</Chip>
        <span className="text-sm text-[var(--muted)]">Review only. Legal approves before anything is exported.</span>
      </header>
      {draft.isPending && <p className="px-4 py-3 text-sm text-[var(--muted)]">Reading the documents...</p>}
      {draft.isError && (
        <p className="px-4 py-3 text-sm text-[var(--bad)]" role="alert">
          Could not build the draft: {draft.error.message}
        </p>
      )}
      {draft.data &&
        FORM_SECTIONS.map((section) => (
          <div key={section.title} className="px-4 py-2">
            <h3 className="mb-1 text-sm font-bold uppercase tracking-wide text-[var(--muted)]">{section.title}</h3>
            {section.fields.map((field) => {
              const row = rows.get(field.target);
              return (
                <div key={field.target} className="flex items-start gap-3 border-b border-[var(--line)] py-2 last:border-b-0">
                  <span className="w-40 shrink-0 font-semibold">{field.label}</span>
                  <span className="min-w-0 flex-1">
                    <span className={row?.value ? "" : "text-[var(--muted)]"}>{row?.value ?? "Not available"}</span>
                    {row && row.evidence_refs.length > 0 && (
                      <span className="ml-2">
                        {row.evidence_refs.map((ref) => (
                          <Citation key={ref} source={ref} showTitle={false} />
                        ))}
                      </span>
                    )}
                    {row?.review_notes && <small className="block text-[var(--muted)]">{row.review_notes}</small>}
                  </span>
                  <Chip tone={STATUS_TONE[row?.status ?? "NOT_AVAILABLE"]}>{(row?.status ?? "NOT_AVAILABLE").replace("_", " ")}</Chip>
                </div>
              );
            })}
          </div>
        ))}
    </section>
  );
}
