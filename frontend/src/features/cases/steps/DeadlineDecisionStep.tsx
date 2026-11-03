import { useState } from "react";
import { useParams } from "react-router-dom";

import { SourceRef } from "../../../components/Stamp";
import { formatLongDate } from "../../review/format";
import { Chip, GhostButton, PrimaryButton } from "../../../components/Stamp";
import CaseNotes from "../../review/CaseNotes";
import { STATUS_LABEL, useCaseProposals, useReview, useSendBack, type Proposal } from "../../review/useProposals";
import { useTimeline } from "../useCases";
import StepFrame from "./StepFrame";
import { useStepKicker } from "./useSteps";

// The proposed date, the portal request behind it and any calendar entry that disagrees. All of it comes from the timeline.
// The decision itself is made in the last step, where a pending proposal can be approved or rejected.
export default function DeadlineDecisionStep() {
  const kicker = useStepKicker("deadline");
  const { caseId = "" } = useParams();
  const timeline = useTimeline(caseId);
  const items = timeline.data?.items ?? [];
  const proposed = items.find((item) => item.kind === "proposed");
  const request = items.find((item) => item.kind === "verified" && item.ref === proposed?.ref);
  const wrong = items.find((item) => item.kind === "wrong");

  return (
    <StepFrame
      kicker={kicker}
      title={proposed ? `Is ${formatLongDate(proposed.date)} the right deadline?` : "Deadline"}
      note={
        proposed
          ? "A verified portal request plus the firm's rule gives the proposed date. A calendar entry that does not match is shown for comparison and is not evidence."
          : "No verified portal request exists for this case, so no deadline is proposed. Nothing is invented."
      }
    >
      {timeline.isError && (
        <p className="text-[var(--bad)]" role="alert">
          {timeline.error.message}
        </p>
      )}
      {proposed && (
        <div className="grid gap-2 sm:grid-cols-3">
          <div className="rounded-xl bg-[var(--soft)] p-2.5 text-sm text-[var(--muted)]">
            Request received (portal, verified)
            <b className="block text-xl text-[var(--ink)]">{request ? formatLongDate(request.date) : "Unknown"}</b>
            {proposed.ref && <SourceRef>{proposed.ref}</SourceRef>}
          </div>
          <div className="rounded-xl bg-[var(--soft)] p-2.5 text-sm text-[var(--muted)]">
            Proposed deadline
            <b className="block text-xl text-[var(--ink)]">{formatLongDate(proposed.date)}</b>
            {proposed.note}
          </div>
          <div className={`rounded-xl p-2.5 text-sm text-[var(--muted)] ${wrong ? "bg-[var(--bad-soft)]" : "bg-[var(--soft)]"}`}>
            Office calendar (typed by hand)
            {wrong ? (
              <>
                <b className="block text-xl text-[var(--bad)] line-through">{formatLongDate(wrong.date)}</b>
                {wrong.ref && <SourceRef>{wrong.ref}</SourceRef>}
              </>
            ) : (
              <b className="block text-xl text-[var(--ink)]">No conflicting entry</b>
            )}
          </div>
        </div>
      )}
      <DeadlineChoice caseId={caseId} />
    </StepFrame>
  );
}

// The attorney's three answers to a deadline proposal. Approve decides it. A different date and a question only save a note and send it back.
function DeadlineChoice({ caseId }: { caseId: string }) {
  const proposals = useCaseProposals(caseId);
  const pending = (proposals.data ?? []).find((item) => item.kind === "DEADLINE_ACTIVATE" && item.status === "PENDING_LEGAL_REVIEW");
  const latest = (proposals.data ?? []).find((item) => item.kind === "DEADLINE_ACTIVATE");
  return (
    <div className="mt-4">
      <CaseNotes caseId={caseId} />
      {pending ? (
        <ChoiceForm proposal={pending} />
      ) : latest ? (
        <p className="text-sm" role="status">
          <b className="font-mono">{latest.proposal_id}</b> <Chip tone={STATUS_LABEL[latest.status].tone}>{STATUS_LABEL[latest.status].text}</Chip>
        </p>
      ) : (
        <p className="text-sm text-[var(--muted)]">No deadline proposal has been sent for this case yet.</p>
      )}
    </div>
  );
}

function ChoiceForm({ proposal }: { proposal: Proposal }) {
  const review = useReview(proposal.proposal_id);
  const sendBack = useSendBack(proposal.proposal_id);
  const [mode, setMode] = useState<"DIFFERENT_DATE" | "QUESTION" | null>(null);
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const ready = note.trim() !== "" && (mode !== "DIFFERENT_DATE" || date !== "");
  const failure = review.error ?? sendBack.error;
  return (
    <div className="rounded-xl border border-[var(--line)] p-3.5">
      <b>Your answer on {proposal.proposal_id}</b>
      <div className="mt-2 flex flex-wrap gap-2">
        <PrimaryButton disabled={review.isPending} onClick={() => review.mutate({ decision: "APPROVE" })}>
          Approve this date
        </PrimaryButton>
        <GhostButton onClick={() => setMode("DIFFERENT_DATE")}>Use a different date</GhostButton>
        <GhostButton onClick={() => setMode("QUESTION")}>Ask a question</GhostButton>
      </div>
      {mode && (
        <div className="mt-3">
          {mode === "DIFFERENT_DATE" && (
            <label className="mb-2 block text-sm font-semibold">
              Date you would use
              <input type="date" className="mt-1 block rounded-xl border border-[var(--line)] bg-[var(--surface)] p-2" value={date} onChange={(e) => setDate(e.target.value)} />
            </label>
          )}
          <label className="block text-sm font-semibold" htmlFor="deadline-note">
            {mode === "QUESTION" ? "Your question" : "Why this date"}
          </label>
          <textarea id="deadline-note" className="mt-1 w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] p-2.5" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
          <p className="mt-1 text-sm text-[var(--muted)]">This saves a note and sends the proposal back to operations. It does not change the deadline.</p>
          <div className="mt-2 flex gap-2">
            <PrimaryButton
              disabled={!ready || sendBack.isPending}
              onClick={() => sendBack.mutate({ kind: mode, note: note.trim(), suggested_date: mode === "DIFFERENT_DATE" ? date : undefined })}
            >
              Send back with note
            </PrimaryButton>
            <GhostButton onClick={() => setMode(null)}>Cancel</GhostButton>
          </div>
        </div>
      )}
      {failure && (
        <p className="mt-2 text-[var(--bad)]" role="alert">
          {failure.message}
        </p>
      )}
    </div>
  );
}
