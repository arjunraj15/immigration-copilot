import { Link } from "react-router-dom";

export type Crumb = { label: string; to?: string };

// Trail above a page title. The last crumb is the current page and is not a link.
export default function Breadcrumb({ items, className = "mb-1 text-xs" }: { items: Crumb[]; className?: string }) {
  return (
    <nav aria-label="Breadcrumb" className={`${className} text-[var(--muted)]`}>
      <ol className="flex flex-wrap items-center gap-1.5">
        {items.map((item, index) => (
          <li key={item.label} className="flex items-center gap-1.5">
            {index > 0 && <span aria-hidden="true">/</span>}
            {item.to ? (
              <Link to={item.to} className="underline">
                {item.label}
              </Link>
            ) : (
              <span
                aria-current="page"
                className="font-semibold text-[var(--ink)]"
              >
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
