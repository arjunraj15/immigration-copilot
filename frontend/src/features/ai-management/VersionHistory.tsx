import { usDateTime } from "../../lib/dates";
import { useActivate, useVersions } from "./hooks";

type Props = { promptKey: string; activeVersion: number | null };

export default function VersionHistory({ promptKey, activeVersion }: Props) {
  const { data, isLoading, error } = useVersions(promptKey);
  const activate = useActivate(promptKey);
  if (isLoading) return <p className="text-sm text-[var(--muted)]">Loading history</p>;
  if (error || !data) return <p className="text-sm text-[var(--bad)]">Could not load history.</p>;
  return (
    <section className="space-y-2">
      {activate.error && <p className="text-sm text-[var(--bad)]">Activate failed. {String(activate.error)}</p>}
      <ul className="space-y-1.5">
        {data.map((item) => (
          <li key={item.id} className="flex flex-wrap items-center gap-2 rounded border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm">
            <span className="font-mono">v{item.version}</span>
            {item.version === activeVersion && (
              <span className="rounded-full bg-[var(--ok-soft)] px-2 py-0.5 text-xs text-[var(--ok)]">Active</span>
            )}
            <span className="text-[var(--muted)]">
              {item.created_by}, {usDateTime(item.created_at)}
            </span>
            {item.note && <span className="text-[var(--muted)]">{item.note}</span>}
            {item.version !== activeVersion && (
              <button
                type="button"
                disabled={activate.isPending}
                onClick={() => activate.mutate(item.version)}
                className="ml-auto rounded border border-[var(--accent)] px-2 py-1 text-xs text-[var(--accent)]"
              >
                Activate v{item.version}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
