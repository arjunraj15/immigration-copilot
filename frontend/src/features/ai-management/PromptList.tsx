import { useEffect, useRef, useState } from "react";

import Icon from "../../components/Icon";
import { usePrompts } from "./hooks";
import type { AiStats, PromptSummary, Step } from "./types";

export type ListFilter = "all" | "attn" | "off";

type Group = { id: string; step: Step; label: string; icon: "tag" | "documents"; include: (p: PromptSummary) => boolean };

const GROUPS: Group[] = [
  { id: "classify", step: "classify", label: "Classify", icon: "tag", include: () => true },
  { id: "read", step: "read", label: "Document types", icon: "documents", include: (p) => p.origin !== "ADDITIONAL" },
  { id: "additional", step: "read", label: "Additional document types", icon: "documents", include: (p) => p.origin === "ADDITIONAL" },
];

type Props = {
  selected: string | null;
  onSelect: (key: string) => void;
  onAdd: () => void;
  stats: AiStats | undefined;
  filter: ListFilter;
  onFilter: (filter: ListFilter) => void;
  needType: number;
  onReview: () => void;
};

const needsAttention = (prompt: PromptSummary, stats: AiStats | undefined) => prompt.enabled && (stats?.by_prompt[prompt.key]?.failed ?? 0) > 0;

function Row({ prompt, stats, active, onSelect }: { prompt: PromptSummary; stats: AiStats | undefined; active: boolean; onSelect: (key: string) => void }) {
  const health = stats?.by_prompt[prompt.key];
  const failed = health?.failed ?? 0;
  const dot = !prompt.enabled ? "bg-[var(--line)]" : (health?.ok_pct ?? 100) < 50 ? "bg-[var(--bad)]" : failed > 0 ? "bg-[#d99a00]" : "bg-[var(--ok)]";
  const sub = !prompt.enabled
    ? "Disabled"
    : `${prompt.category === "UNKNOWN" ? "Unknown fallback · " : ""}${prompt.active_version ? `v${prompt.active_version}` : "no active version"}${failed ? ` · ${failed} failed` : ""}`;
  return (
    <li>
      <button
        type="button"
        aria-pressed={active}
        onClick={() => onSelect(prompt.key)}
        className={`flex w-full items-center gap-2 rounded-[10px] border px-2 py-1.5 text-left hover:bg-[var(--soft)] ${active ? "border-[var(--accent)] bg-[var(--soft)]" : "border-transparent"} ${
          prompt.enabled ? "" : `grayscale ${active ? "opacity-75" : "opacity-50"}`
        }`}
      >
        <i className={`h-[9px] w-[9px] flex-none rounded-full ${dot}`} />
        <span className="min-w-0">
          <span className="block truncate text-sm">{prompt.title}</span>
          <small className={`block text-xs ${active && prompt.enabled ? "text-[var(--ink)]" : "text-[var(--muted)]"}`}>{sub}</small>
        </span>
      </button>
    </li>
  );
}

export default function PromptList({ selected, onSelect, onAdd, stats, filter, onFilter, needType, onReview }: Props) {
  const { data, error, isLoading } = usePrompts();
  const [query, setQuery] = useState("");
  const search = useRef<HTMLInputElement>(null);

  // Press / anywhere outside a field to jump to the filter box.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
      if (e.key !== "/" || typing) return;
      e.preventDefault();
      search.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (isLoading) return <p className="text-sm text-[var(--muted)]">Loading prompts</p>;
  if (error || !data) return <p className="text-sm text-[var(--bad)]">Could not load prompts. {String(error)}</p>;

  const all = GROUPS.flatMap(({ step, include }) => (data[step] ?? []).filter(include));
  const term = query.trim().toLowerCase();
  const matches = (p: PromptSummary) =>
    (filter === "all" || (filter === "attn" && needsAttention(p, stats)) || (filter === "off" && !p.enabled)) &&
    (!term || `${p.title} ${p.key}`.toLowerCase().includes(term));
  const counts = { all: all.length, attn: all.filter((p) => needsAttention(p, stats)).length, off: all.filter((p) => !p.enabled).length };
  const shown = GROUPS.map((g) => {
    const own = (data[g.step] ?? []).filter(g.include);
    return { ...g, rows: own.filter(matches), total: own.length };
  });
  const SEGMENTS: { id: ListFilter; label: string; icon?: "exceptions" | "ban" }[] = [
    { id: "all", label: "All" },
    { id: "attn", label: "Attention", icon: "exceptions" },
    { id: "off", label: "Disabled", icon: "ban" },
  ];

  return (
    <>
      <button type="button" className="flex w-full items-center justify-center gap-1.5 rounded-[10px] bg-[var(--accent)] px-3.5 py-[7px] font-semibold text-white hover:brightness-125" onClick={onAdd}>
        <Icon name="plus" /> Add prompt
      </button>
      <div className="relative">
        <Icon name="search" className="absolute left-2.5 top-2.5 h-4 w-4 text-[var(--muted)]" />
        <input
          ref={search}
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter prompts (press /)"
          aria-label="Filter prompts"
          className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] py-1.5 pl-[30px] pr-2 text-sm"
        />
      </div>
      <div className="grid grid-cols-3 gap-0.5 rounded-xl bg-[var(--soft)] p-[3px]" role="tablist" aria-label="Filter prompts by state">
        {SEGMENTS.map((seg) => (
          <button
            key={seg.id}
            type="button"
            role="tab"
            aria-selected={filter === seg.id}
            onClick={() => onFilter(seg.id)}
            className={`flex min-w-0 items-center justify-center gap-1 whitespace-nowrap rounded-[9px] px-1 py-[5px] text-xs ${filter === seg.id ? "bg-[var(--surface)] font-semibold shadow-sm" : "text-[var(--muted)]"}`}
          >
            {seg.label}
            <em className="rounded-full bg-[var(--line)] px-1.5 text-[11px] font-bold not-italic text-[var(--muted)]">{counts[seg.id]}</em>
          </button>
        ))}
      </div>
      <div className="-mx-1 min-h-0 flex-1 overflow-auto px-1">
        {shown.map(({ id, label, icon, rows, total }) =>
          rows.length === 0 ? null : (
            <section key={id}>
              <h2 className="mx-1 mb-1 mt-3 flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-wider text-[var(--muted)] first:mt-1">
                <Icon name={icon} /> {label}
                <em className="rounded-full bg-[var(--line)] px-1.5 text-[11px] font-bold not-italic">{total}</em>
              </h2>
              <ul>
                {rows.map((prompt) => (
                  <Row key={prompt.key} prompt={prompt} stats={stats} active={prompt.key === selected} onSelect={onSelect} />
                ))}
              </ul>
            </section>
          ),
        )}
        {shown.every((g) => g.rows.length === 0) && <p className="py-4 text-center text-sm text-[var(--muted)]">No prompts match this filter.</p>}
      </div>
      <button type="button" onClick={onReview} className="flex flex-none items-center gap-2.5 rounded-xl bg-[var(--warn-soft)] px-3 py-2 text-left hover:brightness-95">
        <Icon name="review" className="h-[22px] w-[22px] text-[var(--warn)]" />
        <span className="flex-1">
          <b className="block">Review queue</b>
          <small className="font-semibold text-[var(--warn)]">{needType === 1 ? "1 document needs a type" : `${needType} documents need a type`}</small>
        </span>
        <Icon name="arrow" className="h-3.5 w-3.5 text-[var(--warn)]" />
      </button>
    </>
  );
}
