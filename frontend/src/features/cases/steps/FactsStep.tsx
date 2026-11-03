import { useState } from "react";

import { OkRow, SourceRef } from "../../../components/Stamp";
import StepFrame from "./StepFrame";

function Source({ label, value, source, odd }: { label: string; value: string; source: string; odd?: boolean }) {
  return (
    <div className={`rounded-xl border p-2.5 ${odd ? "border-[var(--bad-soft)] bg-[var(--bad-soft)]" : "border-[var(--line)]"}`}>
      <small className="block text-[var(--muted)]">{label}</small>
      <b className={`block text-xl ${odd ? "text-[var(--bad)]" : ""}`}>{value}</b>
      <SourceRef>{source}</SourceRef>
    </div>
  );
}

// One conflict card with sources side by side, a choice, and the facts that match.
export default function FactsStep() {
  const [choice, setChoice] = useState<"suggest" | "attorney">("suggest");
  return (
    <StepFrame
      kicker="Step 2 of 6"
      title="Do the facts match?"
      note="We compared 9 facts across the passport, the verified profile and the intake call. 8 match. 1 needs your call."
    >
      <div className="mb-3 rounded-2xl border-2 border-[var(--bad)] p-3.5">
        <h3 className="mb-2.5 text-lg font-bold">
          <span className="text-[var(--bad)]" aria-hidden>&#9650; </span>
          The surname is spelled two ways
        </h3>
        <div className="mb-2.5 grid gap-2 sm:grid-cols-3">
          <Source label="Passport" value="Mira Dhawan" source="UP-000001 page 1" />
          <Source label="Verified profile, 16 Sep" value="Mira Dhawan" source="PROFILE full_name" />
          <Source label="Intake call notes (unverified)" value="Mira Dawan" source="Z-0001" odd />
        </div>
        {([
          ["suggest", "Suggest the passport spelling, Dhawan", "Legal confirms it before it goes on the form", "Client asked for this on 22 Oct"],
          ["attorney", "Leave it for legal to decide", "No suggestion is sent", ""],
        ] as const).map(([value, title, hint, why]) => (
          <label
            key={value}
            className={`mt-2 flex cursor-pointer items-start gap-2.5 rounded-xl border p-3 ${
              choice === value ? "border-2 border-[var(--accent)] bg-[var(--soft)]" : "border-[var(--line)]"
            }`}
          >
            <input type="radio" name="fact-choice" checked={choice === value} onChange={() => setChoice(value)} />
            <span>
              <b className="block">{title}</b>
              <small className="text-[var(--muted)]">{hint}</small>
            </span>
            {why && <span className="ml-auto rounded-xl bg-[var(--ok-soft)] px-2.5 py-0.5 text-sm font-semibold text-[var(--ok)]">{why}</span>}
          </label>
        ))}
      </div>
      <OkRow label="Date of birth" value="8 Apr 1982" note="2 sources agree" />
      <OkRow label="Last entry" value="10 Jun 2025" note="3 sources agree" />
      <button type="button" className="text-sm underline">Show 6 more matching facts</button>
    </StepFrame>
  );
}
