type Props = { page: number; pageSize: number; total: number; onPage: (page: number) => void; label?: string; showSingle?: boolean };

// Previous and Next over the server's pages. Hidden when everything fits on one page, unless showSingle is set.
export default function Pagination({ page, pageSize, total, onPage, label = "Case queue pages", showSingle = false }: Props) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages === 1 && !showSingle) return null;
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const button = "inline-flex h-8 items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-sm font-medium hover:bg-[var(--soft)] disabled:opacity-40 disabled:hover:bg-transparent";
  return (
    <nav className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] bg-[var(--surface)] px-3 py-2.5" aria-label={label}>
      <span className="text-sm text-[var(--muted)]">{`Showing ${first} to ${Math.min(total, page * pageSize)} of ${total}`}</span>
      <span className="flex items-center gap-2">
        <button type="button" className={button} disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Previous
        </button>
        <span className="min-w-24 rounded-lg bg-[var(--soft)] px-3 py-1 text-center text-sm font-semibold" aria-current="page">{`Page ${page} of ${pages}`}</span>
        <button type="button" className={button} disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next
        </button>
      </span>
    </nav>
  );
}
