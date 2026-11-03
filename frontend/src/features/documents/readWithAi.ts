import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { Tone } from "../../components/Stamp";

export type ReadResult = {
  upload_id: string;
  outcome: string;
  category: string | null;
  reason_code: string | null;
  reason: string | null;
  pages: { page: number; text_source: string; chars: number; reason: string | null }[];
};

export const POLL_MS = 4000;

// The pill text for an outcome. The server decides the outcome, this only words it.
export function outcomeLabel(outcome: string): string {
  if (outcome === "NEEDS_HUMAN_REVIEW") return "Human review";
  if (outcome === "PENDING") return "Pending";
  if (outcome === "READING") return "Reading";
  if (outcome === "CLAIM_SOURCE") return "Claim source";
  return outcome.replace(/_/g, " ");
}

// A straight word pill for an outcome, for example Human review or Claim source.
export function outcomeWord(outcome: string): string {
  const words = outcomeLabel(outcome).toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export const OUTCOME_TONE: Record<string, Tone> = {
  USABLE: "ok",
  PENDING: "muted",
  READING: "ai",
  CLAIM_SOURCE: "ai",
  DUPLICATE: "warn",
  SUPERSEDED: "warn",
  NEEDS_HUMAN_REVIEW: "warn",
  QUARANTINED: "bad",
  INVALID: "bad",
};

// Poll while any file is waiting to be read or being read. Returns false when none is, which stops the polling.
export function pollWhileReading(items: { outcome: string }[] | undefined): number | false {
  return items?.some((item) => item.outcome === "PENDING" || item.outcome === "READING") ? POLL_MS : false;
}

// The small note shown under an outcome when a page was read from its image.
export function pageSourceNote(result: ReadResult | undefined): string | null {
  return result?.pages.some((page) => page.text_source === "IMAGE") ? "Scanned page read from its image" : null;
}

// A person sends a Human review file to the AI again. force=true skips the cached read.
export function useReadWithAi() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (uploadId: string) => api<ReadResult>(`/uploads/${encodeURIComponent(uploadId)}/read?force=true`, { method: "POST" }),
    onSuccess: () => Promise.all([["documents"], ["case-documents"], ["checklist"], ["exceptions"], ["ai", "review"], ["home"], ["case"]].map((queryKey) => client.invalidateQueries({ queryKey }))),
  });
}
