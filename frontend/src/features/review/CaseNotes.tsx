import { formatLongDate, formatStamp } from "./format";
import { useCaseNotes } from "./useProposals";

// The attorney's notes on a case: a question or a different date. A date here is only a suggestion, it never changes the deadline.
export default function CaseNotes({ caseId, proposalId }: { caseId: string; proposalId?: string }) {
  const notes = useCaseNotes(caseId);
  const shown = (notes.data ?? []).filter((note) => !proposalId || note.proposal_id === proposalId);
  if (shown.length === 0) return null;
  return (
    <div className="mb-4 space-y-2" aria-label="Legal notes">
      {shown.map((note) => (
        <div key={note.created_at + note.body} className="rounded-xl border border-[var(--warn)] bg-[var(--soft)] p-3 text-sm" role="note">
          <b>{note.kind === "QUESTION" ? "Question from" : "Different date suggested by"} {note.author}</b>{" "}
          <span className="text-[var(--muted)]">{formatStamp(note.created_at)}</span>
          {note.suggested_date && <p className="mt-1">Suggested date {formatLongDate(note.suggested_date)}. The deadline itself is unchanged.</p>}
          <p className="mt-1 whitespace-pre-wrap">{note.body}</p>
        </div>
      ))}
    </div>
  );
}
