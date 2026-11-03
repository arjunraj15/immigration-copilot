import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { useRole } from "../../lib/role";
import { pollWhileReading } from "./readWithAi";

export type DocumentRow = {
  upload_id: string;
  case_id: string;
  client_name: string;
  original_filename: string;
  category: string | null;
  category_label: string | null;
  outcome: string;
  outcome_reason: string | null;
  file_size_bytes: number;
  uploaded_at: string;
  uploader_role: string;
};
export type DocumentPage = { total: number; page: number; page_size: number; items: DocumentRow[] };
export type DocumentFilters = { case: string; client: string; outcome: string; page: number; pageSize: number };

// Keeps the previous page on screen while the next one loads, so the table does not flash empty.
export function useDocuments(filters: DocumentFilters) {
  const { actor } = useRole();
  const params = new URLSearchParams({ page: String(filters.page), page_size: String(filters.pageSize) });
  if (filters.case) params.set("case", filters.case);
  if (filters.client) params.set("client", filters.client);
  if (filters.outcome) params.set("outcome", filters.outcome);
  return useQuery({
    queryKey: ["documents", actor, filters],
    queryFn: () => api<DocumentPage>(`/documents?${params.toString()}`),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => pollWhileReading(query.state.data?.items),
  });
}

// Deletes an uploaded file, with the reason the audit trail keeps. The facts, checklist, stage and lists all change, so every cached read is refreshed.
export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ caseId, uploadId, reason }: { caseId: string; uploadId: string; reason: string }) =>
      api(`/cases/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(uploadId)}?reason=${encodeURIComponent(reason)}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries(),
  });
}
