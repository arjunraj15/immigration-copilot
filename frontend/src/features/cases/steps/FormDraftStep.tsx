import { useEffect, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";

import Icon from "../../../components/Icon";
import { Chip, GhostButton, type Tone } from "../../../components/Stamp";
import Citation from "../Citation";
import JsonView from "../JsonView";
import { useFormDraft } from "../../review/useProposals";
import { buildDraftJson, downloadJson, needsRequiredDocument, requiredDocumentLabel, type FormStatus } from "../formDraft";
import UploadWizard from "../../upload/UploadWizard";
import { formatUsDate, useCaseInfo } from "../useCases";
import StepFrame from "./StepFrame";
import { useStepKicker } from "./useSteps";

const STATUS_TONE: Record<FormStatus, Tone> = { PROPOSED: "ok", HELD_FOR_REVIEW: "bad", NOT_AVAILABLE: "muted" };

// accent is the soft accent style of the Upload button on the Documents step.
function IconButton({ label, text, onClick, accent, children }: { label: string; text: string; onClick: () => void; accent?: boolean; children: ReactNode }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      className={`flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold ${
        accent ? "bg-[var(--accent)]/10 text-[var(--accent)] transition hover:bg-[var(--accent)]/20" : "border border-[var(--line)] bg-[var(--surface)] text-[var(--ink)]"
      }`}
    >
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        {children}
      </svg>
      {text}
    </button>
  );
}

