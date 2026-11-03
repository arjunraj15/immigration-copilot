import { useState } from "react";

import { Chip, PrimaryButton } from "../../components/Stamp";
import Citation from "../cases/Citation";
import FieldConflict from "../cases/steps/FieldConflict";
import { formatUsDate } from "../cases/useCases";
import { type Conflict, type FieldFact, useConfirmProfile, useConflicts, useFacts, useResolve, useSuggest } from "./hooks";

type Mode = "operations" | "attorney";
const LEAVE = "__leave__";
const TYPED = "__typed__";

// The values the sources give, once each. Both forms offer only these.
function choices(fact: FieldFact): string[] {
  return [...new Map(fact.sources.map((s) => [s.value.toLowerCase(), s.value])).values()];
}

function Option({ name, value, picked, onPick, title, hint }: { name: string; value: string; picked: string; onPick: (v: string) => void; title: string; hint?: string }) {
  return (
    <label
      title={hint}
      className={`flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-1.5 text-sm ${picked === value ? "border-[var(--accent)] bg-[var(--soft)] ring-1 ring-[var(--accent)]" : "border-[var(--line)]"}`}
    >
      <input type="radio" name={name} checked={picked === value} onChange={() => onPick(value)} />
      <b>{title}</b>
    </label>
  );
}

function Reason({ field, value, onChange, label }: { field: string; value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label className="block min-w-0 flex-1 text-sm font-semibold">
      {label}
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={1}
        name={`reason-${field}`}
        className="mt-1 block w-full resize-y rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-1.5 font-normal"
      />
    </label>
  );
}

function Failure({ error }: { error: Error | null }) {
  return error ? (
    <p className="mt-2 text-sm text-[var(--bad)]" role="alert">
      {error.message}
    </p>
  ) : null;
}

// Operations does not decide a conflict. Picking an option sends it to the legal reviewer at once and keeps it selected.
function SuggestForm({ caseId, conflict, note }: { caseId: string; conflict: Conflict; note: boolean }) {
  const suggest = useSuggest(caseId);
  const [chosen, setChosen] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const saved = conflict.suggestion;
  const options = choices(conflict);
  // What was sent before shows as selected until another option is picked.
  const sentValue = saved ? (saved.leave_to_attorney ? LEAVE : (options.find((v) => v.toLowerCase() === (saved.suggested_value ?? "").toLowerCase()) ?? "")) : "";
  const picked = chosen ?? sentValue;
  const send = (value: string) =>
    suggest.mutate({
      field: conflict.field,
      value: value === LEAVE ? null : value,
      leave_to_attorney: value === LEAVE,
      reason: reason.trim() || (value === LEAVE ? "Left to legal review" : "Suggested from the sources"),
    });
  const pick = (value: string) => {
    setChosen(value);
    send(value);
  };
  return (
    <div>
      {note && conflict.severity === "high" && <p className="mb-1 text-sm font-semibold">An identity conflict is decided by legal.</p>}
      {saved && (
        <p className="mb-1 flex flex-wrap items-center gap-2 text-sm text-[var(--muted)]">
          <Chip tone="ok">SENT TO LEGAL</Chip>
          {saved.actor} {saved.leave_to_attorney ? "left this to legal" : `suggested ${formatUsDate(saved.suggested_value ?? "")}`}. Reason: {saved.reason}
        </p>
      )}
      <fieldset disabled={suggest.isPending}>
        <legend className="text-sm font-semibold">
          Send to legal <span className="font-normal text-[var(--muted)]">Picking an option sends it. Legal confirms it before it goes on the form.</span>
        </legend>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          {options.map((value) => (
            <Option key={value} name={`suggest-${conflict.field}`} value={value} picked={picked} onPick={pick} title={formatUsDate(value)} hint="Legal confirms it before it goes on the form" />
          ))}
          <Option name={`suggest-${conflict.field}`} value={LEAVE} picked={picked} onPick={pick} title="Submit to Legal" hint="No value is suggested" />
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            onBlur={() => picked && reason.trim() && reason.trim() !== saved?.reason && send(picked)}
            name={`reason-${conflict.field}`}
            aria-label="Note for legal, optional"
            placeholder="Note for legal (optional)"
            className="min-w-48 flex-1 rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-1.5 text-sm"
          />
        </div>
      </fieldset>
      <Failure error={suggest.error} />
    </div>
  );
}

function ResolveForm({ caseId, conflict, reasonRequired }: { caseId: string; conflict: Conflict; reasonRequired: boolean }) {
  const resolve = useResolve(caseId);
  const [picked, setPicked] = useState("");
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  const typing = picked === TYPED;
  const value = typing ? typed.trim() : picked;
  const ready = Boolean(value) && (!(typing || reasonRequired) || Boolean(reason.trim()));
  const hint = conflict.suggestion;
  return (
    <div>
      {hint && (
        <p className="mb-1 text-sm text-[var(--muted)]">
          {hint.actor} {hint.leave_to_attorney ? "left this to you" : `suggested ${formatUsDate(hint.suggested_value ?? "")}`}. Reason: {hint.reason}
        </p>
      )}
      <fieldset>
        <legend className="text-sm font-semibold">Resolve</legend>
        <div className="mt-1 flex flex-wrap gap-2">
          {choices(conflict).map((v) => (
            <Option key={v} name={`resolve-${conflict.field}`} value={v} picked={picked} onPick={setPicked} title={formatUsDate(v)} hint="Use the value this source gives" />
          ))}
          <Option name={`resolve-${conflict.field}`} value={TYPED} picked={picked} onPick={setPicked} title="Type a correction" hint="A reason is required" />
        </div>
      </fieldset>
      {typing && (
        <input
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          aria-label={`Corrected ${conflict.label}`}
          className="mt-2 block w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2"
        />
      )}
      <div className="mt-2 flex items-end gap-3">
        <Reason field={conflict.field} value={reason} onChange={setReason} label={typing || reasonRequired ? "Reason (required)" : "Reason (optional)"} />
        <PrimaryButton onClick={() => resolve.mutate({ field: conflict.field, value, reason: reason.trim() })} disabled={!ready || resolve.isPending}>
          Resolve
        </PrimaryButton>
      </div>
      <Failure error={resolve.error} />
    </div>
  );
}

