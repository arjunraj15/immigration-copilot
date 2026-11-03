import { useRef } from "react";
import { useParams } from "react-router-dom";

import { Chip, OkRow, PrimaryButton } from "../../../components/Stamp";
import { countRows } from "../../review/FormView";
import { formatStamp, newKey } from "../../review/format";
import { useCaseExceptions } from "../../review/useExceptions";
import { STATUS_LABEL, useCaseProposals, useFormDraft, usePropose } from "../../review/useProposals";
import { FORM_SECTIONS } from "../formDraft";
import { useCaseInfo } from "../useCases";
import StepFrame from "./StepFrame";
import { useStepKicker } from "./useSteps";

const labelOf = (target: string): string => FORM_SECTIONS.flatMap((section) => section.fields).find((field) => field.target === target)?.label ?? target;

// Sends the form draft to the assigned attorney. The server builds the form from evidence, this page only asks for it.
export default function SendStep() {
  const kicker = useStepKicker("send");
  const { caseId = "" } = useParams();
  const info = useCaseInfo(caseId);
  const draft = useFormDraft(caseId);
  const existing = useCaseProposals(caseId);
  const propose = usePropose(caseId);
  // Any open exception of the case stops the send: a missing or defective document, a wrong client file, a field conflict.
  // The server decides which ones count and refuses the send as well.
  const exceptions = useCaseExceptions(caseId);
  const blocking = (exceptions.data?.items ?? []).filter((item) => item.blocks_send);
  const openExceptions = blocking.length;
  // One key per open case, so a double click sends the same key and gets the same proposal back.
  const keys = useRef(new Map<string, string>());
  if (!keys.current.has(caseId)) keys.current.set(caseId, newKey());

  const current = propose.data ?? existing.data?.find((item) => item.kind === "FORM_EXPORT");
  const counts = draft.data ? countRows(draft.data) : null;
  // Green is a proposed value. A held row or a row with nothing available keeps the send off until the case is fixed.
  const notGreen = (draft.data?.fields ?? []).filter((row) => row.status !== "PROPOSED");
  const status = current ? STATUS_LABEL[current.status] : null;
  // A rejection is final for that exact form. Ops fixes the case, then sends again under a new key. Unchanged data comes back as the same rejection.
  const rejected = current?.status === "REJECTED";
  const send = () => {
    if (rejected) keys.current.set(caseId, newKey());
    propose.mutate(keys.current.get(caseId) ?? newKey());
  };

  return (
    <StepFrame kicker={kicker} title="Send to legal" note="Check the summary, then send the form draft for a legal decision. Nothing is filed.">
      {info.data && (
        <p className="mb-3 text-sm">
          <b>{info.data.name}</b> <span className="font-mono text-[var(--muted)]">{info.data.case_id}</span>
        </p>
      )}
      {counts && (
        <>
          <OkRow label="Filled" value={`${counts.filled} fields`} />
          <OkRow label="Held for review" value={`${counts.held} fields`} />
          <OkRow label="Not available" value={`${counts.missing} fields`} />
        </>
      )}
      <p className="mt-2 text-sm font-semibold text-[var(--bad)]">DRAFT - NOT FOR FILING</p>
      {(draft.isPending || existing.isPending) && <p className="mt-2 text-[var(--muted)]">Loading...</p>}
      {draft.isError && (
        <p className="mt-2 text-[var(--bad)]" role="alert">
          {draft.error.message}
        </p>
      )}
      {existing.isError && (
        <p className="mt-2 text-[var(--bad)]" role="alert">
          {existing.error.message}
        </p>
      )}
      {current && status && (
        <div className="mt-3 rounded-xl border border-[var(--line)] p-3.5" role="status">
          <b className="font-mono">{current.proposal_id}</b> <Chip tone={status.tone}>{status.text}</Chip>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Legal reviewer {info.data?.legal_reviewer ?? "not known"}. Sent by {current.proposed_by}, {formatStamp(current.proposed_at)}.
          </p>
          {current.review_reason && <p className="mt-1 text-sm">Reason: {current.review_reason}</p>}
          {rejected && (
            <p className="mt-1 text-sm text-[var(--muted)]">
              Legal rejected this form. The rejection stays on record. Fix what legal named in the Exceptions or Form draft step, then send it again.
            </p>
          )}
        </div>
      )}
      {openExceptions > 0 && !current && (
        <p className="mt-2 text-sm text-[var(--bad)]" role="alert">
          {openExceptions} {openExceptions === 1 ? "exception is" : "exceptions are"} still open ({blocking.slice(0, 3).map((item) => item.title).join(", ")}
          {openExceptions > 3 ? ", ..." : ""}). Settle {openExceptions === 1 ? "it" : "them"} in the Exceptions step before sending.
        </p>
      )}
      {notGreen.length > 0 && !current && (
        <p className="mt-2 text-sm text-[var(--bad)]" role="alert">
          {notGreen.length} {notGreen.length === 1 ? "field is" : "fields are"} not green yet ({notGreen.slice(0, 3).map((row) => labelOf(row.target)).join(", ")}
          {notGreen.length > 3 ? ", ..." : ""}). Send to legal is available when every field has a proposed value.
        </p>
      )}
      <div className="mt-3">
        <PrimaryButton
          disabled={(!!current && !rejected) || propose.isPending || !draft.data || existing.isPending || exceptions.isPending || openExceptions > 0 || notGreen.length > 0}
          onClick={send}
        >
          {propose.isPending ? "Sending..." : rejected ? "Send to legal again" : "Send to legal for review"}
        </PrimaryButton>
      </div>
      {propose.isSuccess && propose.data.status === "REJECTED" && (
        <p className="mt-2 text-sm text-[var(--warn)]" role="status">
          Nothing changed since legal rejected it, so the same rejection is shown. Change the case data first.
        </p>
      )}
      {propose.isError && (
        <p className="mt-2 text-[var(--bad)]" role="alert">
          {propose.error.message}
        </p>
      )}
    </StepFrame>
  );
}
