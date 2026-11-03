import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { Tone } from "../../components/Stamp";
import { usDate } from "../../lib/dates";
import { useRole } from "../../lib/role";

export type QueueItem = { case_id: string; initials: string; name: string; number: string; note: string; tone: Tone | "info" };
export type QueueGroup = { key: string; title: string; items: QueueItem[] };
export type Queue = { as_of: string; groups: QueueGroup[] };

export type CaseInfo = {
  case_id: string;
  name: string;
  number: string;
  archetype: string;
  stage: string;
  stage_code: string;
  ops_user: string;
  legal_reviewer: string;
  workflow_status: string;
  portal_status: { event_id: string; date: string; label: string | null; details: string } | null;
};

export type TimelineKind = "verified" | "unverified" | "proposed" | "wrong" | "claim" | "activity" | "refused" | "today";
export type TimelineItem = {
  date: string;
  lane: "portal" | "calendar" | "communication" | "activity" | "today";
  kind: TimelineKind;
  title: string;
  note: string;
  ref: string | null;
  why: string;
  manual: boolean;
};

// Query keys include the acting user, so switching user never shows another user's cached cases.
export function useQueue(term: string) {
  const { actor } = useRole();
  return useQuery({ queryKey: ["queue", actor, term], queryFn: () => api<Queue>(`/cases?q=${encodeURIComponent(term)}`) });
}

export function useCaseInfo(caseId: string | undefined) {
  const { actor } = useRole();
  return useQuery({ queryKey: ["case", actor, caseId], queryFn: () => api<CaseInfo>(`/cases/${caseId}`), enabled: !!caseId, retry: false });
}

export function useTimeline(caseId: string) {
  const { actor } = useRole();
  return useQuery({
    queryKey: ["timeline", actor, caseId],
    queryFn: () => api<{ as_of: string; items: TimelineItem[] }>(`/cases/${caseId}/timeline`),
    retry: false,
  });
}

export type CalendarEventType = "CALENDAR_DEADLINE" | "CALENDAR_REMINDER" | "CALENDAR_NOTE";
export type CalendarEventInput = { event_date: string; event_type: CalendarEventType; details: string };

// Demo control: add a hand-typed calendar entry. It is stored unverified and the timeline reloads.
export function useAddCalendarEvent(caseId: string) {
  const { actor } = useRole();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CalendarEventInput) =>
      api(`/cases/${caseId}/calendar-events`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["timeline", actor, caseId] }),
  });
}

// Deletes the case. The server hides it from every list and every page, so everything cached is dropped.
export function useDeleteCase(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api(`/cases/${caseId}`, { method: "DELETE" }),
    onSuccess: () => queryClient.clear(),
  });
}

// Removes an entry added through the demo form. Seeded events cannot be removed.
export function useRemoveCalendarEvent(caseId: string) {
  const { actor } = useRole();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (eventId: string) => api(`/cases/${caseId}/calendar-events/${eventId}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["timeline", actor, caseId] }),
  });
}

export type ProfileField = { field_name: string; verified_value: string; verification_state: string; verified_at: string; source_id: string };
export type CaseSources = { profile_fields: ProfileField[] };

// Verified profile values for one case, each with the source id to cite.
export function useSources(caseId: string | undefined) {
  const { actor } = useRole();
  return useQuery({ queryKey: ["sources", actor, caseId], queryFn: () => api<CaseSources>(`/cases/${caseId}/sources`), enabled: !!caseId, retry: false });
}

// A YYYY-MM-DD value shown as MM/DD/YYYY. Anything else is shown as it came. Display only, see lib/dates.ts.
export const formatUsDate = usDate;

// A short MM/DD for a tight spot such as a calendar chip. Display only, see lib/dates.ts.
export function formatDay(iso: string): string {
  return usDate(iso).slice(0, 5);
}
