import { useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import { Chip, PrimaryButton } from "../../components/Stamp";
import PossibleMatches from "./PossibleMatches";
import { matchesOf, useNameCandidates, useSubmitCase, type NameCandidate } from "./useIntake";

const KIND_LABELS = { DOCUMENT: "Document", INTAKE: "Zoom note", MESSAGE: "Message", COMMUNICATION: "Call or message file" };
const MANUAL = "manual";
const normal = (value: string) => value.trim().replace(/\s+/g, " ").toLowerCase();
// One entry per distinct name. Every source that gave the name is listed under it as a citation.
type NameGroup = { key: string; value: string; sources: NameCandidate[] };
function groupNames(list: NameCandidate[]): NameGroup[] {
  const groups = new Map<string, NameGroup>();
  for (const c of list) {
    const key = normal(c.value);
    const group = groups.get(key);
    if (group) group.sources.push(c);
    else groups.set(key, { key, value: c.value.trim(), sources: [c] });
  }
  return [...groups.values()];
}

// The client name comes from a candidate or is typed. Nothing is picked when sources disagree or none exist.
export default function NameStep({ caseId, onSubmitted }: { caseId: string; onSubmitted: (name: string) => void }) {
  const candidates = useNameCandidates(caseId);
  const submit = useSubmitCase();
  const [choice, setChoice] = useState<string | null>(null);
  const [manual, setManual] = useState("");
  const manualInput = useRef<HTMLInputElement>(null);
  const list = candidates.data?.candidates ?? [];
  const conflict = candidates.data?.conflict ?? false;
  // A single agreeing candidate is preselected. It still needs the click on Submit.
  const groups = groupNames(list);
  const only = !conflict && groups.length === 1 ? groups[0] : null;
  const selected = choice ?? (only ? only.key : null);
  const picked = groups.find((g) => g.key === selected)?.sources[0] ?? null;
  const typing = selected === MANUAL || (candidates.isSuccess && list.length === 0);
  const needsName = typing && !manual.trim();
  const name = typing ? manual.trim() : (picked?.value ?? "");
  useEffect(() => {
    if (needsName) manualInput.current?.focus();
  }, [needsName]);
  const matches = matchesOf(submit.error);
  const failure = submit.error && !(submit.error instanceof ApiError && submit.error.status === 409) ? submit.error : null;
  const send = (confirmNew: boolean) =>
    submit.mutate(
      { caseId, name, nameSource: typing ? "MANUAL" : "EXTRACTED", sourceId: typing ? null : (picked?.source_id ?? null), confirmNew },
      { onSuccess: (data) => onSubmitted(data.name) },
    );
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {candidates.isPending && <p className="text-[var(--muted)]">Looking for the client name...</p>}
      {candidates.isError && (
        <p className="text-[var(--bad)]" role="alert">
          Could not load the names: {candidates.error.message}
        </p>
      )}
      {conflict && (
        <p className="mb-2 rounded-xl bg-[var(--warn-soft)] px-3 py-2 font-semibold text-[var(--warn)]" role="alert">
          Sources disagree, choose the spelling to use. Nothing is picked for you.
        </p>
      )}
      <ul className="min-h-0 flex-1 overflow-y-auto" aria-label="Name candidates">
        {groups.map((g) => (
          <li key={g.key}>
            <label className={`mb-2 flex cursor-pointer items-start gap-3 rounded-xl border-2 p-3 ${selected === g.key ? "border-[var(--accent)] bg-[var(--soft)]" : "border-[var(--line)]"}`}>
              <input type="radio" name="client-name-choice" checked={selected === g.key} onChange={() => setChoice(g.key)} className="mt-1" />
              <span className="min-w-0 flex-1">
                <b className="text-lg">{g.value}</b>
                <span className="mt-1 flex flex-wrap gap-1">
                  {g.sources.map((c) => (
                    <Chip key={`${c.source_id}-${c.quote}`} tone="muted">{KIND_LABELS[c.source_kind]} {c.source_id}</Chip>
                  ))}
                </span>
                {g.sources.some((c) => c.from_image) && <small className="block text-[var(--warn)]">Read from a scanned page, unverified</small>}
              </span>
            </label>
          </li>
        ))}
      </ul>
      {groups.length > 0 && (
        <label className={`mb-2 flex cursor-pointer items-center gap-3 rounded-xl border-2 p-3 ${selected === MANUAL ? "border-[var(--accent)] bg-[var(--soft)]" : "border-[var(--line)]"}`}>
          <input type="radio" name="client-name-choice" checked={selected === MANUAL} onChange={() => setChoice(MANUAL)} />
          <b>Enter the name manually</b>
        </label>
      )}
      {typing && (
        <div>
          <label className="block font-semibold" htmlFor="client-name">
            Client name
          </label>
          <input
            id="client-name"
            ref={manualInput}
            aria-invalid={needsName}
            value={manual}
            onChange={(event) => {
              setManual(event.target.value);
              submit.reset();
            }}
            className={`mt-1.5 w-full rounded-xl border-2 px-3 py-2.5 ${needsName ? "border-[var(--accent)] bg-[var(--soft)]" : "border-[var(--line)]"}`}
          />
          {needsName && (
            <p className="mt-2 rounded-xl bg-[var(--warn-soft)] px-3 py-2 text-sm font-semibold text-[var(--warn)]" role="alert">
              Add the client name to continue.
            </p>
          )}
        </div>
      )}
      <PossibleMatches matches={matches} />
      {matches.length > 0 && (
        <p className="mt-2 text-sm">
          Not the same client?{" "}
          <button type="button" disabled={submit.isPending} onClick={() => send(true)} className="font-semibold underline">
            Create anyway
          </button>
        </p>
      )}
      {failure && (
        <p className="mt-3 rounded-xl bg-[var(--bad-soft)] px-3 py-2 text-sm text-[var(--bad)]" role="alert">
          Could not submit the case: {failure.message}
        </p>
      )}
      <div className="mt-3 text-right">
        <PrimaryButton disabled={!name || submit.isPending} onClick={() => send(false)}>
          {submit.isPending ? "Submitting..." : "Submit case"}
        </PrimaryButton>
      </div>
    </div>
  );
}
