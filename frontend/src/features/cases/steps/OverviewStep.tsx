import { useParams } from "react-router-dom";

import { OkRow } from "../../../components/Stamp";
import { useRole } from "../../../lib/role";
import { useHomeRow } from "../../home/useHome";
import { countRows } from "../../review/FormView";
import { formatLongDate } from "../../review/format";
import { KIND_LABEL, STATUS_LABEL, useCaseProposals, useFormDraft } from "../../review/useProposals";
import { useCaseDocuments } from "../useCaseDocuments";
import InvestigatePanel from "../InvestigatePanel";
import { useCaseInfo } from "../useCases";
import StepFrame from "./StepFrame";
import { useStepKicker } from "./useSteps";

// Summary rows come from the case, its documents, the form draft, the home row and the proposals. Nothing is made up here.
export default function OverviewStep() {
  const kicker = useStepKicker("overview");
  const { caseId = "" } = useParams();
  const { actor } = useRole();
  const info = useCaseInfo(caseId).data;
  const docs = useCaseDocuments(caseId, { pageSize: 1 }).data;
  const draft = useFormDraft(caseId).data;
  const proposals = useCaseProposals(caseId).data;
  const due = useHomeRow(caseId).data?.due;
  const usable = docs?.counts.USABLE ?? 0;
  const counts = draft ? countRows(draft) : null;

  return (
    <StepFrame
      kicker={kicker}
      title="Overview"
      note={info ? `${info.name}, ${info.archetype}. Prepared by ${info.ops_user}. Stage: ${info.stage}.` : "Loading this case..."}
    >
      {info?.portal_status && (
        <OkRow label="Portal status" value={info.portal_status.label ?? "Not stated"} note={formatLongDate(info.portal_status.date)} />
      )}
      {docs && <OkRow label="Documents" value={`${usable} of ${docs.total} usable`} note={usable === docs.total ? "No issues" : "Some need a look"} />}
      {counts && (
        <OkRow label="Form draft" value={`${counts.filled} filled, ${counts.held} held, ${counts.missing} not available`} />
      )}
      {due && (
        <OkRow
          label="Deadline"
          value={`${formatLongDate(due.date)} proposed`}
          note={due.calendar_date ? "Calendar conflict" : "Matches the portal rule"}
        />
      )}
      {proposals?.map((item) => (
        <OkRow key={item.proposal_id} label={KIND_LABEL[item.kind]} value={item.proposal_id} note={STATUS_LABEL[item.status].text} />
      ))}
      {proposals?.length === 0 && <OkRow label="Proposals" value="None yet" note="Waiting for the paralegal" />}
      <InvestigatePanel key={actor} caseId={caseId} />
    </StepFrame>
  );
}
