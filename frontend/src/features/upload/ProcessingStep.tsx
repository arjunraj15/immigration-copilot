import { useEffect } from "react";

import { Chip, PrimaryButton, type Tone } from "../../components/Stamp";
import { useCaseDocuments } from "../cases/useCaseDocuments";
import { outcomeLabel } from "../documents/readWithAi";
import { useJob, type DraftResult } from "./useIntake";

const WAITING = ["PENDING", "READING"];

function tone(outcome: string | undefined): Tone {
  if (!outcome || WAITING.includes(outcome)) return "muted";
  return outcome === "USABLE" ? "ok" : outcome === "CLAIM_SOURCE" ? "ai" : outcome === "NEEDS_HUMAN_REVIEW" ? "warn" : "bad";
}

function Line({ title, note, outcome }: { title: string; note: string; outcome?: string }) {
  return (
    <li className="flex items-center gap-3 border-b border-[var(--line)] py-2.5">
      <span className="min-w-0 flex-1">
        <b className="block truncate" title={title}>{title}</b>
        <small className="text-[var(--muted)]">{note}</small>
      </span>
      <Chip tone={tone(outcome)}>{outcome && !WAITING.includes(outcome) ? outcomeLabel(outcome).toUpperCase() : "READING"}</Chip>
    </li>
  );
}

// Live progress of the background job. It moves on by itself when the job succeeds and shows an error when it does not.
export default function ProcessingStep({ draft, onContinue }: { draft: DraftResult; onContinue: () => void }) {
  const job = useJob(draft.job_id);
  const docs = useCaseDocuments(draft.case_id, { pageSize: 100 });
  const uploaded = new Set(draft.results.map((result) => result.upload_id));
  const files = (docs.data?.items ?? []).filter((doc) => uploaded.has(doc.upload_id));
  const refused = draft.results.filter((result) => result.status === "refused");
  const status = job.data?.status;
  const ended = !draft.job_id || status === "SUCCEEDED" || status === "FAILED";
  useEffect(() => {
    if (status !== "SUCCEEDED") return;
    const timer = setTimeout(onContinue, 900);
    return () => clearTimeout(timer);
  }, [status, onContinue]);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <p className="font-semibold" role="status">
        {!draft.job_id ? "Automatic reading is off. Continue to choose the client name." : status === "SUCCEEDED" ? "AI finished reading." : status === "FAILED" ? "The AI could not finish reading." : `AI is reading ${job.data?.done ?? 0} of ${job.data?.total ?? files.length} items`}
      </p>
      {status === "FAILED" && (
        <p className="mt-2 rounded-xl bg-[var(--bad-soft)] px-3 py-2 text-sm text-[var(--bad)]" role="alert">
          {job.data?.reason ?? "Some items failed. Open them from the case later. You can still continue."}
        </p>
      )}
      {job.isError && (
        <p className="mt-2 text-sm text-[var(--bad)]" role="alert">
          Could not read the progress: {job.error.message}
        </p>
      )}
      <ul className="mt-2 min-h-0 flex-1 overflow-y-auto" aria-label="Reading progress">
        {files.map((doc) => (
          <Line key={doc.upload_id} title={doc.original_filename} note={WAITING.includes(doc.outcome) ? "AI is reading this file" : [doc.category_label, doc.outcome_reason].filter(Boolean).join(". ")} outcome={doc.outcome} />
        ))}
        {refused.map((result, index) => (
          <li key={`${result.original_filename}-${index}`} className="flex items-center gap-3 border-b border-[var(--line)] py-2.5">
            <span className="min-w-0 flex-1">
              <b className="block truncate">{result.original_filename}</b>
              <small className="text-[var(--muted)]">{result.reason}</small>
            </span>
            <Chip tone="bad">REFUSED</Chip>
          </li>
        ))}
      </ul>
      <div className="mt-3 text-right">
        <PrimaryButton disabled={!ended} onClick={onContinue}>
          Continue
        </PrimaryButton>
      </div>
    </div>
  );
}
