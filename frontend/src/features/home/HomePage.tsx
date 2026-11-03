import { useEffect, useRef, useState } from "react";

import Icon from "../../components/Icon";
import { PrimaryButton } from "../../components/Stamp";
import { useRole } from "../../lib/role";
import UploadWizard from "../upload/UploadWizard";
import CaseTable from "./CaseTable";
import FilterBar from "./FilterBar";
import Pagination from "./Pagination";
import SideRail from "./SideRail";
import { defaultFilters, formatLong, useHome, type Filters } from "./useHome";

function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName));
}

// Command list home page. Full width table of the acting user's cases in urgency order, with a side rail.
export default function HomePage() {
  const { role, actor } = useRole();
  const [filters, setFilters] = useState<Filters>(() => defaultFilters(role));
  const [page, setPage] = useState(1);
  const [sent, setSent] = useState(filters);
  const home = useHome(sent, page);
  const reset = defaultFilters(role);
  const [current, setCurrent] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [uploading, setUploading] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setFilters(defaultFilters(role));
  }, [role]);

  // Typing waits for a pause before asking the server. A tile, dropdown or toggle goes out at once. Any change starts at page 1.
  useEffect(() => {
    const timer = setTimeout(
      () => {
        setSent(filters);
        setPage(1);
      },
      filters.term === sent.term ? 0 : 250,
    );
    return () => clearTimeout(timer);
  }, [filters]);

  const shown = home.data?.rows ?? [];
  // An attorney with the default view and no cases is simply caught up, which is not a filter problem.
  const caughtUp = role === "attorney" && filters.kpi === "legal" && !filters.term && !filters.stage && !filters.reason;
  const emptyText = caughtUp ? "You are all caught up. No cases are waiting for your review right now." : undefined;

  const toggle = (caseId: string) => setOpen((now) => ({ ...now, [caseId]: !now[caseId] }));

  // Keyboard: / searches, j and k move between rows, Enter opens details for the current row.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
      const ids = shown.map((row) => row.case_id);
      if (event.key === "/") {
        event.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (event.key === "j" || event.key === "k") {
        const at = ids.indexOf(current);
        const next = event.key === "j" ? Math.min(ids.length - 1, at + 1) : Math.max(0, at < 0 ? 0 : at - 1);
        if (ids[next]) {
          setCurrent(ids[next]);
          document.getElementById(`row-${ids[next]}`)?.focus();
        }
        return;
      }
      const onControl = event.target instanceof HTMLElement && ["BUTTON", "A"].includes(event.target.tagName);
      if (event.key === "Enter" && current && !onControl) toggle(current);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [shown, current]);

  return (
    <section className="min-w-0" aria-label="Case desk home">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-bold">
          Case queue
          {home.data && (
            <span className="ml-2 text-sm font-normal text-[var(--muted)]">{`As of ${formatLong(home.data.as_of)}. ${home.data.assigned} ${home.data.assigned === 1 ? "case" : "cases"} assigned to ${actor}.`}</span>
          )}
        </h1>
        {role === "paralegal" && (
          <span className="ml-auto">
            <PrimaryButton onClick={() => setUploading(true)}>
              <Icon name="plus" /> Create new case
            </PrimaryButton>
          </span>
        )}
      </div>
      {home.isPending && <p className="text-[var(--muted)]">Loading cases...</p>}
      {home.isError && (
        <p className="text-[var(--bad)]" role="alert">
          Could not load cases: {home.error.message}
        </p>
      )}
      {home.data && (
        <>
          {role === "attorney" && (
            <div className="mb-3 flex gap-0.5 self-start rounded-xl bg-[var(--soft)] p-1 w-fit" role="tablist" aria-label="Case sections">
              {[
                { kpi: "legal" as const, label: "To review" },
                { kpi: "" as const, label: "All my cases" },
              ].map((item) => (
                <button
                  key={item.label}
                  type="button"
                  role="tab"
                  aria-selected={filters.kpi === item.kpi}
                  onClick={() => setFilters({ ...filters, kpi: item.kpi })}
                  className={`rounded-lg px-3.5 py-1.5 ${filters.kpi === item.kpi ? "bg-[var(--surface)] font-semibold shadow-sm" : "text-[var(--muted)]"}`}
                >
                  {item.label} ({item.kpi ? home.data.kpi_counts[item.kpi] : home.data.kpi_total})
                </button>
              ))}
            </div>
          )}
          <FilterBar
            filters={filters}
            reset={reset}
            actor={actor}
            stages={home.data.stages}
            reasons={home.data.reasons}
            kpiCounts={home.data.kpi_counts}
            stageTotal={home.data.stages.reduce((sum, item) => sum + item.count, 0)}
            reasonTotal={home.data.reasons.reduce((sum, item) => sum + item.count, 0)}
            searchRef={searchRef}
            onChange={setFilters}
          />
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_290px]">
            <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)]">
              <CaseTable rows={shown} current={current} open={open} onCurrent={setCurrent} onToggle={toggle} empty={emptyText} />
              <Pagination page={home.data.page} pageSize={home.data.page_size} total={home.data.total} onPage={setPage} />
            </div>
            <SideRail deadlines={home.data.deadlines} activity={home.data.activity} />
          </div>
        </>
      )}
      {uploading && <UploadWizard onClose={() => setUploading(false)} />}
    </section>
  );
}
