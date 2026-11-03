import Icon from "../../components/Icon";
import Breadcrumb from "../../components/Breadcrumb";
import { Fragment, useState } from "react";
import { Link } from "react-router-dom";

import { Chip, SourceRef } from "../../components/Stamp";
import { useRole } from "../../lib/role";
import DecisionPanel from "./DecisionPanel";
import { formatStamp } from "./format";
import { flagsFor, summarize } from "./summary";
import { KIND_LABEL, STATUS_LABEL, useProposals, type Proposal, type ProposalStatus } from "./useProposals";

type Filter = ProposalStatus | "ALL";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "PENDING_LEGAL_REVIEW", label: "Waiting for your decision" },
  { key: "APPROVED", label: "Approved" },
  { key: "SENT_BACK", label: "Sent back" },
  { key: "REJECTED", label: "Rejected" },
  { key: "COMMITTED", label: "Committed" },
  { key: "ALL", label: "All" },
];

const CELL = "px-3 py-2.5 text-left align-top";

// Proposals for the acting user. A legal reviewer decides here. Operations sees the same list read only.
export default function ReviewPage() {
  const { role } = useRole();
  const proposals = useProposals();
  const [filter, setFilter] = useState<Filter>("PENDING_LEGAL_REVIEW");
  const [oldestFirst, setOldestFirst] = useState(true);
  const [openId, setOpenId] = useState<string | null>(null);
  const all = proposals.data ?? [];
  const count = (key: Filter) => (key === "ALL" ? all.length : all.filter((item) => item.status === key).length);
  const shown = (filter === "ALL" ? [...all] : all.filter((item) => item.status === filter)).sort(
    (a, b) => (oldestFirst ? 1 : -1) * a.proposed_at.localeCompare(b.proposed_at),
  );
  const readOnly = role !== "attorney";
  const waiting = count("PENDING_LEGAL_REVIEW");
  const approved = count("APPROVED");

  return (
    <main className="p-4">
      <section className="rounded-2xl bg-[var(--surface)] p-4" aria-label="Review queue">
        <Breadcrumb items={[{ label: "Review" }]} />
        <h1 className="text-2xl font-bold">Review</h1>
        <p className="mb-3 text-[var(--muted)]">Proposals that need a legal decision. Nothing is filed or sent from this app.</p>
        <div
          className={`mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl px-3 py-2 font-semibold ${
            !readOnly && waiting > 0 ? "bg-[var(--warn-soft)] text-[var(--warn)]" : "bg-[var(--soft)] text-[var(--muted)]"
          }`}
          role="status"
        >
          {readOnly ? (
            <>
              <span>Read only for operations. {waiting} waiting on legal.</span>
              {approved > 0 && (
                <Link to="/review/apply" className="underline">
                  Apply {approved} approved change{approved > 1 ? "s" : ""}
                </Link>
              )}
            </>
          ) : waiting > 0 ? (
            <>
              <b className="text-lg">{waiting}</b>
              <span>{waiting > 1 ? "proposals need" : "proposal needs"} your decision. Oldest first.</span>
            </>
          ) : (
            <span>No proposals need your decision.</span>
          )}
        </div>
        <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Filter by status">
          {FILTERS.map((item) => (
            <button
              key={item.key}
              type="button"
              aria-pressed={filter === item.key}
              onClick={() => {
                setFilter(item.key);
                setOpenId(null);
              }}
              className={`rounded-full border px-3 py-1 text-sm font-semibold ${
                filter === item.key ? "border-[var(--accent)] bg-[var(--accent)] text-white" : "border-[var(--line)] bg-[var(--surface)]"
              }`}
            >
              {item.label} ({count(item.key)})
            </button>
          ))}
        </div>
        {proposals.isPending && <p className="text-[var(--muted)]">Loading proposals...</p>}
        {proposals.isError && (
          <p className="text-[var(--bad)]" role="alert">
            {proposals.error.message}
          </p>
        )}
        {proposals.data && shown.length === 0 && (
          <p className="rounded-xl border border-dashed border-[var(--line)] p-6 text-center text-[var(--muted)]">
            {filter === "PENDING_LEGAL_REVIEW" ? "Nothing is waiting for a decision." : "No proposals match this filter."}
          </p>
        )}
        {shown.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[var(--ink)]">
                <tr>
                  {([["Proposal", "review"], ["Case", "cases"], ["Kind", "tag"], ["What is proposed", "documents"]] as const).map(([head, icon]) => (
                    <th key={head} className={`${CELL} font-semibold`}>
                      <Icon name={icon} className="mr-1.5 inline h-3.5 w-3.5 align-[-2px]" />
                      {head}
                    </th>
                  ))}
                  <th className={`${CELL} font-semibold`} aria-sort={oldestFirst ? "ascending" : "descending"}>
                    <button type="button" onClick={() => setOldestFirst(!oldestFirst)} aria-label="Sort by proposed time" className="font-semibold">
                      <Icon name="user" className="mr-1.5 inline h-3.5 w-3.5 align-[-2px]" />
                      Proposed {oldestFirst ? "(oldest first)" : "(newest first)"}
                    </button>
                  </th>
                  <th className={`${CELL} font-semibold`}>
                    <Icon name="check" className="mr-1.5 inline h-3.5 w-3.5 align-[-2px]" />
                    Status
                  </th>
                  <th className={CELL}>
                    <span className="sr-only">Action</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {shown.map((item) => (
                  <Row
                    key={item.proposal_id}
                    item={item}
                    readOnly={readOnly}
                    open={openId === item.proposal_id}
                    onToggle={() => setOpenId(openId === item.proposal_id ? null : item.proposal_id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-3 text-xs text-[var(--muted)]">Simulated approval. A decision here is recorded in the audit trail only.</p>
      </section>
    </main>
  );
}

function Row({ item, readOnly, open, onToggle }: { item: Proposal; readOnly: boolean; open: boolean; onToggle: () => void }) {
  const status = STATUS_LABEL[item.status];
  const decide = item.status === "PENDING_LEGAL_REVIEW" && !readOnly;
  const rejected = item.status === "REJECTED";
  const label = decide ? "Review" : "View";
  return (
    <Fragment>
      <tr className={`border-t border-[var(--line)] ${open ? "bg-[var(--soft)]" : ""}`}>
        <td className={`${CELL} font-mono font-semibold`}>{item.proposal_id}</td>
        <td className={CELL}>
          <Link to={`/cases/${item.case_id}`} className="font-semibold underline">
            {item.client_name ?? item.case_id}
          </Link>
          <span className="block font-mono text-xs text-[var(--muted)]">{item.case_id}</span>
        </td>
        <td className={CELL}>{KIND_LABEL[item.kind]}</td>
        <td className={CELL}>
          <span className="block">{summarize(item)}</span>
          <span className="mt-1 flex flex-wrap gap-1">
            {flagsFor(item).map((flag) => (
              <Chip key={flag.text} tone={flag.tone}>
                {flag.text}
              </Chip>
            ))}
          </span>
          {item.evidence_ids.length > 0 && (
            <span className="mt-1 block">
              {item.evidence_ids.map((id) => (
                <SourceRef key={id}>{id}</SourceRef>
              ))}
            </span>
          )}
          {item.reviewed_by && (
            <span className={`mt-1 block text-[13px] ${rejected ? "border-l-[3px] border-[var(--bad)] pl-2" : ""}`}>
              <b>
                {status.text} by {item.reviewed_by}
              </b>
              {item.reviewed_at && ` on ${formatStamp(item.reviewed_at)}`}
              {item.review_reason && <span className="block">Reason: {item.review_reason}</span>}
            </span>
          )}
        </td>
        <td className={CELL}>
          {formatStamp(item.proposed_at)}
          <span className="block text-xs text-[var(--muted)]">by {item.proposed_by}</span>
        </td>
        <td className={CELL}>
          <Chip tone={status.tone}>{status.text}</Chip>
        </td>
        <td className={`${CELL} whitespace-nowrap`}>
          <button
            type="button"
            aria-expanded={open}
            aria-label={`${label} ${item.proposal_id}`}
            onClick={onToggle}
            className={`rounded-xl px-3 py-1.5 font-semibold ${decide ? "bg-[var(--accent)] text-white" : "border border-[var(--line)]"}`}
          >
            {label}
          </button>
        </td>
      </tr>
      {open && (
        <tr className="bg-[var(--soft)]">
          <td colSpan={7} className="px-3 pb-3">
            <p className="mb-2 text-sm">
              <Link to={`/review/${item.proposal_id}`} className="font-semibold underline">
                Open the full proposal
              </Link>{" "}
              to see the whole value, add a note or send it back.
            </p>
            <DecisionPanel proposal={item} />
          </td>
        </tr>
      )}
    </Fragment>
  );
}
