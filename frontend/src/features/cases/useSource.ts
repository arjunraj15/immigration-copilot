import { useQuery } from "@tanstack/react-query";

import { api, apiFile } from "../../api/client";
import { useRole } from "../../lib/role";
import { caseIdFromSource, sourceKind } from "./sourceId";

type Sources = {
  intake_notes: Record<string, unknown>[];
  messages: Record<string, unknown>[];
  profile_fields: Record<string, unknown>[];
  events: Record<string, unknown>[];
};

// Where each record kind lives in the sources response and which field holds its id.
const LISTS = {
  profile: ["profile_fields", "source_id"],
  note: ["intake_notes", "intake_id"],
  message: ["messages", "message_id"],
  event: ["events", "event_id"],
} as const;

export function useUploadFile(uploadId: string) {
  const { actor } = useRole();
  return useQuery({
    queryKey: ["upload-file", actor, uploadId],
    queryFn: () => apiFile(`/uploads/${encodeURIComponent(uploadId)}/file`),
    retry: false,
  });
}

// One record from the case scoped sources route. A user who cannot open the case gets the server error.
export function useSourceRecord(sourceId: string) {
  const { actor } = useRole();
  const caseId = caseIdFromSource(sourceId);
  const kind = sourceKind(sourceId);
  return useQuery({
    queryKey: ["source-record", actor, sourceId],
    enabled: caseId !== null && kind in LISTS,
    retry: false,
    queryFn: async () => {
      const sources = await api<Sources>(`/cases/${caseId}/sources`);
      const [list, key] = LISTS[kind as keyof typeof LISTS];
      return sources[list].find((row) => row[key] === sourceId) ?? null;
    },
  });
}
