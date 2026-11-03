import type { Ref } from "react";

import { KPIS, type Filters, type KpiKey, type Option } from "./useHome";

type Props = {
  filters: Filters;
  reset: Filters;
  actor: string;
  stages: Option[];
  reasons: Option[];
  kpiCounts: Record<KpiKey, number>;
  stageTotal: number;
  reasonTotal: number;
  searchRef: Ref<HTMLInputElement>;
  onChange: (next: Filters) => void;
};

function Select({ label, all, value, options, onPick }: { label: string; all: string; value: string; options: Option[]; onPick: (value: string) => void }) {
  return (
    <label className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--muted)]">
      {label}
      <select
        value={value}
        onChange={(event) => onPick(event.target.value)}
        className="rounded-xl border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5 text-sm font-normal text-[var(--ink)]"
      >
        <option value="">{all}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label} ({option.count})
          </option>
        ))}
      </select>
    </label>
  );
}

// One bar: search, Just me, Status, Stage, Reason and Clear filters. Status and Reason replace the two rows of tiles.
export default function FilterBar({ filters, reset, actor, stages, reasons, kpiCounts, stageTotal, reasonTotal, searchRef, onChange }: Props) {
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  return (
    <section className="mb-3 flex flex-wrap items-center gap-2.5 rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5" aria-label="Filters">
      <input
        ref={searchRef}
        type="search"
        aria-label="Search by name or case id"
        placeholder="Search name or case id"
        autoComplete="off"
        value={filters.term}
        onChange={(event) => set({ term: event.target.value })}
        className="min-w-[220px] max-w-[420px] flex-1 rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2"
      />
      <button
        type="button"
        aria-pressed={filters.justMe}
        onClick={() => set({ justMe: !filters.justMe })}
        className="inline-flex items-center gap-2 rounded-full border border-[var(--line)] bg-[var(--surface)] py-1 pl-1 pr-3 text-sm"
      >
        <i className={`relative block h-5 w-9 rounded-full ${filters.justMe ? "bg-[var(--ok)]" : "bg-[#9aa3b8]"}`}>
          <i className={`absolute top-0.5 block h-4 w-4 rounded-full bg-white transition-all ${filters.justMe ? "left-[18px]" : "left-0.5"}`} />
        </i>
        Just me ({actor})
      </button>
      <Select
        label="Status"
        all="All cases"
        value={filters.kpi}
        options={KPIS.map((kpi) => ({ value: kpi.key, label: kpi.label, count: kpiCounts[kpi.key] }))}
        onPick={(kpi) => set({ kpi: kpi as KpiKey | "" })}
      />
      <Select label="Stage" all={`All stages (${stageTotal})`} value={filters.stage} options={stages} onPick={(stage) => set({ stage })} />
      <Select label="Reason" all={`All reasons (${reasonTotal})`} value={filters.reason} options={reasons} onPick={(reason) => set({ reason })} />
      <button type="button" onClick={() => onChange({ ...reset, justMe: filters.justMe })} className="rounded-full border border-[var(--line)] px-3 py-1 text-sm hover:bg-[var(--soft)]">
        Clear filters
      </button>
      <span className="ml-auto hidden text-xs text-[var(--muted)] xl:block">
        <Key>/</Key> search <Key>j</Key> <Key>k</Key> move <Key>Enter</Key> details
      </span>
    </section>
  );
}

function Key({ children }: { children: string }) {
  return <kbd className="rounded-md border border-b-2 border-[var(--line)] bg-[var(--soft)] px-1.5 font-mono text-[11px] font-semibold">{children}</kbd>;
}
