import { Fragment } from "react";
import { useNavigate } from "react-router-dom";

import Icon from "../../components/Icon";
import { Chip, SourceRef } from "../../components/Stamp";
import { DUE_LABEL, DUE_TONE, formatLong, humanStatus, relativeDays, type Due, type HomeRow } from "./useHome";

type Props = {
  rows: HomeRow[];
  current: string;
  open: Record<string, boolean>;
  onCurrent: (caseId: string) => void;
  onToggle: (caseId: string) => void;
  empty?: string;
};

function DueCell({ due }: { due: Due | null }) {
  if (!due) return <span className="text-sm text-[var(--muted)]" aria-label="No due date">-</span>;
  return (
    <>
      <b className="block whitespace-nowrap">{formatLong(due.date)}</b>
      <span className={`block text-xs ${due.state === "OVERDUE" ? "font-bold text-[var(--bad)]" : "text-[var(--muted)]"}`}>{relativeDays(due.days_left)}</span>
      <Chip tone={DUE_TONE[due.state]}>{DUE_LABEL[due.state]}</Chip>
    </>
  );
}

function Details({ row }: { row: HomeRow }) {
  const due = row.due;
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <div>
        <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-[var(--muted)]">Sources</h4>
        {row.refs.length === 0 ? <p className="text-sm text-[var(--muted)]">No events or proposals yet.</p> : row.refs.map((ref) => <SourceRef key={ref}>{ref}</SourceRef>)}
      </div>
      <div>
        <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-[var(--muted)]">Case</h4>
        <p className="flex flex-wrap items-center gap-1.5 text-sm">
          <Chip tone="muted">{humanStatus(row.workflow_status)}</Chip>
          <Chip tone="muted">{`Priority ${humanStatus(row.priority)}`}</Chip>
        </p>
        <p className="mt-1.5 text-sm text-[var(--muted)]">{`Owner ${row.ops_user}, legal reviewer ${row.legal_reviewer}.`}</p>
      </div>
      <div>
        <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-[var(--muted)]">Deadline</h4>
        {due ? (
          <p className="text-sm">
            {`Portal request ${formatLong(due.request_date)} (${due.request_event_id}) plus ${due.offset_days} days gives ${formatLong(due.date)}. Proposal only, legal approval required.`}
            {due.calendar_date && ` Calendar entry ${due.calendar_event_id} shows ${formatLong(due.calendar_date)}. It differs and never sets a deadline.`}
          </p>
        ) : (
          <p className="text-sm text-[var(--muted)]">No verified portal evidence request, so no deadline is proposed.</p>
        )}
      </div>
    </div>
  );
}

// Flat table in urgency order. The row chevron or Enter opens details, a click on the row opens the case.
export default function CaseTable({ rows, current, open, onCurrent, onToggle, empty = "No cases match these filters." }: Props) {
  const navigate = useNavigate();
  const go = (caseId: string, tab = "") => navigate(`/cases/${caseId}${tab ? `?tab=${tab}` : ""}`);

  if (rows.length === 0) return <p className="p-7 text-center text-[var(--muted)]">{empty}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0">
        <thead>
          <tr className="bg-[var(--soft)] text-left text-sm text-[var(--ink)]">
            {([["Case and client", "user"], ["Stage", "stage"], ["Reason", "flag"], ["Due", "calendar"], ["Next action", "arrow"]] as const).map(([head, icon]) => (
              <th key={head} scope="col" className="border-b border-[var(--line)] px-3.5 py-2 font-semibold first:rounded-tl-2xl last:rounded-tr-2xl">
                <Icon name={icon} className="mr-1.5 inline h-3.5 w-3.5 align-[-2px]" />
                {head}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isOpen = !!open[row.case_id];
            const isCurrent = current === row.case_id;
            return (
              <Fragment key={row.case_id}>
                <tr
                  id={`row-${row.case_id}`}
                  data-row={row.case_id}
                  tabIndex={isCurrent ? 0 : -1}
                  onClick={() => {
                    onCurrent(row.case_id);
                    go(row.case_id);
                  }}
                  onFocus={() => onCurrent(row.case_id)}
                  className={`cursor-pointer hover:bg-[#f6f8fc] ${isCurrent ? "bg-[#e3ecfa] shadow-[inset_4px_0_0_#2f6fe0]" : ""}`}
                >
                  <td className="border-b border-[var(--line)] px-3.5 py-3 align-top">
                    <div className="flex items-start gap-1">
                      <button
                        type="button"
                        aria-expanded={isOpen}
                        aria-label={`Details for ${row.case_id} ${row.name}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          onToggle(row.case_id);
                        }}
                        className="grid h-[22px] w-[22px] shrink-0 place-items-center rounded-md text-[var(--muted)] hover:bg-[var(--soft)]"
                      >
                        <span aria-hidden className={`transition-transform ${isOpen ? "rotate-90" : ""}`}>
                          &#9656;
                        </span>
                      </button>
                      <div>
                        <b>{row.name}</b>
                        <span className="block text-xs leading-snug text-[var(--muted)]">
                          <span className="font-mono font-semibold text-[var(--ink)]">{row.case_id}</span>
                          {` · ${row.ops_user}, legal reviewer ${row.legal_reviewer}`}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td className="border-b border-[var(--line)] px-3.5 py-3 align-top text-sm">{row.stage}</td>
                  <td className="border-b border-[var(--line)] px-3.5 py-3 align-top">
                    <Chip tone={row.reason.tone}>{row.reason.label}</Chip>
                    <span className="mt-1 block text-sm leading-snug text-[var(--muted)]">{row.reason.text}</span>
                  </td>
                  <td className="border-b border-[var(--line)] px-3.5 py-3 align-top">
                    <DueCell due={row.due} />
                  </td>
                  <td className="border-b border-[var(--line)] px-3.5 py-3 align-top">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        go(row.case_id, row.next_action === "Open documents" ? "documents" : "");
                      }}
                      className="whitespace-nowrap rounded-lg border border-[var(--accent)] bg-[var(--accent)] px-2.5 py-1 text-sm font-semibold text-white"
                    >
                      {row.next_action}
                    </button>
                  </td>
                </tr>
                {isOpen && (
                  <tr>
                    <td colSpan={5} className="border-b border-[var(--line)] bg-[#fafbfe] py-2.5 pb-3 pl-9 pr-3">
                      <Details row={row} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
