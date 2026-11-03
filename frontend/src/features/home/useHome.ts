import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { IconName } from "../../components/Icon";
import type { Tone } from "../../components/Stamp";
import { usDate, usDateTime } from "../../lib/dates";
import { useRole } from "../../lib/role";

export type DueState = "PROPOSED" | "APPROVED" | "CONFLICT" | "OVERDUE";
export type Reason = { key: string; label: string; tone: Tone; text: string };
export type Due = {
  date: string;
  state: DueState;
  days_left: number;
  request_date: string;
  request_event_id: string;
  offset_days: number;
  calendar_date: string | null;
  calendar_event_id: string | null;
};
export type HomeRow = {
  case_id: string;
  name: string;
  stage: string;
  ops_user: string;
  legal_reviewer: string;
  priority: string;
  workflow_status: string;
  reason: Reason;
  due: Due | null;
  next_action: string;
  attention: boolean;
  legal_review: boolean;
  refs: string[];
};
export type Deadline = { case_id: string; name: string; date: string; state: DueState; days_left: number };
export type Activity = {
  case_id: string | null;
  name: string | null;
  occurred_at: string;
  actor: string;
  action: string;
  label: string;
  tone: Tone;
  title: string;
  note: string;
};
export type Option = { value: string; label: string; count: number; tone?: Tone };
export type Home = {
  as_of: string;
  rows: HomeRow[];
  page: number;
  page_size: number;
  total: number;
  assigned: number;
  kpi_total: number;
  kpi_counts: Record<KpiKey, number>;
  stages: Option[];
  reasons: Option[];
  deadlines: Deadline[];
  activity: Activity[];
};

export type KpiKey = "attention" | "soon" | "overdue" | "legal" | "quarantined";
export type Filters = { kpi: KpiKey | ""; stage: string; reason: string; term: string; justMe: boolean };

export const NO_FILTERS: Filters = { kpi: "", stage: "", reason: "", term: "", justMe: true };

// An attorney opens on the cases waiting for a legal decision. Everything else is one click away.
export const defaultFilters = (role: string): Filters => ({ ...NO_FILTERS, kpi: role === "attorney" ? "legal" : "" });

// Tiles in display order. Each tile is also a filter on the table.
export const KPIS: { key: KpiKey; label: string; tone: Tone; icon: IconName }[] = [
  { key: "attention", label: "Needs attention", tone: "warn", icon: "exceptions" },
  { key: "soon", label: "Due in 3 days", tone: "warn", icon: "clock" },
  { key: "overdue", label: "Overdue", tone: "bad", icon: "flag" },
  { key: "legal", label: "Waiting on legal", tone: "ai", icon: "review" },
  { key: "quarantined", label: "Quarantined", tone: "bad", icon: "pause" },
];

export function useHome(filters: Filters = NO_FILTERS, page = 1) {
  const { actor } = useRole();
  const params = new URLSearchParams({ page: String(page), just_me: String(filters.justMe) });
  (["kpi", "stage", "reason", "term"] as const).forEach((key) => {
    const value = key === "term" ? filters.term.trim() : filters[key];
    if (value) params.set(key, value);
  });
  // The server filters and pages. Keeping the previous page on screen while the next one loads avoids a flash.
  return useQuery({ queryKey: ["home", actor, params.toString()], queryFn: () => api<Home>(`/home?${params}`), placeholderData: keepPreviousData });
}

// The server row for one case, wherever it sits in the queue.
export function useHomeRow(caseId: string | undefined) {
  const { actor } = useRole();
  return useQuery({
    queryKey: ["home", actor, "row", caseId],
    queryFn: () => api<Home>(`/home?case_id=${encodeURIComponent(caseId ?? "")}&just_me=false`),
    enabled: !!caseId,
    select: (home) => home.rows[0],
  });
}
// A YYYY-MM-DD value shown as MM/DD/YYYY and a timestamp as MM/DD/YYYY, 3:42 PM. Display only, see lib/dates.ts.
export const formatLong = usDate;
export const formatStamp = usDateTime;

// The server sends days left. This only words it.
export function relativeDays(daysLeft: number): string {
  const count = Math.abs(daysLeft);
  const unit = count === 1 ? "day" : "days";
  if (daysLeft < 0) return `${count} ${unit} overdue`;
  return daysLeft === 0 ? "Today" : `in ${count} ${unit}`;
}

// WITH_ATTORNEY becomes With attorney.
export function humanStatus(code: string): string {
  const words = code.replace(/_/g, " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export const DUE_TONE: Record<DueState, Tone> = { PROPOSED: "ai", APPROVED: "ok", CONFLICT: "bad", OVERDUE: "bad" };
export const DUE_LABEL: Record<DueState, string> = { PROPOSED: "Proposed", APPROVED: "Approved", CONFLICT: "Conflict", OVERDUE: "Overdue" };
