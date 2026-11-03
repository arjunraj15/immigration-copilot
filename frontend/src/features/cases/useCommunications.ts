import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { useRole } from "../../lib/role";

export type CommunicationKind = "ZOOM" | "WHATSAPP" | "EMAIL";
export type Communication = {
  source_id: string;
  kind: CommunicationKind;
  direction: "INBOUND" | "OUTBOUND_DRAFT_ONLY" | "NOTE";
  sender_role: string;
  subject: string | null;
  body: string;
  thread_id: string | null;
  occurred_at: string;
  is_draft: boolean;
  claim: boolean;
  client_question: boolean;
  claims: number;
  role: "INTAKE_CALL" | "UPDATE" | "OFFICE_DRAFT";
  claim_rows: { field: string; value: string; quote: string }[];
  // Set for a draft the office wrote in this app. A draft from the starter kit has none.
  draft_status: "DRAFT" | "PENDING_LEGAL_REVIEW" | "APPROVED" | "REJECTED" | null;
};

// Calls and messages of one case, oldest first. Every item is a claim.
export function useCommunications(caseId: string) {
  const { actor } = useRole();
  return useQuery({
    queryKey: ["communications", actor, caseId],
    queryFn: () => api<Communication[]>(`/cases/${encodeURIComponent(caseId)}/communications`),
    retry: false,
  });
}

// Saves pasted text or a chosen file as a document, so it goes through the normal read. The list is refetched a few times after
// a short wait so the extracted claim counts appear. There is no long polling.
export function useAddCommunication(caseId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("files", file, file.name);
      return api<unknown>(`/cases/${encodeURIComponent(caseId)}/documents`, { method: "POST", body: form });
    },
    onSuccess: async () => {
      const refresh = () =>
        Promise.all(["communications", "sources", "case-documents", "documents"].map((queryKey) => client.invalidateQueries({ queryKey: [queryKey] })));
      await refresh();
      [4000, 12000].forEach((wait) => window.setTimeout(() => void refresh(), wait));
    },
  });
}
