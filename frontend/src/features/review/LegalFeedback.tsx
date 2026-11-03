import { useState } from "react";
import { Link } from "react-router-dom";

import { Chip } from "../../components/Stamp";
import { useRole } from "../../lib/role";
import CaseNotes from "./CaseNotes";
import { formatStamp } from "./format";
import { KIND_LABEL, STATUS_LABEL, useCaseProposals } from "./useProposals";

// For operations, on every tab: what the attorney decided on this case, with the reason and any note, newest first.
// It opens by itself while something was rejected or sent back and has not been replaced by a newer proposal of the same kind.
export default function LegalFeedback({ caseId }: { caseId: string }) {
  const { role } = useRole();
  const proposals = useCaseProposals(caseId);
  const [shown, setShown] = useState<boolean | null>(null);
  if (role !== "paralegal" || !proposals.data) return null;
  const list = proposals.data;
  const decided = list.filter((item) => item.reviewed_by).sort((a, b) => (b.reviewed_at ?? "").localeCompare(a.reviewed_at ?? ""));
  if (decided.length === 0) return null;
  const rework = decided.filter(
    (item) => (item.status === "SENT_BACK" || item.status === "REJECTED") && !list.some((other) => other.kind === item.kind && other.proposal_id > item.proposal_id),
  );
  const open = shown ?? rework.length > 0;
  const latest = decided[0];

  return (
    <div className="mt-2 rounded-xl border border-[var(--line)] bg-[var(--soft)] text-sm" role="region" aria-label="Legal feedback">
      <button type="button" aria-expanded={open} onClick={() => setShown(!open)} className="flex w-full flex-wrap items-center gap-2 px-3 py-1.5 text-left">
        <b>Legal feedback</b>
        <span className="text-[var(--muted)]">
          {decided.length} decision{decided.length === 1 ? "" : "s"}
          {rework.length > 0 && `, ${rework.length} need${rework.length === 1 ? "s" : ""} your rework`}
        </span>
        {!open && <Chip tone={STATUS_LABEL[latest.status].tone}>{`${KIND_LABEL[latest.kind]}: ${STATUS_LABEL[latest.status].text}`}</Chip>}
        <span className="ml-auto text-xs text-[var(--muted)]">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="max-h-[min(14rem,30vh)] space-y-2 overflow-y-auto overscroll-contain border-t border-[var(--line)] p-3">
          {decided.map((item) => (
            <div key={item.proposal_id}>
              <b>{KIND_LABEL[item.kind]}</b> <span className="font-mono">{item.proposal_id}</span>{" "}
              <Chip tone={STATUS_LABEL[item.status].tone}>{STATUS_LABEL[item.status].text}</Chip>{" "}
              <span className="text-[var(--muted)]">
                by {item.reviewed_by}
                {item.reviewed_at && `, ${formatStamp(item.reviewed_at)}`}
              </span>{" "}
              <Link to={`/review/${item.proposal_id}`} className="underline">
                Open
              </Link>
              {item.review_reason && <p className="mt-1">Reason: {item.review_reason}</p>}
              <CaseNotes caseId={caseId} proposalId={item.proposal_id} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
