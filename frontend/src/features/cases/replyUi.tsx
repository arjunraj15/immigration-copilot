// Small pieces shared by the operations and attorney Client reply steps, the proposal page and the Communication tab.
import { Chip, type Tone } from "../../components/Stamp";
import { usDateTime } from "../../lib/dates";
import Citation from "./Citation";
import type { DraftStatus, Intent, ReplyQuestion, Triage } from "./useReplyDraft";

export const DRAFT_STATUS: Record<DraftStatus, { text: string; tone: Tone }> = {
  DRAFT: { text: "Draft", tone: "muted" },
  PENDING_LEGAL_REVIEW: { text: "Pending legal review", tone: "warn" },
  APPROVED: { text: "Approved", tone: "ok" },
  REJECTED: { text: "Rejected", tone: "bad" },
};

const INTENT_LABEL: Record<Intent, string> = {
  STATUS_QUESTION: "Status question",
  DOCUMENT_QUESTION: "Document question",
  OUTCOME_PREDICTION: "Outcome prediction",
  LEGAL_ADVICE: "Legal advice",
  OTHER_CLIENT_DATA: "Another client",
  OTHER: "Other question",
  NONE: "No question",
};
const REFUSED: Intent[] = ["OUTCOME_PREDICTION", "LEGAL_ADVICE", "OTHER_CLIENT_DATA"];

const CHANNEL: Record<string, string> = { WHATSAPP: "WhatsApp", EMAIL: "Email" };

export function DraftBanner() {
  return (
    <p className="mb-2 flex flex-wrap items-center gap-2">
      <Chip tone="bad">DRAFT, NOT SENT</Chip>
      <small className="text-[var(--muted)]">Nothing is sent to the client from this app.</small>
    </p>
  );
}

export function CitedIds({ ids }: { ids: string[] }) {
  if (ids.length === 0) return null;
  return (
    <p className="mt-2 text-sm">
      <span className="mr-2 text-[var(--muted)]">Cited sources</span>
      {ids.map((id) => (
        <Citation key={id} source={id} showTitle={false} />
      ))}
    </p>
  );
}

// The client's latest message with its channel, time and citation.
export function QuestionCard({ question }: { question: ReplyQuestion }) {
  return (
    <section className="mb-3 rounded-xl border border-[var(--line)] p-3.5" aria-label="Latest client question">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <b>Latest client question</b>
        <Chip tone="muted">{CHANNEL[question.channel] ?? question.channel}</Chip>
        <small className="text-[var(--muted)]">{usDateTime(question.occurred_at)}</small>
        <span className="ml-auto">
          <Citation source={question.source_id} showTitle={false} />
        </span>
      </div>
      <p className="whitespace-pre-wrap">{question.text}</p>
    </section>
  );
}

// What the triage found, as pills and one line of reason. The model only labels the question, the reply is a template.
export function TriagePills({ triage, reason }: { triage: Triage; reason: string | null }) {
  const refused = REFUSED.includes(triage.intent);
  return (
    <div className="mb-3">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={refused ? "bad" : "ai"}>{`Intent: ${INTENT_LABEL[triage.intent]}`}</Chip>
        {triage.intent !== "NONE" && (
          <Chip tone={triage.supported ? "ok" : "warn"}>{triage.supported ? "Supported by the data" : "Cannot be answered from the data"}</Chip>
        )}
        {triage.injection_flag && <Chip tone="bad">Instructions in the message were flagged</Chip>}
        <small className="text-[var(--muted)]">{triage.origin === "MODEL" ? "Question read by AI and checked by rules" : "Question read by keyword rules"}</small>
      </div>
      {reason && <p className="mt-2 text-xs font-semibold text-[var(--warn)]">&#9873; {reason}</p>}
    </div>
  );
}