// A profile value imported from the kit is evidence that nobody has confirmed here yet. Confirming records who and when.
function Matching({ facts, caseId }: { facts: FieldFact[]; caseId: string }) {
  const confirm = useConfirmProfile(caseId);
  if (facts.length === 0) return null;
  return (
    <details className="mb-3">
      <summary className="cursor-pointer text-sm underline">Show {facts.length} matching facts</summary>
      {facts.map((fact) => (
        <div key={fact.field} className="mt-1.5 flex flex-wrap items-center gap-2 rounded-lg bg-[var(--soft)] px-3.5 py-2">
          <b>{fact.label}</b>
          <span>{formatUsDate(fact.value ?? "")}</span>
          <Chip tone="ok">{fact.state === "AGREE" ? "SOURCES AGREE" : "ONE EVIDENCE SOURCE"}</Chip>
          {fact.sources.some((s) => s.source_kind === "PROFILE" && !s.verified) && (
            <button
              type="button"
              disabled={confirm.isPending}
              onClick={() => confirm.mutate(fact.field)}
              className="rounded-lg border border-[var(--accent)] px-2.5 py-0.5 text-xs font-semibold text-[var(--accent)] hover:bg-[var(--surface)]"
            >
              Confirm profile value
            </button>
          )}
          <span className="ml-auto">
            {fact.sources.map((s) => (
              <Citation key={s.source_id} source={s.source_id} showTitle={false} />
            ))}
          </span>
        </div>
      ))}
      {confirm.error && (
        <p className="mt-1 text-sm text-[var(--bad)]" role="alert">
          {confirm.error.message}
        </p>
      )}
    </details>
  );
}

// A value that only a call or message states stays a claim. Nothing is picked, it waits for a document.
function Waiting({ facts }: { facts: FieldFact[] }) {
  if (facts.length === 0) return null;
  return (
    <details className="mb-3">
      <summary className="cursor-pointer text-sm underline">{facts.length} claimed {facts.length === 1 ? "value is" : "values are"} waiting for a document or a person to confirm</summary>
      {facts.map((fact) => (
        <div key={fact.field} className="mt-1.5 flex flex-wrap items-center gap-2 rounded-lg bg-[var(--soft)] px-3.5 py-2">
          <b>{fact.label}</b>
          <span>{formatUsDate(fact.sources[0]?.value ?? "")}</span>
          <Chip tone="warn">{fact.sources.some((s) => s.source_kind === "DOCUMENT") ? "DOCUMENT HELD FOR REVIEW" : fact.sources.some((s) => s.source_kind === "PROFILE") ? "PROFILE ONLY, NEEDS A DOCUMENT" : fact.document_source === false ? "CLAIM, NEEDS CONFIRMING" : "CLAIM, NEEDS A DOCUMENT"}</Chip>
          <span className="ml-auto">
            {fact.sources.map((s) => (
              <Citation key={s.source_id} source={s.source_id} showTitle={false} />
            ))}
          </span>
        </div>
      ))}
    </details>
  );
}

// Fields whose sources disagree, each with the plain words explanation. Whoever the server allows resolves, everyone else suggests.
// The server finds every conflict. This only shows them and sends the choice.
export default function ConflictsPanel({ caseId, mode }: { caseId: string; mode: Mode }) {
  const facts = useFacts(caseId);
  const conflicts = useConflicts(caseId);
  if (facts.isPending || conflicts.isPending) return <p className="mb-3 text-[var(--muted)]">Comparing the sources...</p>;
  const error = facts.error ?? conflicts.error;
  if (error) return <p className="mb-3 text-[var(--bad)]" role="alert">Could not compare the sources: {error.message}</p>;
  const fields = facts.data?.fields ?? [];
  const open = conflicts.data?.conflicts ?? [];
  const decided = fields.filter((f) => f.state === "HUMAN_DECIDED");
  const matching = fields.filter((f) => f.state === "AGREE" || f.state === "SINGLE_SOURCE_EVIDENCE");
  const waiting = fields.filter((f) => f.state === "UNVERIFIED");
  return (
    <section aria-label="Conflicts" className="mb-3">
      {open.length === 0 && decided.length === 0 && <p className="mb-3 text-[var(--muted)]">No sources disagree.</p>}
      {open.map((conflict) => (
        <FieldConflict key={conflict.field} fact={conflict} explanation={conflict.explanation}>
          {conflict.can_resolve ? <ResolveForm caseId={caseId} conflict={conflict} reasonRequired={mode === "operations"} /> : <SuggestForm caseId={caseId} conflict={conflict} note={mode === "operations"} />}
        </FieldConflict>
      ))}
      {decided.map((fact) => (
        <FieldConflict key={fact.field} fact={fact} />
      ))}
      <Waiting facts={waiting} />
      <Matching facts={matching} caseId={caseId} />
    </section>
  );
}
