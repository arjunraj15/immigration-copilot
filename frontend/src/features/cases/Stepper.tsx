import { useRole } from "../../lib/role";
import { STEP_RESULTS } from "./mockData";
import { useSteps } from "./steps/useSteps";

type Props = { current: number; onSelect: (index: number) => void };

// Visa stamp stepper. A finished step shows its result text in a rotated double ring. A step with an issue shows a red ring.
export default function Stepper({ current, onSelect }: Props) {
  const { role } = useRole();
  const steps = useSteps();

  return (
    <div className="mt-2 flex overflow-x-auto border-b border-[var(--line)] pb-2">
      {steps.map((step, index) => {
        const result = STEP_RESULTS[role][index];
        const isCurrent = index === current;
        const stamped = !isCurrent && !!result?.text && (index < current || result.issue);
        const issue = stamped && result?.issue;
        const done = stamped && index < current;
        const lineDone = index < current;

        let circle = "border-2 border-[var(--line)] bg-[var(--surface)] text-base font-semibold text-[var(--muted)]";
        if (isCurrent) circle = "border-2 border-[var(--accent)] bg-[var(--accent)] text-base font-semibold text-white shadow-[0_0_0_4px_var(--soft)]";
        else if (issue) circle = "-rotate-6 border-[3px] border-double border-[var(--bad)] bg-[var(--bad-soft)] text-[8px] font-extrabold leading-tight text-[var(--bad)]";
        else if (done) circle = "-rotate-6 border-[3px] border-double border-[var(--ok)] bg-[var(--ok-soft)] text-[8px] font-extrabold leading-tight text-[var(--ok)]";

        return (
          <button
            key={step.key}
            type="button"
            onClick={() => onSelect(index)}
            aria-current={isCurrent ? "step" : undefined}
            className={`relative min-w-20 flex-1 text-center text-sm ${isCurrent ? "font-semibold" : "text-[var(--muted)]"}`}
          >
            {index < steps.length - 1 && (
              <span
                aria-hidden
                className={`absolute left-[calc(50%+22px)] right-[calc(-50%+22px)] top-[18px] border-t-2 ${
                  lineDone ? "border-solid border-[var(--ok)]" : "border-dashed border-[var(--line)]"
                }`}
              />
            )}
            <span className={`mx-auto mb-1 grid h-9 w-9 place-items-center rounded-full ${circle}`}>
              {stamped ? <span className="px-1">{result.text}</span> : index + 1}
            </span>
            {step.label}
          </button>
        );
      })}
    </div>
  );
}
