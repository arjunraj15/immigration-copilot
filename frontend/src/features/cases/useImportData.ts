import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";

export type ImportBody =
  | { kind: "EVENT"; event_date: string; event_type: string; event_source: "MOCK_PORTAL" | "GOOGLE_CALENDAR_MOCK"; source_reference: string; details: string; source_verified: boolean }
  | { kind: "ZOOM_NOTE"; recorded_at: string; summary: string }
  | { kind: "MESSAGE"; created_at: string; channel: "EMAIL" | "WHATSAPP"; subject: string; body: string };

export type ImportResult = {
  case_id: string;
  kind: string;
  record_id: string;
  result: "INSERTED" | "UPDATED" | "UNCHANGED" | "DUPLICATE_CONTENT";
  duplicate_of: string | null;
  changes: { field: string; label: string; before_state: string | null; after_state: string | null; before_value: string | null; after_value: string | null }[];
  deadline: { before: string | null; after: string | null; before_state: string | null; after_state: string | null } | null;
};

// New mock data for one case. The facts, checklist, deadline and lists all change, so every cached read is refreshed.
export function useImportData(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ImportBody) =>
      api<ImportResult>(`/cases/${encodeURIComponent(caseId)}/import`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
    onSuccess: () => queryClient.invalidateQueries(),
  });
}
