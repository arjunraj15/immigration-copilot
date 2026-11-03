import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { useRole } from "../../lib/role";

export type Severity = "HIGH" | "MEDIUM" | "LOW";
export type ExceptionItem = {
  case_id: string;
  client_name: string;
  type: string;
  severity: Severity;
  title: string;
  reason: string;
  source_ids: string[];
  next_action: string;
  owner_role: "OPS" | "LEGAL";
  blocks_send: boolean;
};
export type ExceptionList = { items: ExceptionItem[]; counts: Record<string, number>; total: number };

// The exceptions of one case, for the case's own Exceptions step.
export function useCaseExceptions(caseId: string) {
  const { actor } = useRole();
  return useQuery({
    queryKey: ["case-exceptions", actor, caseId],
    queryFn: () => api<ExceptionList>(`/cases/${encodeURIComponent(caseId)}/exceptions`),
    retry: false,
  });
}

// The server limits the list to the acting user's cases, so the key carries the actor.
export function useExceptions(type: string, term: string) {
  const { actor } = useRole();
  const params = new URLSearchParams();
  if (type) params.set("type", type);
  if (term) params.set("q", term);
  return useQuery({
    queryKey: ["exceptions", actor, type, term],
    queryFn: () => api<ExceptionList>(`/exceptions?${params.toString()}`),
    placeholderData: keepPreviousData,
  });
}
