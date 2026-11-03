import { FORM_SECTIONS, type FormField } from "../cases/formDraft";

// The wizard preview uses the same form definition and row shape as the case form draft.
export { FORM_SECTIONS };
export type { FormField as DraftRow, FormStatus as DraftStatus } from "../cases/formDraft";

// Placeholder for the draft endpoint. The server reads the documents, joins the sources and returns one row per target with its status and citations.
// Until it exists every field is NOT_AVAILABLE. Nothing is guessed in the browser. Replace the body with a call through api/client.ts.
export async function fetchDraft(fileNames: string[]): Promise<FormField[]> {
  await new Promise((resolve) => setTimeout(resolve, 400));
  const note = fileNames.length === 0 ? "No documents were read." : "Waiting for the server to read these documents. Nothing is guessed.";
  return FORM_SECTIONS.flatMap((section) => section.fields).map((field) => ({
    target: field.target,
    value: null,
    status: "NOT_AVAILABLE",
    evidence_refs: [],
    confidence: null,
    needs_legal_review: true,
    review_notes: note,
  }));
}
