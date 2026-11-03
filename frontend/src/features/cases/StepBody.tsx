import { useParams } from "react-router-dom";

import { GhostButton, PrimaryButton } from "../../components/Stamp";
import { useRole } from "../../lib/role";
import { useSteps } from "./steps/useSteps";
import { useCaseDocuments } from "./useCaseDocuments";

type Props = { current: number; onChange: (index: number) => void };

// Current step and the Back and Next footer. Nothing here changes data.
export default function StepBody({ current, onChange }: Props) {
  const { role } = useRole();
  const { caseId = "" } = useParams();
  const files = useCaseDocuments(caseId, { pageSize: 1 });
  const steps = useSteps();
  const index = Math.min(current, steps.length - 1);
  const step = steps[index];
  const last = index >= steps.length - 1;
  // Next waits only while a file is being read. A file that is still pending can be read later.
  const reading = role === "paralegal" && step.key === "documents" && ((files.data?.counts.READING ?? 0) > 0);

  return (
    <div className="flex h-full min-h-0 flex-col pt-3">
      <div className="min-h-0 flex-1 overflow-auto">
        <step.Component />
      </div>
      <div className="mt-3 flex shrink-0 items-center justify-between gap-3 border-t border-[var(--line)] pt-4 text-sm text-[var(--muted)]">
        <GhostButton onClick={() => onChange(Math.max(0, index - 1))}>&larr; Back</GhostButton>
        {reading && <span>You can continue when reading finishes</span>}
        <PrimaryButton disabled={reading} onClick={() => !last && onChange(index + 1)}>
          {last ? "Finish" : `Next: ${steps[index + 1].label.toLowerCase()} →`}
        </PrimaryButton>
      </div>
    </div>
  );
}
