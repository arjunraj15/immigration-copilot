import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { Tone } from "../../components/Stamp";

export type AuditLine = {
  entry: {
    seq: number;
    occurred_at: string;
    actor: string;
    details: Record<string, unknown>;
    row_hash: string;
  };
  display: { who: string; label: string; tone: Tone; title: string; note: string };
};

export type AuditPage = { stream_id: string; total: number; entries: AuditLine[] };

export type VerifyResult = {
  valid: boolean;
  entries_checked: number;
  first_break: { seq: number | null; reason: string } | null;
};

const auditKey = (caseId: string) => ["audit", caseId];

export function useAudit(caseId: string) {
  return useQuery({ queryKey: auditKey(caseId), queryFn: () => api<AuditPage>(`/cases/${caseId}/audit?limit=100`) });
}

// Checking the chain adds a "Verified" line, so the list is refreshed afterwards.
export function useVerifyChain(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api<VerifyResult>(`/cases/${caseId}/audit/verify`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: auditKey(caseId) }),
  });
}