// A plain form for the open case. Every value carries its citations, a conflict holds the value empty and an unknown stays empty.
// Nothing here is typed in. Rows follow the output keys of the form template.
export default function FormDraftStep() {
  const kicker = useStepKicker("form");
  const { caseId = "" } = useParams();
  const draft = useFormDraft(caseId);
  const info = useCaseInfo(caseId);
  const [uploading, setUploading] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  useEffect(() => {
    if (!previewing) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setPreviewing(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [previewing]);
  const rows = draft.data?.fields ?? [];
  // The server sends the form id and the sections, so a new form field appears here without a code change.
  const formId = draft.data?.form_id ?? "";
  const byTarget = new Map(rows.map((row) => [row.target, row]));
  const filled = rows.filter((row) => row.status === "PROPOSED").length;
  const held = rows.filter((row) => row.status === "HELD_FOR_REVIEW").length;

  return (
    <StepFrame
      kicker={
        <>
          {kicker}
          <span
            title={`${formId}. Review-only worksheet, legal must approve before export.`}
            className="ml-3 rounded-md border border-dashed border-[var(--bad)] bg-[var(--bad-soft)] px-2 py-0.5 font-mono text-xs font-bold tracking-widest text-[var(--bad)]"
          >
            DRAFT - NOT FOR FILING
          </span>
        </>
      }
      actions={
        <>
          <IconButton label="Preview JSON" text="Preview" onClick={() => setPreviewing(true)}>
            <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
            <circle cx="12" cy="12" r="3" />
          </IconButton>
          <IconButton label="Download draft JSON" text="Download" onClick={() => downloadJson(`${caseId}-form-draft.json`, buildDraftJson(caseId, rows, formId))}>
            <path d="M12 3v12m0 0-4-4m4 4 4-4M4 20h16" />
          </IconButton>
          <IconButton label="Upload files" text="Upload" accent onClick={() => setUploading(true)}>
            <path d="M12 16V4m0 0-4 4m4-4 4 4M4 20h16" />
          </IconButton>
        </>
      }
      note={`${filled} of ${rows.length} fields have a value${held > 0 ? `, ${held} held for review. Settle them in the Exceptions tab` : ""}. Each shows where it came from. The rest wait for the documents to be read.`}
    >
      {previewing && (
        <>
          <div className="fixed inset-0 z-[9] bg-black/45" onClick={() => setPreviewing(false)} aria-hidden />
          <aside role="dialog" aria-label="Draft JSON preview" className="fixed inset-y-0 right-0 z-10 w-[min(640px,100%)] overflow-auto bg-[var(--soft)] p-4 shadow-2xl">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-lg font-bold">Draft JSON</h3>
                <small className="text-[var(--muted)]">{caseId}, marked as a draft</small>
              </div>
              <GhostButton onClick={() => setPreviewing(false)}>Close</GhostButton>
            </div>
            <JsonView value={buildDraftJson(caseId, rows, formId)} maxHeight="calc(100vh - 6rem)" />
          </aside>
        </>
      )}
      {uploading && info.data && (
        <UploadWizard
          onClose={() => setUploading(false)}
          forCase={{ case_id: info.data.case_id, initials: "", name: info.data.name, number: info.data.number, note: "", tone: "muted" }}
        />
      )}
      {draft.isPending && <p className="text-[var(--muted)]">Loading this case...</p>}
      {draft.isError && (
        <p className="text-[var(--bad)]" role="alert">
          Could not load this case: {draft.error.message}
        </p>
      )}

      {draft.data && (
        <div className="@container">
        <div className="grid items-start gap-x-4 @[80rem]:grid-cols-2">
          {draft.data.sections.map((section, index) => (
            <fieldset key={section.title} className={`mb-3 min-w-0 rounded-xl border border-[var(--line)] px-4 pb-1.5 ${index === 0 ? "@[80rem]:row-span-3" : ""}`}>
              <legend className="px-2 text-sm font-bold">{section.title}</legend>
              {section.fields.map((field) => {
                const row = byTarget.get(field.target);
                if (!row) return null;
                const isHeld = row.status === "HELD_FOR_REVIEW";
                const needsDoc = needsRequiredDocument(row);
                const docLabel = requiredDocumentLabel(row);
                // The ids this note lists are already shown as source chips.
                const agreed = row.review_notes.startsWith("All sources agree");
                const note = `${agreed ? "" : row.review_notes}${row.confidence !== null ? ` Confidence ${Math.round(row.confidence * 100)}%.` : ""}`;
                return (
                  <div key={field.target} className="border-t border-[var(--line)] py-2.5 first:border-t-0">
                    <div className="flex items-center gap-3">
                      <span className="w-44 shrink-0 whitespace-nowrap text-base font-bold">{field.label}{field.required !== false && <span className="ml-0.5 text-[var(--bad)]" title="Required" aria-label="required">*</span>}</span>
                      <div
                        className={`min-w-0 flex-1 truncate rounded-md border px-2.5 py-1.5 text-sm ${
                          isHeld ? "border-[var(--bad)] bg-[var(--bad-soft)] font-bold text-[var(--bad)]" : "border-[var(--line)] bg-[var(--soft)]"
                        } ${row.value ? "font-bold" : "text-[var(--muted)]"}`}
                      >
                        {row.value ? (
                          field.date ? formatUsDate(row.value) : row.value
                        ) : isHeld ? (
                          "Held, sources disagree"
                        ) : (
                          "Not available"
                        )}
                      </div>
                      <span className="flex shrink-0 items-center gap-1 whitespace-nowrap">
                        <Chip tone={STATUS_TONE[row.status]}>{row.status.replace(/_/g, " ")}</Chip>
                        {row.needs_legal_review && <Chip tone="warn">LEGAL REVIEW</Chip>}
                      </span>
                    </div>
                    <div className="mt-1.5 flex items-center gap-2 pl-[11.75rem] text-xs text-[var(--muted)]">
                      <span className="flex shrink-0 items-center whitespace-nowrap">
                        {row.evidence_refs.map((ref) => (
                          <Citation key={ref} source={ref} showTitle={false} />
                        ))}
                      </span>
                      {needsDoc ? (
                        <span className="inline-flex min-w-0 items-center gap-1 font-semibold text-[var(--bad)]" title={`${row.review_notes} See Exceptions.`}>
                          <Icon name="flag" className="h-3.5 w-3.5 shrink-0" />
                          <span className="truncate">{docLabel ?? "Document"} missing</span>
                        </span>
                      ) : (
                        <span className="min-w-0 truncate" title={note}>
                          {note}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </fieldset>
          ))}
        </div>
        </div>
      )}
    </StepFrame>
  );
}
