import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type {
  AiStats,
  CreateTypeBody,
  FieldDefinition,
  PromptCreate,
  PromptDetail,
  PromptList,
  ReviewKind,
  ReviewPage,
  RunOut,
  SampleUpload,
  TestRequest,
  TraceOut,
  TypeDraft,
  TestResult,
  FormTarget,
  NewFormField,
  ToolInfo,
  VersionCreate,
  VersionOut,
} from "./types";

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function usePrompts() {
  return useQuery({ queryKey: ["ai", "prompts"], queryFn: () => api<PromptList>("/ai/prompts") });
}

export function useAiStats() {
  return useQuery({ queryKey: ["ai", "stats"], queryFn: () => api<AiStats>("/ai/stats") });
}

export function usePromptRuns(key: string) {
  return useQuery({
    queryKey: ["ai", "prompt-runs", key],
    queryFn: () => api<RunOut[]>(`/ai/runs?prompt_key=${encodeURIComponent(key)}&limit=20`),
  });
}

export function useRunTrace(id: number, enabled: boolean) {
  return useQuery({ queryKey: ["ai", "trace", id], enabled, staleTime: Infinity, queryFn: () => api<TraceOut>(`/ai/runs/${id}/trace`) });
}

export function useTools() {
  return useQuery({ queryKey: ["ai", "tools"], queryFn: () => api<ToolInfo[]>("/ai/tools"), staleTime: Infinity });
}

export function useFormTargets() {
  return useQuery({ queryKey: ["ai", "form-targets"], queryFn: () => api<FormTarget[]>("/ai/form-targets"), staleTime: 5 * 60_000 });
}

// Adds an additional client field. It then shows in every Fills form field picker and as a row of the Form draft.
export function useAddFormField() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: NewFormField) => api<FormTarget>("/ai/form-fields", json(body)),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["ai", "form-targets"] });
      void client.invalidateQueries({ queryKey: ["form-draft"] });
    },
  });
}

// The schema the server derives from the field definitions. Kept on screen while the next one loads.
export function useOutputSchema(category: string | null, fields: FieldDefinition[]) {
  return useQuery({
    queryKey: ["ai", "output-schema", category, JSON.stringify(fields)],
    queryFn: () => api<Record<string, unknown>>("/ai/output-schema", json({ category, field_definitions: fields })),
    enabled: !!category,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function usePrompt(key: string) {
  return useQuery({
    queryKey: ["ai", "prompt", key],
    queryFn: () => api<PromptDetail>(`/ai/prompts/${key}`),
  });
}

export function useVersions(key: string) {
  return useQuery({
    queryKey: ["ai", "versions", key],
    queryFn: () => api<VersionOut[]>(`/ai/prompts/${key}/versions`),
  });
}

export function useTestRuns(ids: number[]) {
  return useQuery({
    queryKey: ["ai", "runs", ids],
    enabled: ids.length > 0,
    queryFn: async () => (await api<RunOut[]>("/ai/runs")).filter((run) => ids.includes(run.id)),
  });
}

export function useSamples() {
  return useQuery({
    queryKey: ["uploads"],
    queryFn: () => api<SampleUpload[]>("/uploads"),
    retry: false,
  });
}

function useRefresh(key: string) {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ["ai"] }).then(() => client.invalidateQueries({ queryKey: ["ai", "prompt", key] }));
}

export function useSaveVersion(key: string) {
  const refresh = useRefresh(key);
  return useMutation({
    mutationFn: (body: VersionCreate) => api<VersionOut>(`/ai/prompts/${key}/versions`, json(body)),
    onSuccess: refresh,
  });
}

export function useActivate(key: string) {
  const refresh = useRefresh(key);
  return useMutation({
    mutationFn: (version: number) => api<VersionOut>(`/ai/prompts/${key}/activate`, json({ version })),
    onSuccess: refresh,
  });
}

export function useRunTest() {
  return useMutation({
    mutationFn: (body: TestRequest) => api<TestResult>("/ai/test", json(body)),
  });
}

export function useCreatePrompt() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: PromptCreate) => api<PromptDetail>("/ai/prompts", json(body)),
    onSuccess: () => client.invalidateQueries({ queryKey: ["ai", "prompts"] }),
  });
}

export function usePromptState(key: string) {
  const refresh = useRefresh(key);
  return useMutation({
    mutationFn: (action: "enable" | "disable") => api<PromptDetail>(`/ai/prompts/${key}/${action}`, json({})),
    onSuccess: refresh,
  });
}

export function useDeletePrompt(key: string) {
  const refresh = useRefresh(key);
  return useMutation({
    mutationFn: () => api<void>(`/ai/prompts/${key}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
}

export function useRenamePrompt(key: string) {
  const refresh = useRefresh(key);
  return useMutation({
    mutationFn: (title: string) => api<PromptDetail>(`/ai/prompts/${key}`, { ...json({ title }), method: "PATCH" }),
    onSuccess: refresh,
  });
}

export type ReviewFilters = { kind: ReviewKind; q: string; page: number; pageSize: number };

// One server page at a time. The previous page stays on screen while the next one loads.
export function useReview({ kind, q, page, pageSize }: ReviewFilters) {
  const params = new URLSearchParams({ kind, page: String(page), page_size: String(pageSize) });
  if (q) params.set("q", q);
  return useQuery({
    queryKey: ["ai", "review", { kind, q, page, pageSize }],
    queryFn: () => api<ReviewPage>(`/ai/review?${params.toString()}`),
    placeholderData: keepPreviousData,
  });
}

export function useResolveReview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ uploadId, category }: { uploadId: string; category: string }) =>
      api<void>(`/ai/review/${uploadId}/resolve`, json({ category })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["ai", "review"] }),
  });
}

// The AI reads the file and drafts a new document type. Nothing is saved yet.
export function useDraftType() {
  return useMutation({ mutationFn: (uploadId: string) => api<TypeDraft>(`/ai/review/${uploadId}/draft-type`, json({})) });
}

// Creates and activates the type. The server reads the source file again in the background.
export function useCreateType(uploadId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateTypeBody) => api<{ key: string; category: string; reread: string }>(`/ai/review/${uploadId}/create-type`, json(body)),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["ai", "prompts"] });
      void client.invalidateQueries({ queryKey: ["ai", "review"] });
    },
  });
}
