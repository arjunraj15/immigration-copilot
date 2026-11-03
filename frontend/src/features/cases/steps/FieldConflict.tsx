import type { ReactNode } from "react";

import { Chip } from "../../../components/Stamp";
import type { FactSource, FieldFact } from "../../facts/hooks";
import { usDate } from "../../../lib/dates";
import Citation from "../Citation";
import { formatUsDate } from "../useCases";

const KIND: Record<FactSource["source_kind"], string> = {
  DOCUMENT: "Document",
  PROFILE: "Profile, checked earlier (may be stale)",
  INTAKE: "Intake call notes",
  MESSAGE: "Client message",
  CLAIM: "Call or message file",
};

const PHASE: Record<FactSource["phase"], string> = {
  BASELINE: "Intake call",
  UPDATE: "Update after the call",
  DOCUMENT: "Document",
  PROFILE: "Profile",
};

const STATE_PILL = {
  CONFLICT: { tone: "bad", text: "CONFLICT" },
  UNVERIFIED: { tone: "warn", text: "UNVERIFIED" },
  HUMAN_DECIDED: { tone: "ok", text: "DECIDED" },
} as const;

// Display only. The server decides the dates it sends.
export const usDay = usDate;

function trustNote(source: FactSource): string | null {
  if (source.from_image) return "Read from a scanned page, unverified";
  if (source.source_kind === "DOCUMENT" && !source.verified) return "The quote was not found in the page text, unverified";
  return null;
}

type ValueGroup = { key: string; value: string; sources: FactSource[]; odd: boolean };

// The sources of one field grouped by the value they give, in the order they first appear. A value shows once and the
// sources that give it are listed under it, so the same value is not repeated on a tile for each source.
function groupByValue(sources: FactSource[]): ValueGroup[] {
  const groups = new Map<string, ValueGroup>();
  for (const source of sources) {
    const key = source.value.trim().toLowerCase();
    const group = groups.get(key) ?? { key, value: source.value, sources: [], odd: true };
    group.sources.push(source);
    group.odd = group.odd && source.odd;
    groups.set(key, group);
  }
  return [...groups.values()];
}

function SourceLine({ source }: { source: FactSource }) {
  const note = trustNote(source);
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
      <span className="text-[var(--muted)]">{KIND[source.source_kind]}</span>
      {source.phase === "UPDATE" && <Chip tone="muted">{PHASE[source.phase]}</Chip>}
      <Chip tone={source.trust === "EVIDENCE" ? "ok" : "warn"}>{source.trust === "EVIDENCE" ? "EVIDENCE" : "CLAIM"}</Chip>
      <Citation source={source.page ? `${source.source_id} page ${source.page}` : source.source_id} showTitle={false} />
      {source.quote && <small className="italic text-[var(--muted)]">&ldquo;{source.quote}&rdquo;</small>}
      {note && <small className="w-full text-[var(--warn)]">{note}</small>}
    </li>
  );
}

function ValueBlock({ group }: { group: ValueGroup }) {
  return (
    <div className={`rounded-xl border px-3 py-2 ${group.odd ? "border-[var(--bad)] bg-[var(--bad-soft)]" : "border-[var(--line)]"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <b className={`break-words text-lg leading-tight ${group.odd ? "text-[var(--bad)]" : ""}`}>{formatUsDate(group.value)}</b>
        {group.odd && <Chip tone="bad">ODD ONE OUT</Chip>}
        <small className="text-[var(--muted)]">{group.sources.length === 1 ? "1 source" : `${group.sources.length} sources`}</small>
      </div>
      <ul className="mt-1 space-y-0.5">
        {group.sources.map((source) => (
          <SourceLine key={`${source.source_id}-${source.value}`} source={source} />
        ))}
      </ul>
    </div>
  );
}

// One field whose sources disagree, were never checked against a document, or were decided by an attorney.
// The sources are grouped under the value each one gives and nothing is picked here. The actions arrive as children.
export default function FieldConflict({ fact, explanation, children }: { fact: FieldFact; explanation?: string; children?: ReactNode }) {
  const pill = STATE_PILL[fact.state as keyof typeof STATE_PILL];
  const decision = fact.decided_by;
  return (
    <div className={`mb-2 rounded-2xl border-2 px-3.5 py-2.5 ${fact.state === "HUMAN_DECIDED" ? "border-[var(--ok)]" : "border-[var(--bad)]"}`}>
      <h3 className="mb-1 flex flex-wrap items-center gap-2 text-base font-bold">
        {fact.label}
        {pill && <Chip tone={pill.tone}>{fact.state === "HUMAN_DECIDED" && decision ? `DECIDED BY ${decision.reviewer_id}` : pill.text}</Chip>}
        <Chip tone="muted">{fact.severity === "high" ? "HIGH SEVERITY" : "MEDIUM SEVERITY"}</Chip>
      </h3>
      {explanation && <p className="mb-2 text-sm">{explanation}</p>}
      {fact.change && <p className="mb-2.5 text-sm text-[var(--warn)]">A later message changed this after the intake call. Nothing is updated automatically.</p>}
      {decision && (
        <p className="mb-2.5 rounded-xl bg-[var(--ok-soft)] px-3 py-2 text-sm">
          <b>{formatUsDate(fact.value ?? "")}</b> was decided by {decision.reviewer_id}, {decision.reviewer_role ? decision.reviewer_role.toLowerCase().replace(/_/g, " ") + ", " : ""}on {usDay(decision.recorded_at)}.
          {decision.reason && ` Reason: ${decision.reason}`}
        </p>
      )}
      <div className="mb-2 grid gap-2 sm:grid-cols-2">
        {groupByValue(fact.sources).map((group) => (
          <ValueBlock key={group.key} group={group} />
        ))}
      </div>
      {children}
    </div>
  );
}
