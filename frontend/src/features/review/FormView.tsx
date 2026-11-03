import { Chip, type Tone } from "../../components/Stamp";
import Icon from "../../components/Icon";
import Citation from "../cases/Citation";
import { needsRequiredDocument, requiredDocumentLabel, type FormStatus } from "../cases/formDraft";
import { formatLongDate } from "./format";
import type { FormValue } from "./useProposals";

const STATUS_TONE: Record<FormStatus, Tone> = { PROPOSED: "ok", HELD_FOR_REVIEW: "bad", NOT_AVAILABLE: "muted" };

export function countRows(value: FormValue): { filled: number; held: number; missing: number } {
  const count = (status: FormStatus) => value.fields.filter((row) => row.status === status).length;
  return { filled: count("PROPOSED"), held: count("HELD_FOR_REVIEW"), missing: count("NOT_AVAILABLE") };
}

// The form as the server built it. Nothing here is typed in or worked out, rows come from the proposal value.
export default function FormView({ value }: { value: FormValue }) {
  const byTarget = new Map(value.fields.map((row) => [row.target, row]));
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span
          title="Review-only worksheet. Values come from case evidence."
          className="whitespace-nowrap rounded-md border border-dashed border-[var(--bad)] bg-[var(--bad-soft)] px-2 py-0.5 font-mono font-bold tracking-widest text-[var(--bad)]"
        >
          DRAFT - NOT FOR FILING
        </span>
        <span className="text-[var(--muted)]">{value.form_id}</span>
      </div>
      {value.sections.map((section) => (
        <fieldset key={section.title} className="mb-3 rounded-2xl border border-[var(--line)] px-4 pb-1">
          <legend className="px-2 font-bold">{section.title}</legend>
          {section.fields.map((field) => {
            const row = byTarget.get(field.target);
            if (!row) return null;
            const held = row.status === "HELD_FOR_REVIEW";
            const needsDoc = needsRequiredDocument(row);
            const docLabel = requiredDocumentLabel(row);
            return (
              <div key={field.target} className="flex items-start gap-3 border-t border-[var(--line)] py-3 first:border-t-0">
                <span className="w-40 shrink-0 pt-2 text-sm font-semibold">{field.label}{field.required !== false && <span className="ml-0.5 text-[var(--bad)]" title="Required" aria-label="required">*</span>}</span>
                <div className="min-w-0 flex-1">
                  <div
                    className={`rounded-xl border px-3 py-2 ${
                      held ? "border-[var(--bad)] bg-[var(--bad-soft)] font-bold text-[var(--bad)]" : "border-[var(--line)] bg-[var(--soft)]"
                    } ${row.value ? "font-bold" : "text-[var(--muted)]"}`}
                  >
                    {row.value ? (
                      field.date ? formatLongDate(row.value) : row.value
                    ) : held ? (
                      "Held, sources disagree"
                    ) : (
                      "Not available"
                    )}
                  </div>
                  {row.evidence_refs.length > 0 && (
                    <div className="mt-1.5 text-sm">
                      <span className="mr-2 text-[var(--muted)]">{held ? "Sources that disagree" : "Source"}</span>
                      {row.evidence_refs.map((ref) => (
                        <Citation key={ref} source={ref} />
                      ))}
                    </div>
                  )}
                  <small className={`mt-1 block ${needsDoc ? "font-semibold text-[var(--bad)]" : "text-[var(--muted)]"}`} title={needsDoc ? `${row.review_notes} See Exceptions.` : row.review_notes}>
                    {needsDoc && <Icon name="flag" className="mr-1 inline h-3.5 w-3.5 align-text-bottom" />}
                    {needsDoc ? `${docLabel ?? "Document"} missing` : row.review_notes}
                    {row.confidence !== null && ` Confidence ${Math.round(row.confidence * 100)}%.`}
                  </small>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <Chip tone={STATUS_TONE[row.status]}>{row.status.replace(/_/g, " ")}</Chip>
                  {row.needs_legal_review && <Chip tone="warn">NEEDS LEGAL REVIEW</Chip>}
                </div>
              </div>
            );
          })}
        </fieldset>
      ))}
    </div>
  );
}
