import { useState } from "react";

import { Chip, GhostButton, PrimaryButton } from "../../components/Stamp";
import { useRole } from "../../lib/role";
import { formatStamp, saveBlob } from "./format";
import { STATUS_LABEL, useCommit, useDownloadPdf, useReview, type Proposal } from "./useProposals";

function Failure({ error }: { error: Error | null }) {
  if (!error) return null;
  return (
    <p className="mt-2 text-[var(--bad)]" role="alert">
      {error.message}
    </p>
  );
}

// Approve, reject, download and commit for one proposal. The server decides who may do what, this only shows the buttons that apply.
export default function DecisionPanel({ proposal }: { proposal: Proposal }) {
  const { role } = useRole();
  const review = useReview(proposal.proposal_id);
  const commit = useCommit(proposal.proposal_id);
  const download = useDownloadPdf(proposal.proposal_id);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const status = STATUS_LABEL[proposal.status];
  const decided = proposal.status === "APPROVED" || proposal.status === "COMMITTED";
  const canDecide = role === "attorney" && proposal.status === "PENDING_LEGAL_REVIEW";
  const canCommit = role === "paralegal" && proposal.status === "APPROVED";
  const canDownload = decided && proposal.kind === "FORM_EXPORT";

  const save = () =>
    download.mutate(undefined, { onSuccess: (blob) => saveBlob(blob, `${proposal.case_id}-form-draft.pdf`) });

  return (
    <div className="rounded-2xl border border-[var(--line)] p-3.5">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <b>Decision</b>
        <Chip tone={status.tone}>{status.text}</Chip>
        {proposal.reviewed_by && (
          <small className="text-[var(--muted)]">
            {proposal.reviewed_by}
            {proposal.reviewed_at && `, ${formatStamp(proposal.reviewed_at)}`}
          </small>
        )}
      </div>
      {proposal.review_reason && <p className="mb-2 text-sm">Reason: {proposal.review_reason}</p>}
      {proposal.committed_at && (
        <p className="mb-2 text-sm text-[var(--muted)]">
          Committed by {proposal.committed_by}, {formatStamp(proposal.committed_at)}
        </p>
      )}
      {canDecide && (
        <div className="flex flex-wrap items-center gap-2">
          <PrimaryButton disabled={review.isPending} onClick={() => review.mutate({ decision: "APPROVE" })}>
            Approve
          </PrimaryButton>
          <GhostButton onClick={() => setRejecting(true)}>Reject</GhostButton>
        </div>
      )}
      {canDecide && rejecting && (
        <div className="mt-3">
          <label className="block text-sm font-semibold" htmlFor={`reason-${proposal.proposal_id}`}>
            Reason for rejecting (required)
          </label>
          <textarea
            id={`reason-${proposal.proposal_id}`}
            className="mt-1 w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] p-2.5"
            rows={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <PrimaryButton
              disabled={review.isPending || reason.trim() === ""}
              onClick={() => review.mutate({ decision: "REJECT", reason: reason.trim() })}
            >
              Confirm reject
            </PrimaryButton>
            <GhostButton
              onClick={() => {
                setRejecting(false);
                setReason("");
              }}
            >
              Cancel
            </GhostButton>
          </div>
        </div>
      )}
      {(canCommit || canDownload) && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {canCommit && (
            <PrimaryButton disabled={commit.isPending} onClick={() => commit.mutate()}>
              Commit
            </PrimaryButton>
          )}
          {canDownload && (
            <GhostButton onClick={save}>{download.isPending ? "Preparing PDF..." : "Download PDF"}</GhostButton>
          )}
        </div>
      )}
      {!canDecide && proposal.status === "PENDING_LEGAL_REVIEW" && (
        <p className="text-sm text-[var(--muted)]">Waiting for the assigned legal reviewer. Operations cannot decide.</p>
      )}
      <Failure error={review.error} />
      <Failure error={commit.error} />
      <Failure error={download.error} />
    </div>
  );
}
