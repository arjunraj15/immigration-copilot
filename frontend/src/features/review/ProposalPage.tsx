import { Link, useParams } from "react-router-dom";

import Breadcrumb from "../../components/Breadcrumb";
import { Chip, SourceRef } from "../../components/Stamp";
import { useCaseInfo } from "../cases/useCases";
import Citation from "../cases/Citation";
import CaseNotes from "./CaseNotes";
import DecisionPanel from "./DecisionPanel";
import { formatStamp } from "./format";
import FormView, { countRows } from "./FormView";
import MessageView, { type MessageValue } from "./MessageView";
import PacketView from "./PacketView";
import StageView, { type StageValue } from "./StageView";
import { KIND_LABEL, STATUS_LABEL, useProposal, type FormValue, type PacketValue, type Proposal } from "./useProposals";

// What is being decided, then the decision. A form export shows the form. Other kinds show their stored value as plain rows.
export default function ProposalPage() {
  const { proposalId = "" } = useParams();
  const proposal = useProposal(proposalId);
  return (
    <main className="p-4">
      <section className="rounded-2xl bg-[var(--surface)] p-4" aria-label="Proposal review">
        <Breadcrumb items={[{ label: "Review", to: "/review" }, { label: proposalId }]} />
        {proposal.isPending && <p className="mt-3 text-[var(--muted)]">Loading proposal...</p>}
        {proposal.isError && (
          <p className="mt-3 text-[var(--bad)]" role="alert">
            {proposal.error.message}
          </p>
        )}
        {proposal.data && <Body proposal={proposal.data} />}
      </section>
    </main>
  );
}

function Body({ proposal }: { proposal: Proposal }) {
  const info = useCaseInfo(proposal.case_id);
  const status = STATUS_LABEL[proposal.status];
  const form = proposal.kind === "FORM_EXPORT" ? (proposal.value as unknown as FormValue) : null;
  const counts = form ? countRows(form) : null;
  return (
    <div>
      <h1 className="mt-2 text-2xl font-bold">
        {KIND_LABEL[proposal.kind]} <span className="font-mono text-base">{proposal.proposal_id}</span>
      </h1>
      <p className="mb-3 text-[var(--muted)]">
        <Link to={`/cases/${proposal.case_id}`} className="font-semibold underline">
          {proposal.client_name ?? proposal.case_id}
        </Link>{" "}
        <SourceRef>{proposal.case_id}</SourceRef> Proposed by {proposal.proposed_by}, {formatStamp(proposal.proposed_at)}.{" "}
        <Chip tone={status.tone}>{status.text}</Chip>
        {info.data?.portal_status?.label && <> Portal status {info.data.portal_status.label}.</>}
      </p>
      {counts && (
        <p className="mb-3 text-sm">
          {counts.filled} fields have a value, {counts.held} held for review, {counts.missing} not available.
        </p>
      )}
      <div className="mb-4">
        {form && <FormView value={form} />}
        {proposal.kind === "MESSAGE_APPROVE" && <MessageView value={proposal.value as unknown as MessageValue} />}
        {proposal.kind === "PACKET_APPROVE" && <PacketView value={proposal.value as unknown as PacketValue} />}
        {proposal.kind === "STAGE_CHANGE" && <StageView value={proposal.value as unknown as StageValue} />}
        {!form && !["MESSAGE_APPROVE", "PACKET_APPROVE", "STAGE_CHANGE"].includes(proposal.kind) && <GenericValue value={proposal.value} />}
      </div>
      {proposal.evidence_ids.length > 0 && (
        <p className="mb-4 text-sm">
          <span className="mr-2 text-[var(--muted)]">Evidence cited</span>
          {proposal.evidence_ids.map((id) => (
            <Citation key={id} source={id} showTitle={false} />
          ))}
        </p>
      )}
      <CaseNotes caseId={proposal.case_id} proposalId={proposal.proposal_id} />
      <DecisionPanel proposal={proposal} />
    </div>
  );
}

function GenericValue({ value }: { value: Record<string, unknown> }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-xl bg-[var(--soft)] p-3 text-sm">
      {Object.entries(value).map(([key, item]) => (
        <div key={key} className="contents">
          <dt className="font-semibold">{key.replace(/_/g, " ")}</dt>
          <dd>{typeof item === "object" ? JSON.stringify(item) : String(item)}</dd>
        </div>
      ))}
    </dl>
  );
}
