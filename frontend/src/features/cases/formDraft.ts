import type { ProfileField } from "./useCases";

// Row shape and statuses from 13_synthetic_form_template.json (field_output_keys and permitted_statuses).
export type FormStatus = "PROPOSED" | "HELD_FOR_REVIEW" | "NOT_AVAILABLE";

export type FormField = {
  target: string;
  value: string | null;
  status: FormStatus;
  evidence_refs: string[];
  confidence: number | null;
  needs_legal_review: boolean;
  review_notes: string;
};

// A row that waits for a document the rules require. The server starts every such note with "Needs a document".
export const needsRequiredDocument = (row: { status: string; review_notes: string }): boolean =>
  row.status === "NOT_AVAILABLE" && row.review_notes.startsWith("Needs a document");

// The name of that document, such as Passport, from "Needs a document: Passport."
export const requiredDocumentLabel = (row: { review_notes: string }): string | null => /^Needs a document: ([^.]+)\./.exec(row.review_notes)?.[1] ?? null;

export const FORM_ID = "SYN-WORK-RENEWAL-DRAFT-V2";

// Sections, labels and order from 13_synthetic_form_template.json. date marks a value shown as MM/DD/YYYY.
export const FORM_SECTIONS: { title: string; fields: { target: string; label: string; date?: boolean }[] }[] = [
  {
    title: "Applicant details",
    fields: [
      { target: "applicant.legal_name", label: "Legal name" },
      { target: "applicant.date_of_birth", label: "Date of birth", date: true },
      { target: "applicant.passport_number", label: "Passport number" },
      { target: "applicant.passport_expiration", label: "Passport expiration", date: true },
      { target: "applicant.mailing_address", label: "Mailing address" },
    ],
  },
  { title: "Recent travel", fields: [{ target: "travel.last_entry", label: "Last entry", date: true }] },
  {
    title: "Employment details",
    fields: [
      { target: "employment.organization", label: "Employer" },
      { target: "employment.start_date", label: "Employment start", date: true },
    ],
  },
  { title: "Prior case reference", fields: [{ target: "case.prior_receipt_reference", label: "Prior receipt reference" }] },
];

// Profile field behind each target, from 08_form_field_map.json. The other source candidates are documents and events.
const PROFILE_FIELD: Record<string, string> = {
  "applicant.legal_name": "full_name",
  "applicant.date_of_birth": "date_of_birth",
  "applicant.mailing_address": "mailing_address",
  "travel.last_entry": "last_entry_date",
  "employment.organization": "employer_name",
  "employment.start_date": "employment_start_date",
  "case.prior_receipt_reference": "prior_receipt_number",
};

// Placeholder until the server returns the draft. It only has the verified profile, so a value is proposed with a note that no
// document has checked it. HELD_FOR_REVIEW needs the server to compare sources, so it never comes from here.
// Replace with a call through api/client.ts that returns FormField rows.
export function rowsFromProfile(profile: ProfileField[]): FormField[] {
  const byName = new Map(profile.map((item) => [item.field_name, item]));
  return FORM_SECTIONS.flatMap((section) => section.fields).map(({ target }) => {
    const item = byName.get(PROFILE_FIELD[target] ?? "");
    if (!item) {
      return {
        target,
        value: null,
        status: "NOT_AVAILABLE",
        evidence_refs: [],
        confidence: null,
        needs_legal_review: false,
        review_notes: "Needs the document to be read. Nothing is guessed.",
      };
    }
    return {
      target,
      value: item.verified_value,
      status: "PROPOSED",
      evidence_refs: [item.source_id],
      confidence: null,
      needs_legal_review: false,
      review_notes: "From the profile, checked earlier and possibly out of date. No document has checked it yet.",
    };
  });
}

// Output file from 18_submission_schema.json. The release status stays pending until an attorney approves the export.
export function buildDraftJson(caseId: string, fields: FormField[], formId: string = FORM_ID) {
  return { case_id: caseId, form_id: formId || FORM_ID, draft: true, fields, release_status: "PENDING_LEGAL_REVIEW_ONLY" };
}

export function downloadJson(fileName: string, data: unknown): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}
