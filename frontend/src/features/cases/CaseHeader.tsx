import { useNavigate } from "react-router-dom";

import Breadcrumb, { type Crumb } from "../../components/Breadcrumb";
import { useRole } from "../../lib/role";
import Icon, { type IconName } from "../../components/Icon";
import { SourceRef } from "../../components/Stamp";
import CaseStage from "./CaseStage";
import ImportData from "./ImportData";
import { useCaseInfo, useDeleteCase } from "./useCases";

export type CaseTab = "steps" | "documents" | "timeline" | "activity" | "communication";

const TABS: { value: CaseTab; label: string; icon: IconName }[] = [
  { value: "steps", icon: "steps", label: "Steps" },
  { value: "documents", icon: "documents", label: "Documents" },
  { value: "timeline", icon: "timeline", label: "Timeline" },
  { value: "activity", icon: "activity", label: "Activity" },
  { value: "communication", icon: "message", label: "Communication" },
];

type Props = { caseId: string; tab: CaseTab; onTab: (tab: CaseTab) => void; crumbs: Crumb[]; queueOpen: boolean; onToggleQueue: () => void };

type Part = { label: string; value: string; bold?: boolean };

// One row. The breadcrumb names the client and the tab, the case details follow it and the tabs sit on the right.
export default function CaseHeader({ caseId, tab, onTab, crumbs, queueOpen, onToggleQueue }: Props) {
  const { role, actor } = useRole();
  const { data: info, error } = useCaseInfo(caseId);
  const remove = useDeleteCase(caseId);
  const navigate = useNavigate();
  // Only the OPS user and the legal reviewer assigned to the case may delete it. The server checks this again.
  const canDelete = !!info && (actor === info.ops_user || actor === info.legal_reviewer);
  const deleteCase = () => {
    if (!window.confirm(`Delete case ${caseId}? It disappears from every list and page. The audit trail keeps a record of it.`)) return;
    remove.mutate(undefined, { onSuccess: () => navigate("/") });
  };
  const portal = info?.portal_status ?? null;
  const parts: Part[] = !info
    ? []
    : role === "paralegal"
      ? [
          { label: "", value: info.case_id },
          { label: "", value: info.archetype },
          { label: "Legal", value: info.legal_reviewer, bold: true },
        ]
      : [
          { label: "", value: info.case_id },
          { label: "Prepared by", value: info.ops_user, bold: true },
          ...(portal?.label ? [{ label: "Portal status", value: portal.label, bold: true }] : []),
        ];

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
      <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-0.5">
        <button
          type="button"
          onClick={onToggleQueue}
          aria-pressed={queueOpen}
          title={queueOpen ? "Hide the case list" : "Show the case list"}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line)] px-2 py-1 text-xs font-semibold text-[var(--muted)]"
        >
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
            <path d="M4 6h16M4 12h16M4 18h10" />
          </svg>
          {queueOpen ? "Hide cases" : "Cases"}
        </button>
        <h1 className="sr-only">{info?.name ?? caseId}</h1>
        <Breadcrumb items={crumbs} className="text-sm" />
        {error && (
          <p className="text-sm text-[var(--bad)]" role="alert">
            {error.message}
          </p>
        )}
        <p className="text-sm text-[var(--muted)]">
          {parts.map((part) => (
            <span key={part.value} className="mr-3">
              {part.label && `${part.label} `}
              {part.bold ? <b className="text-[var(--ink)]">{part.value}</b> : part.value}
            </span>
          ))}
          {role === "attorney" && portal && <SourceRef>{portal.event_id}</SourceRef>}
        </p>
        {remove.error && (
          <p className="text-sm text-[var(--bad)]" role="alert">
            {remove.error.message}
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <CaseStage caseId={caseId} />
        <div className="flex max-w-full flex-wrap gap-0.5 rounded-xl bg-[var(--soft)] p-1" role="tablist">
          {/* The Communication tab is hidden for now. Calls and messages show on the Timeline tab. */}
          {TABS.filter((item) => item.value !== "communication").map((item) => (
            <button
              key={item.value}
              type="button"
              role="tab"
              aria-selected={tab === item.value}
              onClick={() => onTab(item.value)}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1 text-sm ${
                tab === item.value ? "bg-[var(--surface)] font-semibold shadow-sm" : "text-[var(--muted)]"
              }`}
            >
              <Icon name={item.icon} />
              {item.label}
            </button>
          ))}
        </div>
        {canDelete && <ImportData caseId={caseId} />}
        {canDelete && (
          <button
            type="button"
            onClick={deleteCase}
            disabled={remove.isPending}
            title="Delete this case. It disappears from every list."
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--bad)] px-2.5 py-1 text-sm font-semibold text-[var(--bad)] hover:bg-[var(--bad-soft)]"
          >
            <Icon name="trash" />
            {remove.isPending ? "Deleting..." : "Delete"}
          </button>
        )}
      </div>
    </div>
  );
}
