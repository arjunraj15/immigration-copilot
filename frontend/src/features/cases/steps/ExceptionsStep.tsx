import { useParams } from "react-router-dom";

import { useRole } from "../../../lib/role";
import ConflictsPanel from "../../facts/ConflictsPanel";
import DocumentExceptions from "./DocumentExceptions";
import { useConflicts } from "../../facts/hooks";
import StepFrame from "./StepFrame";
import { useStepKicker } from "./useSteps";

// Fields whose sources disagree, kept apart from the form so each one can be reviewed and settled quickly.
// A settled value goes on the form draft. Nothing is typed into the form itself.
export default function ExceptionsStep() {
  const kicker = useStepKicker("exceptions");
  const { caseId = "" } = useParams();
  const { role } = useRole();
  const legal = role === "attorney";
  const conflicts = useConflicts(caseId);
  const open = conflicts.data?.conflicts.length ?? 0;

  return (
    <StepFrame
      kicker={kicker}
      title="Exceptions"
      note={
        open > 0
          ? legal
            ? `${open} ${open === 1 ? "field needs" : "fields need"} your decision. Choose a value or type a correction, and it goes on the form draft.`
            : `${open} ${open === 1 ? "field needs" : "fields need"} a decision. Once decided, the value is used on the form draft.`
          : "Nothing needs a decision. The form draft uses the values the sources agree on."
      }
    >
      <DocumentExceptions caseId={caseId} />
      <ConflictsPanel caseId={caseId} mode={legal ? "attorney" : "operations"} />
    </StepFrame>
  );
}
