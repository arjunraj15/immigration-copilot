import { Chip, GhostButton } from "../../../components/Stamp";
import { useAudit, useVerifyChain } from "../audit";

const clock = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

// Audit log. Entries cannot be edited. Verify chain asks the backend to recompute every hash.
export default function ActivityTab({ caseId }: { caseId: string }) {
  const audit = useAudit(caseId);
  const verify = useVerifyChain(caseId);
  const result = verify.data;

  return (
    <div className="pt-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold">Everything that happened on this case</h2>
          <p className="mb-3 text-[var(--muted)]">Every action is recorded here and can't be edited or deleted.</p>
        </div>
        <div className="flex gap-2">
          <GhostButton>Download log</GhostButton>
          <button
            type="button"
            onClick={() => verify.mutate()}
            disabled={verify.isPending}
            className="rounded-xl bg-[var(--ok)] px-4 py-2.5 font-semibold text-white disabled:opacity-60"
          >
            {verify.isPending ? "Checking..." : "Verify chain"}
          </button>
        </div>
      </div>
      {verify.isError && (
        <p className="mb-2 text-sm" role="alert">
          <Chip tone="bad">Check failed</Chip> {verify.error.message}
        </p>
      )}
      {result?.valid && (
        <p className="mb-2 text-sm text-[var(--muted)]">
          <Chip>Chain valid</Chip> {result.entries_checked} entries checked. Each entry links to the one before it.
        </p>
      )}
      {result && !result.valid && result.first_break && (
        <p className="mb-2 text-sm" role="alert">
          <Chip tone="bad">Chain broken</Chip> First problem at entry {result.first_break.seq}: {result.first_break.reason}.
        </p>
      )}
      {audit.isPending && <p className="py-3 text-[var(--muted)]">Loading activity...</p>}
      {audit.isError && (
        <p className="py-3" role="alert">
          <Chip tone="bad">Could not load</Chip> {audit.error.message}
        </p>
      )}
      {audit.data?.entries.length === 0 && <p className="py-3 text-[var(--muted)]">Nothing has happened on this case yet.</p>}
      <div>
        {audit.data?.entries.map(({ entry, display }) => (
          <div key={entry.seq} className="grid grid-cols-[70px_36px_1fr_auto] items-start gap-3 border-t border-[var(--line)] py-2.5">
            <span className="text-sm text-[var(--muted)]">{clock.format(new Date(entry.occurred_at))}</span>
            <span className="grid h-9 w-9 place-items-center rounded-full bg-[var(--soft)] text-xs font-bold">{display.who}</span>
            <span>
              <b>{display.title}</b>
              <small className="block text-[var(--muted)]">{display.note}</small>
              {typeof entry.details.code === "string" && (
                <code className="mt-1 block rounded-md bg-[var(--soft)] px-2 py-1 text-xs">{entry.details.code}</code>
              )}
              <small className="mt-0.5 block font-mono text-[11px] text-[var(--muted)]">#{entry.seq} {entry.row_hash.slice(0, 10)}</small>
            </span>
            <Chip tone={display.tone}>{display.label}</Chip>
          </div>
        ))}
      </div>
    </div>
  );
}
