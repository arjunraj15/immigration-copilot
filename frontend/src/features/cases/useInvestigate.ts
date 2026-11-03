import { useMutation } from "@tanstack/react-query";

import { api } from "../../api/client";
import { useRole } from "../../lib/role";

export type InvestigationReason = { text: string; cited: string[]; source_ids: string[] };
export type TraceStep = { tool: string; args: Record<string, unknown>; result_id: string };

export type Investigation = {
  question: string;
  answer: string;
  reasons: InvestigationReason[];
  trace: TraceStep[];
  origin: "MODEL" | "FALLBACK" | "REFUSED";
  dropped: number;
  injection_flagged: boolean;
  note: string;
};

// The server runs read only tools on this one case. The answer is an explanation and nothing is sent or changed.
export function useInvestigate(caseId: string) {
  const { actor } = useRole();
  return useMutation({
    mutationKey: ["investigate", actor, caseId],
    mutationFn: () =>
      api<Investigation>(`/cases/${encodeURIComponent(caseId)}/investigate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      }),
  });
}
