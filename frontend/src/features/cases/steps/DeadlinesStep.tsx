import { useParams } from "react-router-dom";

import { Chip, PrimaryButton } from "../../../components/Stamp";
import { formatLongDate, newKey } from "../../review/format";
import { STATUS_LABEL, useCaseProposals, useProposeKind } from "../../review/useProposals";
import Citation from "../Citation";
import { useTimeline, type TimelineItem } from "../useCases";
import StepFrame from "./StepFrame";
import { useStepKicker } from "./useSteps";

function EventLine({ event, tone }: { event: TimelineItem; tone: "ok" | "bad" }) {
  return (
    <div className="mb-1.5 flex flex-wrap items-center gap-3 rounded-lg bg-[var(--soft)] px-3.5 py-2.5">
      <b className={tone === "bad" ? "line-through" : ""}>{formatLongDate(event.date)}</b>
      <span className={tone === "bad" ? "line-through" : ""}>{event.title}</span>
      {event.ref && <Citation source={event.ref} showTitle={false} />}
      <span className="min-w-0 flex-1 text-sm text-[var(--muted)]">{event.note}</span>
      <Chip tone={tone}>{tone === "ok" ? "Verified portal event" : "Calendar, not evidence"}</Chip>
    </div>
  );
}

// Display only. The server worked out the proposed date from the verified request and the rule offset.
export default function DeadlinesStep() {
  const kicker = useStepKicker("deadlines");
  const { caseId = "" } = useParams();
  const timeline = useTimeline(caseId);
  const items = timeline.data?.items ?? [];
  const verified = items.filter((item) => item.kind === "verified" && item.lane === "portal");
  const proposed = items.find((item) => item.kind === "proposed");
  const wrong = items.filter((item) => item.kind === "wrong");
  const existing = useCaseProposals(caseId);
  const propose = useProposeKind(caseId);
  const open = (existing.data ?? []).find((item) => item.kind === "DEADLINE_ACTIVATE" && ["PENDING_LEGAL_REVIEW", "APPROVED", "COMMITTED"].includes(item.status));

  return (
    <StepFrame kicker={kicker} title="Is there a deadline to propose?" note="Only a verified portal event starts a deadline. Calendar entries and messages never do.">
      {timeline.isPending && <p className="py-3 text-[var(--muted)]">Loading timeline...</p>}
      {timeline.isError && <p className="py-3 text-[var(--bad)]" role="alert">{timeline.error.message}</p>}
      {timeline.data && (
        <>
          <h3 className="mb-1.5 font-bold">Verified portal events</h3>
          {verified.length === 0 && <p className="mb-3 text-sm text-[var(--muted)]">No verified portal events yet.</p>}
          {verified.map((event) => (
            <EventLine key={event.ref} event={event} tone="ok" />
          ))}
          <h3 className="mb-1.5 mt-4 font-bold">Proposed deadline</h3>
          {proposed ? (
            <div className="rounded-xl border-2 border-[var(--accent)] bg-[var(--soft)] px-3.5 py-2.5">
              <b className="text-lg">{formatLongDate(proposed.date)}</b>
              <Chip tone="ai">Proposal only</Chip>
              <p className="text-sm">{proposed.note}</p>
              <p className="text-sm text-[var(--muted)]">{proposed.why}</p>
            </div>
          ) : (
            <p className="rounded-xl bg-[var(--soft)] px-3.5 py-2.5">No request for evidence, so no deadline is proposed.</p>
          )}
          {wrong.length > 0 && <h3 className="mb-1.5 mt-4 font-bold">Does not match</h3>}
          {wrong.map((event) => (
            <EventLine key={event.ref} event={event} tone="bad" />
          ))}
          <div className="mt-4 rounded-xl border border-[var(--line)] px-3.5 py-3">
            {open ? (
              <p role="status">
                <b className="font-mono">{open.proposal_id}</b> <Chip tone={STATUS_LABEL[open.status].tone}>{STATUS_LABEL[open.status].text}</Chip>
              </p>
            ) : (
              <PrimaryButton
                disabled={!proposed || !proposed.ref || propose.isPending}
                onClick={() =>
                  proposed &&
                  propose.mutate({ kind: "DEADLINE_ACTIVATE", key: newKey(), value: { due_date: proposed.date, trigger_event_id: proposed.ref } })
                }
              >
                {propose.isPending ? "Sending..." : "Propose for legal approval"}
              </PrimaryButton>
            )}
            <p className="mt-2 text-sm text-[var(--muted)]">The server checks the date again against the verified request. Legal decides. Nothing is final before that.</p>
            {propose.isError && (
              <p className="mt-2 text-[var(--bad)]" role="alert">
                {propose.error.message}
              </p>
            )}
          </div>
        </>
      )}
    </StepFrame>
  );
}
