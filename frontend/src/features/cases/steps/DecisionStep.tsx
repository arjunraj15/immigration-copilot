import { Link, useParams } from "react-router-dom";

import DecisionPanel from "../../review/DecisionPanel";
import { KIND_LABEL, useCaseProposals } from "../../review/useProposals";
import StepFrame from "./StepFrame";
import { useStepKicker } from "./useSteps";

// Decides the proposals for this case through the same panel as the review screen. The server enforces who may decide.
export default function DecisionStep() {
  const kicker = useStepKicker("decision");
  const { caseId = "" } = useParams();
  const proposals = useCaseProposals(caseId);
  return (
    <StepFrame kicker={kicker} title="Your decision" note="Approve or reject each proposal. A rejection needs a reason, and your reason is saved in the activity log.">
      {proposals.isPending && <p className="text-[var(--muted)]">Loading proposals...</p>}
      {proposals.isError && (
        <p className="text-[var(--bad)]" role="alert">
          {proposals.error.message}
        </p>
      )}
      {proposals.data?.length === 0 && <p className="text-[var(--muted)]">No proposal has been sent for this case yet.</p>}
      {proposals.data?.map((item) => (
        <div key={item.proposal_id} className="mb-3">
          <p className="mb-1 text-sm">
            <b>{KIND_LABEL[item.kind]}</b> <span className="font-mono">{item.proposal_id}</span>{" "}
            <Link to={`/review/${item.proposal_id}`} className="underline">
              Open the full proposal
            </Link>
          </p>
          <DecisionPanel proposal={item} />
        </div>
      ))}
    </StepFrame>
  );
}
