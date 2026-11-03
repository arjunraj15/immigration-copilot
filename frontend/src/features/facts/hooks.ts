import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { useRole } from "../../lib/role";

export type FactState = "AGREE" | "CONFLICT" | "UNVERIFIED" | "SINGLE_SOURCE_EVIDENCE" | "NO_SOURCE" | "HUMAN_DECIDED";
export type FactSource = {
  source_id: string;
  source_kind: "DOCUMENT" | "PROFILE" | "INTAKE" | "MESSAGE" | "CLAIM";
  trust: "EVIDENCE" | "CLAIM";
  value: string;
  quote: string | null;
  page: number | null;
  verified: boolean;
  from_image: boolean;
  odd: boolean;
  phase: "BASELINE" | "UPDATE" | "DOCUMENT" | "PROFILE";
};
export type FactDecision = { decision_id: string; reviewer_id: string; reviewer_role: string | null; recorded_at: string; reason: string | null; source_ref: string | null };
export type FieldFact = {
  field: string;
  label: string;
  state: FactState;
  severity: "high" | "medium";
  value: string | null;
  trust: { evidence: number; claim: number };
  sources: FactSource[];
  decided_by: FactDecision | null;
  note: string | null;
  review_open: boolean;
  change: boolean;
  document_source?: boolean;
};
export type Suggestion = { suggested_value: string | null; leave_to_attorney: boolean; reason: string; actor: string; created_at: string };
export type Conflict = FieldFact & {
  explanation: string;
  explanation_origin: "MODEL" | "FALLBACK";
  cited_source_ids: string[];
  can_resolve: boolean;
  suggestion: Suggestion | null;
};

// Facts are rebuilt on the server for each request, so a page that was just seen is not asked again for a short while.
// A decision, an upload or a name change still reloads them at once.
const FACTS_FRESH_MS = 60_000;

// The server builds every state, explanation and decision. Query keys include the acting user.
export function useFacts(caseId: string) {
  const { actor } = useRole();
  return useQuery({
    queryKey: ["facts", actor, caseId],
    queryFn: () => api<{ fields: FieldFact[] }>(`/cases/${encodeURIComponent(caseId)}/facts`),
    staleTime: FACTS_FRESH_MS,
    retry: false,
  });
}

export function useConflicts(caseId: string) {
  const { actor } = useRole();
  return useQuery({
    queryKey: ["conflicts", actor, caseId],
    queryFn: () => api<{ conflicts: Conflict[] }>(`/cases/${encodeURIComponent(caseId)}/conflicts`),
    staleTime: FACTS_FRESH_MS,
    retry: false,
  });
}

// A suggestion or a decision changes the facts, the form draft, the case name and the home reasons.
function useRefreshFacts() {
  const client = useQueryClient();
  return () => Promise.all(["facts", "conflicts", "form-draft", "home", "case", "queue"].map((key) => client.invalidateQueries({ queryKey: [key] })));
}

const JSON_HEADERS = { "Content-Type": "application/json" };

export function useSuggest(caseId: string) {
  const refresh = useRefreshFacts();
  return useMutation({
    mutationFn: (input: { field: string; value: string | null; leave_to_attorney: boolean; reason: string }) =>
      api<Suggestion>(`/cases/${encodeURIComponent(caseId)}/conflicts/${input.field}/suggest`, {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({ value: input.value, leave_to_attorney: input.leave_to_attorney, reason: input.reason }),
      }),
    onSuccess: refresh,
  });
}

export function useConfirmProfile(caseId: string) {
  const refresh = useRefreshFacts();
  return useMutation({
    mutationFn: (field: string) => api<FieldFact>(`/cases/${encodeURIComponent(caseId)}/profile/${field}/confirm`, { method: "POST" }),
    onSuccess: refresh,
  });
}

export function useResolve(caseId: string) {
  const refresh = useRefreshFacts();
  return useMutation({
    mutationFn: (input: { field: string; value: string; reason: string }) =>
      api<FieldFact>(`/cases/${encodeURIComponent(caseId)}/conflicts/${input.field}/resolve`, {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({ value: input.value, reason: input.reason || null }),
      }),
    onSuccess: refresh,
  });
}
