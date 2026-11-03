import { Chip } from "../../components/Stamp";
import { OUTCOME_TONE, outcomeWord } from "../documents/readWithAi";
import Citation from "./Citation";
import type { CaseDocument, ChecklistItem } from "./useCaseDocuments";

export const QUARANTINE_TEXT = "This file belongs to a different client. Its details are hidden.";

// Short words for the reason code the server saved on a file. The server decides the code, this only words it.
const CODE_WORD: Record<string, string> = {
  DUPLICATE: "Duplicate",
  WRONG_CLIENT: "Wrong client",
  MIXED_CLIENTS: "Mixed clients",
  UNREADABLE: "Unreadable",
  BLANK: "Blank",
  ROTATED: "Rotated scan",
  SUPERSEDED: "Older version",
  EXPIRED: "Expired",
  STALE: "Stale",
  NEEDS_TRANSLATION: "Needs translation",
  PAY_PERIOD: "Wrong pay period",
  NO_REFERENCE: "No reference number",
  SCANNED_PAGE: "Scanned page",
};

export function OutcomePill({ outcome }: { outcome: string }) {
  return <Chip tone={OUTCOME_TONE[outcome] ?? "muted"}>{outcomeWord(outcome)}</Chip>;
}

// A file of another client is described only as belonging to a different client. Pages are numbers only.
export function reasonText(doc: CaseDocument): string | null {
  if (doc.outcome !== "QUARANTINED") return doc.outcome_reason;
  if (doc.reason_code !== "MIXED_CLIENTS" || doc.foreign_pages.length === 0) return QUARANTINE_TEXT;
  const one = doc.foreign_pages.length === 1;
  return `${one ? "Page" : "Pages"} ${doc.foreign_pages.join(", ")} ${one ? "belongs" : "belong"} to a different client. Its details are hidden.`;
}

// Reason chips and the source id chips of one file. The original of a duplicate is cited too.
export function ReasonChips({ doc }: { doc: CaseDocument }) {
  const word = doc.reason_code ? CODE_WORD[doc.reason_code] : null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {word && <Chip tone="muted">{word}</Chip>}
      {doc.injection && <Chip tone="bad">Suspicious text</Chip>}
      <Citation source={doc.upload_id} showTitle={false} />
      {doc.duplicate_of && <Citation source={doc.duplicate_of} showTitle={false} />}
    </span>
  );
}

// Where the pages of a file were read from. Never set for a file of another client.
export function scannedNote(doc: CaseDocument): string | null {
  return doc.pages.some((page) => page.text_source === "IMAGE") ? "Scanned page read from its image" : null;
}

const CELL = { SATISFIED: "bg-[var(--ok-soft)] text-[var(--ok)]", MISSING: "bg-[var(--bad-soft)] text-[var(--bad)]", NOT_USABLE: "bg-[var(--warn-soft)] text-[var(--warn)]" };
const CELL_WORD = { SATISFIED: "✓ Satisfied", MISSING: "✕ Missing", NOT_USABLE: "! Not usable" };

// The six required categories, each with a status word and the reasons from the server.
export function ChecklistCells({ items }: { items: ChecklistItem[] }) {
  return (
    <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6" role="list" aria-label="Required documents">
      {items.map((item) => (
        <div key={item.category} role="listitem" className={`rounded-xl p-2 text-sm ${CELL[item.status]}`}>
          <b className="block">{item.label}</b>
          <span className="block">{CELL_WORD[item.status]}</span>
          {item.reasons.map((reason) => (
            <span key={reason.upload_id} className="mt-1 block text-xs text-[var(--ink)]">
              <Citation source={reason.upload_id} showTitle={false} />
              {reason.outcome === "QUARANTINED" ? QUARANTINE_TEXT : reason.reason}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}
