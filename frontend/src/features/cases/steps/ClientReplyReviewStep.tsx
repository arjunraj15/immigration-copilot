import { Link, useParams } from "react-router-dom";

import { Chip } from "../../../components/Stamp";
import { CitedIds, DRAFT_STATUS, DraftBanner, QuestionCard, TriagePills } from "../replyUi";
import { useReplyDraft } from "../useReplyDraft";
import StepFrame from "./StepFrame";
import { useStepKicker } from "./useSteps";

// Attorney view. Read only. The decision is made on the proposal page, and nothing is sent from this app.
export default function ClientReplyReviewStep() {
  const kicker = useStepKicker("reply");
  const { caseId = "" } = useParams();
  const reply = useReplyDraft(caseId);
  const data = reply.data;
  const draft = data?.draft ?? null;
  const status = draft ? DRAFT_STATUS[draft.status] : null;
  return (
    <StepFrame kicker={kicker} title="Client reply" note="Check the wording. Nothing is sent from this app.">
      {reply.isPending && <p className="text-[var(--muted)]">Loading the client reply...</p>}
      {reply.isError && (
        <p className="text-[var(--bad)]" role="alert">
          {reply.error.message}
        </p>
      )}
      {data && !data.question && <p className="rounded-xl bg-[var(--soft)] p-3.5">No client question is waiting</p>}
      {data?.question && <QuestionCard question={data.question} />}
      {data?.triage && <TriagePills triage={data.triage} reason={data.refusal_reason} />}
      {data?.question && !draft && <p className="rounded-xl bg-[var(--soft)] p-3.5">Operations has not drafted a reply yet.</p>}
      {draft && status && (
        <div className="rounded-xl border border-[var(--line)] p-3.5">
          <DraftBanner />
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Chip tone={status.tone}>{status.text}</Chip>
            <span className="font-mono text-xs text-[var(--muted)]">{draft.draft_id}</span>
            <Chip tone="muted">{draft.channel === "EMAIL" ? "Email" : "WhatsApp"}</Chip>
          </div>
          {draft.subject && <p className="mb-1 text-sm">Subject: {draft.subject}</p>}
          <p className="whitespace-pre-wrap rounded-xl bg-[var(--soft)] p-3">{draft.body}</p>
          <CitedIds ids={draft.source_ids} />
          {draft.proposal?.review_reason && <p className="mt-2 text-sm">Reason: {draft.proposal.review_reason}</p>}
          {draft.proposal ? (
            <p className="mt-2 text-sm">
              <Link to={`/review/${draft.proposal.proposal_id}`} className="font-semibold underline">
                Open the proposal to decide
              </Link>
            </p>
          ) : (
            <p className="mt-2 text-sm text-[var(--muted)]">Not sent for legal review yet.</p>
          )}
        </div>
      )}
    </StepFrame>
  );
}
