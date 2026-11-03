import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../../api/client";

export type Match = { case_id: string; name: string };
export type FileResult = { upload_id: string | null; original_filename: string; status: "accepted" | "refused"; outcome: string | null; reason: string | null };
export type IntakeResult = { case_id: string; results: FileResult[] };

// The server answers 409 with the cases that may be the same client.
export function matchesOf(error: Error | null): Match[] {
  if (!(error instanceof ApiError) || error.status !== 409) return [];
  return (error.detail as { matches?: Match[] } | null)?.matches ?? [];
}

function formOf(files: File[]): FormData {
  const form = new FormData();
  files.forEach((file) => form.append("files", file, file.name));
  return form;
}

export type DraftResult = IntakeResult & { job_id: string | null };
export type Job = { job_id: string; status: "RUNNING" | "SUCCEEDED" | "FAILED"; total: number; done: number; events: { upload_id: string; outcome: string; summary: string | null }[]; reason: string | null };
export type NameCandidate = { value: string; source_id: string; source_kind: "DOCUMENT" | "INTAKE" | "MESSAGE" | "COMMUNICATION"; quote: string; from_image: boolean };
export type NameCandidates = { candidates: NameCandidate[]; conflict: boolean; status: "PROCESSING" | "DONE" };

const REFRESH = [["home"], ["documents"], ["case-documents"], ["queue"], ["case"], ["facts"], ["conflicts"], ["form-draft"]];

// A draft case with the intake text and files. The AI processing starts from this one request.
export function useCreateDraft() {
  return useMutation({
    mutationFn: (files: File[]) => api<DraftResult>("/cases/draft", { method: "POST", body: formOf(files) }),
  });
}

// Progress of the background job, polled until it ends.
export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api<Job>(`/jobs/${encodeURIComponent(jobId ?? "")}`),
    enabled: !!jobId,
    refetchInterval: (query) => (query.state.data?.status === "RUNNING" || !query.state.data ? 3000 : false),
  });
}

export function useNameCandidates(caseId: string) {
  return useQuery({ queryKey: ["name-candidates", caseId], queryFn: () => api<NameCandidates>(`/cases/${encodeURIComponent(caseId)}/name-candidates`) });
}

export type SubmitVars = { caseId: string; name: string; nameSource: "EXTRACTED" | "MANUAL"; sourceId: string | null; confirmNew: boolean };

export function useSubmitCase() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ caseId, name, nameSource, sourceId, confirmNew }: SubmitVars) =>
      api<{ case_id: string; name: string }>(`/cases/${encodeURIComponent(caseId)}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client_name: name, name_source: nameSource, source_id: sourceId, confirm_new: confirmNew }),
      }),
    onSuccess: () => Promise.all(REFRESH.map((queryKey) => client.invalidateQueries({ queryKey }))),
  });
}

export function useDiscardDraft() {
  return useMutation({ mutationFn: (caseId: string) => api<void>(`/cases/${encodeURIComponent(caseId)}/draft`, { method: "DELETE" }) });
}

export function useAddDocuments() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ caseId, files }: { caseId: string; files: File[] }) =>
      api<IntakeResult>(`/cases/${encodeURIComponent(caseId)}/documents`, { method: "POST", body: formOf(files) }),
    onSuccess: () => Promise.all(REFRESH.map((queryKey) => client.invalidateQueries({ queryKey }))),
  });
}

export type ChecklistItem = { category: string; status: "SATISFIED" | "NOT_USABLE" | "MISSING" };

// Required documents per category, decided by the server. Refreshed while the automatic read runs.
export function useChecklist(caseId: string) {
  return useQuery({
    queryKey: ["checklist", caseId],
    queryFn: () => api<ChecklistItem[]>(`/cases/${encodeURIComponent(caseId)}/checklist`),
    refetchInterval: 4000,
  });
}
