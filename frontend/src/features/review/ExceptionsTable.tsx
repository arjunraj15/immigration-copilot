import { Link } from "react-router-dom";

import Icon from "../../components/Icon";
import { Chip, SourceRef, type Tone } from "../../components/Stamp";
import Citation from "../cases/Citation";
import { sourceKind } from "../cases/sourceId";
import type { ExceptionItem, Severity } from "./useExceptions";

export const TYPE_LABEL: Record<string, string> = {
  SUSPICIOUS_TEXT: "Suspicious text",
  WRONG_CLIENT: "Wrong client",
  MIXED_CLIENTS: "Mixed clients",
  UNREADABLE: "Unreadable",
  EXPIRED: "Expired passport",
  STALE: "Stale letter",
  NEEDS_TRANSLATION: "Needs translation",
  DUPLICATE: "Duplicate",
  SUPERSEDED: "Older version",
  MISSING_DOCUMENT: "Missing document",
  HUMAN_REVIEW: "Human review",
  FACT_CONFLICT: "Fact conflict",
  DEADLINE_CONFLICT: "Deadline conflict",
  OVERDUE: "Overdue",
  PROPOSAL_REJECTED: "Proposal rejected",
  PROPOSAL_PENDING: "Waiting on legal",
};
const SEVERITY: Record<Severity, { label: string; tone: Tone }> = {
  HIGH: { label: "High", tone: "bad" },
  MEDIUM: { label: "Medium", tone: "warn" },
  LOW: { label: "Low", tone: "muted" },
};
const HEADS = [["Case and client", "user"], ["Type", "tag"], ["Severity", "flag"], ["Reason", "activity"], ["Source", "documents"], ["Next action", "arrow"]] as const;
const BUTTON = "whitespace-nowrap rounded-lg border px-2.5 py-1 text-sm font-semibold";

function Source({ id }: { id: string }) {
  return sourceKind(id) === "unknown" ? <SourceRef>{id}</SourceRef> : <Citation source={id} showTitle={false} />;
}

export default function ExceptionsTable({ items }: { items: ExceptionItem[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-[var(--soft)] text-left text-sm text-[var(--ink)]">
            {HEADS.map(([title, icon]) => (
              <th key={title} scope="col" className="px-3.5 py-2.5 font-semibold">
                <Icon name={icon} className="mr-1.5 inline h-3.5 w-3.5 align-[-2px]" />
                {title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => {
            const documents = item.next_action === "Open documents";
            return (
              <tr key={`${item.case_id}-${item.type}-${index}`} className="border-t border-[var(--line)] align-top hover:bg-[var(--soft)]">
                <td className="px-3.5 py-3">
                  <Link to={`/cases/${item.case_id}`} className="font-semibold hover:underline">{item.client_name}</Link>
                  <small className="block font-mono text-[var(--muted)]">{item.case_id}</small>
                </td>
                <td className="px-3.5 py-3">
                  <Chip tone="muted">{TYPE_LABEL[item.type] ?? item.type}</Chip>
                  <small className="mt-1 block text-[var(--muted)]">{item.title}</small>
                </td>
                <td className="px-3.5 py-3">
                  <Chip tone={SEVERITY[item.severity].tone}>{SEVERITY[item.severity].label}</Chip>
                </td>
                <td className="max-w-md px-3.5 py-3">{item.reason}</td>
                <td className="px-3.5 py-3">
                  {item.source_ids.length === 0 ? <span className="text-[var(--muted)]">None</span> : item.source_ids.map((id) => <Source key={id} id={id} />)}
                </td>
                <td className="whitespace-nowrap px-3.5 py-3">
                  <Link to={`/cases/${item.case_id}${documents ? "?tab=documents" : item.type === "FACT_CONFLICT" ? "?step=exceptions" : ""}`} className={`${BUTTON} border-[var(--accent)] bg-[var(--accent)] text-white`}>
                    {item.next_action}
                  </Link>
                  {!documents && item.next_action !== "Open case" && (
                    <Link to={`/cases/${item.case_id}`} className={`${BUTTON} ml-1.5 border-[var(--line)] bg-[var(--surface)] hover:bg-[var(--soft)]`}>
                      Open case
                    </Link>
                  )}
                  {documents && (
                    <Link to={`/cases/${item.case_id}`} className={`${BUTTON} ml-1.5 border-[var(--line)] bg-[var(--surface)] hover:bg-[var(--soft)]`}>
                      Open case
                    </Link>
                  )}
                  <small className="mt-1 block text-[var(--muted)]">{item.owner_role === "LEGAL" ? "Owner: legal" : "Owner: operations"}</small>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
