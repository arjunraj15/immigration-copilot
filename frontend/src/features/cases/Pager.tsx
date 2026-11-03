type Props = { page: number; pageSize: number; total: number; onPage: (page: number) => void };

const BUTTON = "rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 disabled:opacity-40";

// Previous and Next under a list the server pages. Shows nothing when one page holds every file.
export default function Pager({ page, pageSize, total, onPage }: Props) {
  if (total <= pageSize) return null;
  const pages = Math.ceil(total / pageSize);
  const from = (page - 1) * pageSize + 1;
  return (
    <nav className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--line)] bg-[var(--soft)] px-3.5 py-2 text-sm" aria-label="Pages">
      <span className="text-[var(--muted)]">{`${from}-${Math.min(page * pageSize, total)} of ${total}`}</span>
      <span className="flex items-center gap-2">
        <button type="button" className={BUTTON} disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
        <span>{`Page ${page} of ${pages}`}</span>
        <button type="button" className={BUTTON} disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
      </span>
    </nav>
  );
}
