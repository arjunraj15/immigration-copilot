import { Chip, GhostButton, SourceRef, type Tone } from "../../components/Stamp";
import Icon from "../../components/Icon";
import Citation from "./Citation";
import { sourceKind } from "./sourceId";
import { useInvestigate, type Investigation } from "./useInvestigate";

const ORIGIN: Record<Investigation["origin"], { tone: Tone; label: string }> = {
  MODEL: { tone: "ai", label: "AI explanation, checked by code" },
  FALLBACK: { tone: "muted", label: "Built from the case records, no AI" },
  REFUSED: { tone: "warn", label: "Not answered" },
};

function argText(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([key, value]) => `${key}=${String(value)}`)
    .join(", ");
}

// "Why is this blocked?" The answer is an explanation with the tool results it cites. It is never a draft to send.
export default function InvestigatePanel({ caseId }: { caseId: string }) {
  const run = useInvestigate(caseId);
  const result = run.data;

  return (
    <section className="mt-4 rounded-2xl border border-[var(--line)] p-4" aria-label="Why is this blocked">
      <div className="flex flex-wrap items-center gap-3">
        <Icon name="ai" />
        <b>Why is this blocked?</b>
        {result && <Chip tone={ORIGIN[result.origin].tone}>{ORIGIN[result.origin].label}</Chip>}
        <span className="ml-auto">
          <GhostButton onClick={() => run.mutate()}>{run.isPending ? "Checking this case..." : result ? "Check again" : "Explain what blocks this case"}</GhostButton>
        </span>
      </div>
      {run.isError && <p className="mt-3 text-[var(--bad)]">The explanation could not be made. Try again.</p>}
      {result && (
        <div className="mt-3">
          <p className="font-semibold">{result.answer}</p>
          <ul className="mt-2 list-disc pl-5">
            {result.reasons.map((reason, i) => (
              <li key={i} className="mb-1.5">
                {reason.text}{" "}
                {reason.source_ids.map((id) => (sourceKind(id) === "unknown" ? <SourceRef key={id}>{id}</SourceRef> : <Citation key={id} source={id} showTitle={false} />))}
                <small className="text-[var(--muted)]">Tool results {reason.cited.join(", ")}</small>
              </li>
            ))}
          </ul>
          {result.dropped > 0 && <p className="text-sm text-[var(--muted)]">{result.dropped} statement(s) were left out because they had no checked source.</p>}
          {result.injection_flagged && <p className="text-sm text-[var(--warn)]">Text in a case file tried to give instructions. It was not followed.</p>}
          <p className="text-sm text-[var(--muted)]">{result.note}</p>
          {result.trace.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer font-semibold">Tool trace ({result.trace.length})</summary>
              <ol className="mt-1 pl-5">
                {result.trace.map((step) => (
                  <li key={step.result_id} className="font-mono text-xs">
                    {step.result_id} {step.tool}({argText(step.args)})
                  </li>
                ))}
              </ol>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
