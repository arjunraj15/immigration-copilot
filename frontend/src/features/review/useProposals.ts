import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, apiBlob } from "../../api/client";
import type { Tone } from "../../components/Stamp";
import { useRole } from "../../lib/role";
import type { FormField } from "../cases/formDraft";

export type ProposalKind = "DEADLINE_ACTIVATE" | "FORM_EXPORT" | "PACKET_APPROVE" | "MESSAGE_APPROVE" | "STAGE_CHANGE";
export type ProposalStatus = "PENDING_LEGAL_REVIEW" | "APPROVED" | "REJECTED" | "COMMITTED" | "SENT_BACK";

export type FormValue = {
  form_id: string;
  sections: { title: string; fields: { target: string; label: string; date?: boolean; required?: boolean }[] }[];
  fields: FormField[];
  release_status: string;
};

export type Proposal = {
  proposal_id: string;
  case_id: string;
  kind: ProposalKind;
  status: ProposalStatus;
  value: Record<string, unknown>;
  evidence_ids: string[];
  proposed_by: string;
  reviewed_by: string | null;
  review_reason: string | null;
  committed_by: string | null;
  proposed_at: string;
  reviewed_at: string | null;
  committed_at: string | null;
  client_name: string | null;
};

export const KIND_LABEL: Record<ProposalKind, string> = {
  FORM_EXPORT: "Form export",
  DEADLINE_ACTIVATE: "Deadline activation",
  PACKET_APPROVE: "Packet approval",
  MESSAGE_APPROVE: "Message approval",
  STAGE_CHANGE: "Case stage change",
};

export const STAGE_LABEL: Record<string, string> = {
  INTAKE_REVIEW: "Intake review",
  DOCUMENT_COLLECTION: "Document collection",
  EVIDENCE_REVIEW: "Evidence review",
  READY_FOR_LEGAL_REVIEW: "Ready for legal review",
  WAITING_FOR_PORTAL_EVENT: "Waiting for portal event",
  ON_HOLD: "On hold",
};

export const STATUS_LABEL: Record<ProposalStatus, { text: string; tone: Tone }> = {
  PENDING_LEGAL_REVIEW: { text: "Pending legal review", tone: "warn" },
  APPROVED: { text: "Approved", tone: "ok" },
  REJECTED: { text: "Rejected", tone: "bad" },
  COMMITTED: { text: "Committed", tone: "ai" },
  SENT_BACK: { text: "Sent back", tone: "warn" },
};

// Query keys include the acting user, so switching user never shows another user's cached rows.
export type PacketDoc = { upload_id: string; filename: string };
export type PacketItem = {
  category: string;
  label: string;
  status: "SATISFIED" | "NOT_USABLE" | "MISSING";
  documents: PacketDoc[];
  not_usable: { upload_id: string; outcome: string; reason: string | null }[];
};
export type PacketValue = {
  case_id: string;
  packet_id: string;
  items: PacketItem[];
  usable_count: number;
  missing: string[];
  not_usable_labels: string[];
  complete: boolean;
  release_status: string;
};
export type CaseNote = {
  kind: "DIFFERENT_DATE" | "QUESTION";
  body: string;
  suggested_date: string | null;
  author: string;
  proposal_id: string | null;
  created_at: string;
};

export function usePacket(caseId: string) {
  const { actor } = useRole();
  return useQuery({ queryKey: ["packet", actor, caseId], queryFn: () => api<PacketValue>(`/cases/${caseId}/packet`), retry: false });
}

export function useCaseNotes(caseId: string) {
  const { actor } = useRole();
  return useQuery({ queryKey: ["case-notes", actor, caseId], queryFn: () => api<CaseNote[]>(`/cases/${caseId}/notes`), retry: false });
}

export function useProposals() {
  const { actor } = useRole();
  return useQuery({ queryKey: ["proposals", actor], queryFn: () => api<Proposal[]>("/proposals") });
}

export function useProposal(proposalId: string) {
  const { actor } = useRole();
  return useQuery({ queryKey: ["proposal", actor, proposalId], queryFn: () => api<Proposal>(`/proposals/${proposalId}`), retry: false });
}

export function useCaseProposals(caseId: string) {
  const { actor } = useRole();
  return useQuery({ queryKey: ["case-proposals", actor, caseId], queryFn: () => api<Proposal[]>(`/cases/${caseId}/proposals`), retry: false });
}

export function useFormDraft(caseId: string) {
  const { actor } = useRole();
  return useQuery({ queryKey: ["form-draft", actor, caseId], queryFn: () => api<FormValue>(`/cases/${caseId}/form-draft`), staleTime: 60_000, retry: false });
}

function useRefreshProposals() {
  const client = useQueryClient();
  return () =>
    Promise.all(
      ["proposals", "proposal", "case-proposals", "case-notes", "queue", "case", "home"].map((key) => client.invalidateQueries({ queryKey: [key] })),
    );
}

// The key is made once by the caller, so a double click sends the same key and the server returns the same proposal.
export function usePropose(caseId: string) {
  const refresh = useRefreshProposals();
  return useMutation({
    mutationFn: (idempotencyKey: string) =>
      api<Proposal>(`/cases/${caseId}/proposals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: "FORM_EXPORT", idempotency_key: idempotencyKey }),
      }),
    onSuccess: refresh,
  });
}

// Any kind other than the form export. The key is made once by the caller. The server builds a packet and checks a deadline and a stage.
export function useProposeKind(caseId: string) {
  const refresh = useRefreshProposals();
  return useMutation({
    mutationFn: (input: { kind: ProposalKind; key: string; value?: Record<string, unknown> }) =>
      api<Proposal>(`/cases/${caseId}/proposals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: input.kind, idempotency_key: input.key, value: input.value }),
      }),
    onSuccess: refresh,
  });
}

export function useSendBack(proposalId: string) {
  const refresh = useRefreshProposals();
  return useMutation({
    mutationFn: (input: { kind: "DIFFERENT_DATE" | "QUESTION"; note: string; suggested_date?: string }) =>
      api<Proposal>(`/proposals/${proposalId}/send-back`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      }),
    onSuccess: refresh,
  });
}

export function useReview(proposalId: string) {
  const refresh = useRefreshProposals();
  return useMutation({
    mutationFn: (input: { decision: "APPROVE" | "REJECT"; reason?: string }) =>
      api<Proposal>(`/proposals/${proposalId}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      }),
    onSuccess: refresh,
  });
}

export function useCommit(proposalId: string) {
  const refresh = useRefreshProposals();
  return useMutation({ mutationFn: () => api<Proposal>(`/proposals/${proposalId}/commit`, { method: "POST" }), onSuccess: refresh });
}

export function useDownloadPdf(proposalId: string) {
  return useMutation({ mutationFn: () => apiBlob(`/proposals/${proposalId}/export.pdf`) });
}
