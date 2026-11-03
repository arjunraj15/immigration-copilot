import { useState } from "react";

import { PrimaryButton } from "../../components/Stamp";
import { newKey } from "../review/format";
import { STAGE_LABEL, STATUS_LABEL, useCaseProposals, useProposeKind } from "../review/useProposals";
import { useCaseInfo } from "./useCases";

// The case stage shown in the header of every tab and step. Operations and legal can change it.
export default function CaseStage({ caseId }: { caseId: string }) {
  const info = useCaseInfo(caseId);
  const existing = useCaseProposals(caseId);
  const propose = useProposeKind(caseId);
  const [open, setOpen] = useState(false);
  const [stage, setStage] = useState("");
  const [reason, setReason] = useState("");
  const current = info.data?.stage_code;
  const sent = (existing.data ?? []).find((item) => item.kind === "STAGE_CHANGE" && item.status === "PENDING_LEGAL_REVIEW");

  const pending = sent ? `Change to ${STAGE_LABEL[String(sent.value.to_stage)] ?? "new stage"}: ${STATUS_LABEL[sent.status].text}` : null;

  const submit = () =>
    propose.mutate(
      { kind: "STAGE_CHANGE", key: newKey(), value: { to_stage: stage, reason: reason.trim() } },
      {
        onSuccess: () => {
          setStage("");
          setReason("");
          setOpen(false);
        },
      },
    );

  return (
    <div className="relative flex items-center gap-2 text-sm">
      <button
        type="button"
        aria-expanded={open}
        title={pending ?? "Case stage. Click to change it."}
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-[var(--line)] bg-[var(--soft)] px-3 py-1 text-sm font-semibold hover:bg-[var(--surface)]"
      >
        <span className="text-[var(--muted)]">Stage</span>
        <b>{info.data?.stage ?? "..."}</b>
        {pending && <span className="size-2 rounded-full bg-[var(--warn)]" aria-label={pending} />}
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden>
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="absolute left-0 top-full z-10 mt-1 w-80 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3 shadow-lg">
          <p className="mb-2 text-xs text-[var(--muted)]">The stage changes as soon as you apply it.</p>
          <label className="block text-sm font-semibold">
            New stage
            <select className="mt-1 block w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] p-2" value={stage} onChange={(e) => setStage(e.target.value)}>
              <option value="">Choose a stage</option>
              {Object.entries(STAGE_LABEL).map(([code, label]) => (
                <option key={code} value={code} disabled={code === current}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="mt-2 block text-sm font-semibold">
            Reason (optional)
            <input className="mt-1 block w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] p-2" value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <div className="mt-3">
            <PrimaryButton disabled={!stage || propose.isPending} onClick={submit}>
              Change stage
            </PrimaryButton>
          </div>
          {propose.isError && (
            <p className="mt-2 text-sm text-[var(--bad)]" role="alert">
              {propose.error.message}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
