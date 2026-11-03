import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { useRole } from "../../lib/role";
import type { ProposalStatus } from "../review/useProposals";

export type DraftStatus = "DRAFT" | "PENDING_LEGAL_REVIEW" | "APPROVED" | "REJECTED";
export type DraftKind = "STATUS_REPLY" | "REFUSAL" | "MISSING_FIELDS";
export type Intent = "STATUS_QUESTION" | "DOCUMENT_QUESTION" | "OUTCOME_PREDICTION" | "LEGAL_ADVICE" | "OTHER_CLIENT_DATA" | "OTHER" | "NONE";

export type Triage = {
  intent: Intent;
  question_text: string;
  quote: string;
  supported: boolean;
  injection_flag: boolean;
  origin: "MODEL" | "FALLBACK";
  route: "ANSWER" | "REFUSE_ADVICE" | "REFUSE_OTHER_CLIENT" | "UNSUPPORTED";
  refusal_reason: string | null;
};

export type ReplyDraft = {
  draft_id: string;
  case_id: string;
  kind: DraftKind;
  channel: "WHATSAPP" | "EMAIL";
  subject: string | null;
  body: string;
  reply_to_source_id: string | null;
  source_ids: string[];
  triage: Triage | null;
  status: DraftStatus;
  proposal_id: string | null;
  created_by: string;
  send_status: "DRAFT_NOT_SENT";
  created_at: string;
  updated_at: string;
  proposal: { proposal_id: string; status: ProposalStatus; reviewed_by: string | null; review_reason: string | null } | null;
};

export type ReplyQuestion = { source_id: string; channel: "WHATSAPP" | "EMAIL"; occurred_at: string; text: string };

export type ReplyDraftResponse = {
  question: ReplyQuestion | null;
  triage: Triage | null;
  draft: ReplyDraft | null;
  refused: boolean;
  refusal_reason: string | null;
  needs_legal_review: boolean;
};

export type MissingFields = { items: string[]; draft: ReplyDraft | null; needs_legal_review: boolean };

const JSON_HEADERS = { "Content-Type": "application/json" };
const base = (caseId: string) => `/cases/${encodeURIComponent(caseId)}`;

// The server builds every draft from the case records. Query keys include the acting user.
export function useReplyDraft(caseId: string) {
  const { actor } = useRole();
  return useQuery({ queryKey: ["reply-draft", actor, caseId], queryFn: () => api<ReplyDraftResponse>(`${base(caseId)}/reply-draft`), retry: false });
}

export function useMissingFields(caseId: string) {
  const { actor } = useRole();
  return useQuery({ queryKey: ["missing-fields", actor, caseId], queryFn: () => api<MissingFields>(`${base(caseId)}/missing-fields-draft`), retry: false });
}

// A draft change shows in the Communication tab, the review lists and the home page.
function useRefreshDrafts() {
  const client = useQueryClient();
  return () =>
    Promise.all(
      ["reply-draft", "missing-fields", "communications", "proposals", "proposal", "case-proposals", "home", "queue", "case"].map((key) =>
        client.invalidateQueries({ queryKey: [key] }),
      ),
    );
}

export function useRegenerateReply(caseId: string) {
  const refresh = useRefreshDrafts();
  return useMutation({ mutationFn: () => api<ReplyDraftResponse>(`${base(caseId)}/reply-draft`, { method: "POST" }), onSuccess: refresh });
}

export function useCreateMissing(caseId: string) {
  const refresh = useRefreshDrafts();
  return useMutation({ mutationFn: () => api<MissingFields>(`${base(caseId)}/missing-fields-draft`, { method: "POST" }), onSuccess: refresh });
}

export function useEditDraft(caseId: string) {
  const refresh = useRefreshDrafts();
  return useMutation({
    mutationFn: (input: { draftId: string; body: string }) =>
      api<ReplyDraft>(`${base(caseId)}/reply-draft/${input.draftId}`, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify({ body: input.body }) }),
    onSuccess: refresh,
  });
}

export function useSubmitDraft(caseId: string) {
  const refresh = useRefreshDrafts();
  return useMutation({
    mutationFn: (draftId: string) => api<{ draft: ReplyDraft }>(`${base(caseId)}/reply-draft/${draftId}/submit`, { method: "POST" }),
    onSuccess: refresh,
  });
}
