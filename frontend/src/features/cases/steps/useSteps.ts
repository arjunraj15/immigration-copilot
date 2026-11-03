import { useParams } from "react-router-dom";

import { useRole } from "../../../lib/role";
import { useCaseProposals } from "../../review/useProposals";
import { useMissingFields, useReplyDraft } from "../useReplyDraft";
import { useTimeline } from "../useCases";
import { STEPS, type StepDef } from "./registry";

// The steps of the current role. Legal reuses the operations hiding rules, so both sides show the same steps for a case. Deadlines shows only when the case has a proposed deadline, a calendar entry that
// does not match, or a deadline proposal already sent. Client reply shows whenever a client question is waiting, a draft
// exists, or information is missing. Both stay while their data loads so the stepper does not jump.
export function useSteps(): StepDef[] {
  const { role } = useRole();
  const { caseId = "" } = useParams();
  const timeline = useTimeline(caseId);
  const proposals = useCaseProposals(caseId);
  const reply = useReplyDraft(caseId);
  const missing = useMissingFields(caseId);
  const steps = STEPS[role];
  const hidden = new Set<string>();
  if (timeline.data) {
    const deadlineNeeded =
      timeline.data.items.some((item) => item.kind === "proposed" || item.kind === "wrong") ||
      (proposals.data ?? []).some((item) => item.kind === "DEADLINE_ACTIVATE");
    if (!deadlineNeeded) hidden.add(role === "paralegal" ? "deadlines" : "deadline");
  }
  if (reply.data && missing.data) {
    const replyNeeded = Boolean(reply.data.question || reply.data.draft) || missing.data.items.length > 0 || Boolean(missing.data.draft);
    if (!replyNeeded) hidden.add("reply");
  }
  return hidden.size === 0 ? steps : steps.filter((step) => !hidden.has(step.key));
}

// "Step 3 of 6" for the step with this key, counted over the steps that are showing.
export function useStepKicker(key: string): string {
  const steps = useSteps();
  return `Step ${steps.findIndex((step) => step.key === key) + 1} of ${steps.length}`;
}
