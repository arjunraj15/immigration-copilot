import { useState } from "react";
import { useParams } from "react-router-dom";

import { Chip, GhostButton, PrimaryButton } from "../../../components/Stamp";
import { CitedIds, DRAFT_STATUS, DraftBanner, QuestionCard, TriagePills } from "../replyUi";
import {
  useCreateMissing,
  useEditDraft,
  useMissingFields,
  useRegenerateReply,
  useReplyDraft,
  useSubmitDraft,
  type ReplyDraft,
} from "../useReplyDraft";
import StepFrame from "./StepFrame";
import { useStepKicker } from "./useSteps";

function Failure({ error }: { error: Error | null }) {
  if (!error) return null;
  return (
    <p className="mt-2 text-[var(--bad)]" role="alert">
      {error.message}
    </p>
  );
}

type BoxProps = { caseId: string; draft: ReplyDraft; onRegenerate: () => void; regenerating: boolean };

// The text box and buttons for one draft. The server builds the draft, this only edits the words and asks for review.
function DraftBox({ caseId, draft, onRegenerate, regenerating }: BoxProps) {
  const [text, setText] = useState(draft.body);
  const edit = useEditDraft(caseId);
  const submit = useSubmitDraft(caseId);
  const status = DRAFT_STATUS[draft.status];
  const open = draft.status === "DRAFT";
  const changed = text !== draft.body;
  return (
    <div className="rounded-xl border border-[var(--line)] p-3.5">
      <DraftBanner />
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Chip tone={status.tone}>{status.text}</Chip>
        <span className="font-mono text-xs text-[var(--muted)]">{draft.draft_id}</span>
        <Chip tone="muted">{draft.channel === "EMAIL" ? "Email" : "WhatsApp"}</Chip>
      </div>
      {draft.subject && <p className="mb-1 text-sm">Subject: {draft.subject}</p>}
      <label className="sr-only" htmlFor={`draft-${draft.draft_id}`}>
        Draft text
      </label>
      <textarea
        id={`draft-${draft.draft_id}`}
        className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] p-2.5"
        rows={14}
        value={text}
        readOnly={!open}
        onChange={(event) => setText(event.target.value)}
      />
      <CitedIds ids={draft.source_ids} />
      {draft.status === "REJECTED" && (
        <p className="mt-2 text-sm">
          Rejected{draft.proposal?.reviewed_by ? ` by ${draft.proposal.reviewed_by}` : ""}.
          {draft.proposal?.review_reason ? ` Reason: ${draft.proposal.review_reason}.` : ""} Regenerate to start a new draft, then change the text before sending it again.
        </p>
      )}
      {draft.status === "PENDING_LEGAL_REVIEW" && <p className="mt-2 text-sm text-[var(--muted)]">Waiting for the legal reviewer. The text is locked.</p>}
      {draft.status === "APPROVED" && <p className="mt-2 text-sm text-[var(--muted)]">Approved by the legal reviewer. It is still a draft and nothing was sent.</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <GhostButton onClick={() => edit.mutate({ draftId: draft.draft_id, body: text })}>{edit.isPending ? "Saving..." : "Save edits"}</GhostButton>
        <GhostButton onClick={onRegenerate}>{regenerating ? "Regenerating..." : "Regenerate"}</GhostButton>
        <PrimaryButton disabled={!open || changed || submit.isPending} onClick={() => submit.mutate(draft.draft_id)}>
          {submit.isPending ? "Submitting..." : "Submit for legal review"}
        </PrimaryButton>
      </div>
      {open && changed && <p className="mt-1 text-xs text-[var(--muted)]">Save your edits before you submit.</p>}
      <Failure error={edit.error} />
      <Failure error={submit.error} />
    </div>
  );
}

// Operations view. The draft is a plain template filled from verified records, so it never predicts an outcome.
export default function ClientReplyStep() {
  const kicker = useStepKicker("reply");
  const { caseId = "" } = useParams();
  const reply = useReplyDraft(caseId);
  const missing = useMissingFields(caseId);
  const regenerate = useRegenerateReply(caseId);
  const create = useCreateMissing(caseId);
  const [showMissing, setShowMissing] = useState(false);

  const openMissing = () => {
    setShowMissing(true);
    if (!missing.data?.draft) create.mutate();
  };
  const data = reply.data;
  const missingDraft = missing.data?.draft ?? create.data?.draft ?? null;

  return (
    <StepFrame kicker={kicker} title="Client reply" note="Drafted from the case records. You can edit it before it goes to legal review.">
      {reply.isPending && <p className="text-[var(--muted)]">Loading the client question...</p>}
      {reply.isError && (
        <p className="text-[var(--bad)]" role="alert">
          {reply.error.message}
        </p>
      )}
      {data && !data.question && <p className="mb-3 rounded-xl bg-[var(--soft)] p-3.5">No client question is waiting</p>}
      {data?.question && <QuestionCard question={data.question} />}
      {!showMissing && data?.triage && <TriagePills triage={data.triage} reason={data.refusal_reason} />}
      {!showMissing && data?.draft && (
        <DraftBox
          key={`${data.draft.draft_id}-${data.draft.updated_at}`}
          caseId={caseId}
          draft={data.draft}
          onRegenerate={() => regenerate.mutate()}
          regenerating={regenerate.isPending}
        />
      )}
      {!showMissing && <Failure error={regenerate.error} />}
      {showMissing && (
        <div>
          <h3 className="mb-1 font-bold">Email for missing information</h3>
          {missing.data && missing.data.items.length > 0 && (
            <ul className="mb-3 list-disc pl-5 text-sm">
              {missing.data.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
          {missing.data && missing.data.items.length === 0 && <p className="mb-3 text-sm">Nothing is missing, so there is no email to draft.</p>}
          {create.isPending && <p className="text-[var(--muted)]">Drafting the email...</p>}
          {missingDraft && (
            <DraftBox
              key={`${missingDraft.draft_id}-${missingDraft.updated_at}`}
              caseId={caseId}
              draft={missingDraft}
              onRegenerate={() => create.mutate()}
              regenerating={create.isPending}
            />
          )}
          <Failure error={create.error} />
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {showMissing ? (
          <GhostButton onClick={() => setShowMissing(false)}>Back to the reply</GhostButton>
        ) : (
          <GhostButton onClick={openMissing}>Draft email for missing information</GhostButton>
        )}
      </div>
    </StepFrame>
  );
}
