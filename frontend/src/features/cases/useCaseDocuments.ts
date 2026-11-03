import { useEffect, useRef } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { useRole } from "../../lib/role";
import { POLL_MS } from "../documents/readWithAi";

export type PageSource = { page: number; text_source: string; reason: string | null };
export type CaseDocument = {
  upload_id: string;
  original_filename: string;
  category: string | null;
  category_label: string | null;
  outcome: string;
  outcome_reason: string | null;
  reason_code: string | null;
  uploaded_at: string;
  duplicate_of: string | null;
  injection: boolean;
  foreign_pages: number[];
  pages: PageSource[];
};
// total is the number of files matching the outcome filter. counts covers every file of the case.
export type CaseDocumentPage = { total: number; page: number; page_size: number; items: CaseDocument[]; counts: Record<string, number> };
export type DocumentQuery = { page?: number; pageSize?: number; outcome?: string[] };
export const DOCUMENT_PAGE_SIZE = 10;
export const WAITING_OUTCOMES = ["PENDING", "READING"];

export const waitingCount = (counts: Record<string, number> | undefined) => WAITING_OUTCOMES.reduce((sum, key) => sum + (counts?.[key] ?? 0), 0);

export type ChecklistReason = { upload_id: string; outcome: string; reason: string | null };
export type ChecklistItem = { category: string; label: string; status: "SATISFIED" | "NOT_USABLE" | "MISSING"; reasons: ChecklistReason[] };

// One page of the files uploaded to one case. The server limits the list to cases the acting user is assigned to.
export function useCaseDocuments(caseId: string, { page = 1, pageSize = DOCUMENT_PAGE_SIZE, outcome }: DocumentQuery = {}) {
  const { actor } = useRole();
  const filter = outcome?.join(",") ?? "";
  return useQuery({
    queryKey: ["case-documents", actor, caseId, page, pageSize, filter],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (filter) params.set("outcome", filter);
      return api<CaseDocumentPage>(`/cases/${encodeURIComponent(caseId)}/documents?${params}`);
    },
    retry: false,
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (waitingCount(query.state.data?.counts) > 0 ? POLL_MS : false),
  });
}

// The six required categories of one case, worked out by the server. Polls while a file is still being read.
export function useChecklist(caseId: string, polling: number | false = false) {
  const { actor } = useRole();
  return useQuery({
    queryKey: ["checklist", actor, caseId],
    queryFn: () => api<ChecklistItem[]>(`/cases/${encodeURIComponent(caseId)}/checklist`),
    retry: false,
    refetchInterval: polling,
  });
}

// Everything on a case that depends on what the AI read: the lists, the checklist, the facts and conflicts, the exceptions, the form draft,
// the packet, the timeline, the case header and stage, the home page and the replies.
const READ_DEPENDENT = [
  "home", "queue", "case", "documents", "case-documents", "checklist", "facts", "conflicts", "exceptions", "case-exceptions", "form-draft",
  "packet", "timeline", "sources", "communications", "reply-draft", "missing-fields", "case-proposals", "name-candidates",
];

// Mount once for the open case. The upload refreshes the views when the files are saved, but the AI reads them afterwards in a
// background job, so every view would stay as it was until a manual reload. This watches the count of files still being read and
// refreshes all the views once, when it falls to zero.
export function useRefreshWhenReadingDone(caseId: string | undefined) {
  const { actor } = useRole();
  const client = useQueryClient();
  const watch = useQuery({
    queryKey: ["case-documents", actor, caseId, "watch"],
    queryFn: () => api<CaseDocumentPage>(`/cases/${encodeURIComponent(caseId ?? "")}/documents?page=1&page_size=1`),
    enabled: !!caseId,
    retry: false,
    refetchInterval: (query) => (waitingCount(query.state.data?.counts) > 0 ? POLL_MS : false),
  });
  const waiting = watch.data ? waitingCount(watch.data.counts) : undefined;
  const before = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (before.current !== undefined && before.current > 0 && waiting === 0) {
      READ_DEPENDENT.forEach((key) => client.invalidateQueries({ queryKey: [key] }));
    }
    before.current = waiting;
  }, [waiting, client]);
}
