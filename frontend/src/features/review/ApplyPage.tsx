import { Link } from "react-router-dom";

import Breadcrumb from "../../components/Breadcrumb";
import { Chip, PrimaryButton } from "../../components/Stamp";
import { useRole } from "../../lib/role";
import { formatStamp } from "./format";
import { KIND_LABEL, STAGE_LABEL, STATUS_LABEL, useCommit, useProposals, type Proposal } from "./useProposals";

function effect(item: Proposal): string {
  const value = item.value as Record<string, string>;
  if (item.kind === "STAGE_CHANGE") return `Moves the case from ${STAGE_LABEL[value.from_stage]} to ${STAGE_LABEL[value.to_stage]}.`;
  if (item.kind === "DEADLINE_ACTIVATE") return `Activates the deadline ${value.due_date} in this app. Nothing is filed.`;
  if (item.kind === "PACKET_APPROVE") return "Marks the evidence index approved. Nothing is filed.";
  if (item.kind === "MESSAGE_APPROVE") return "Marks the message text approved. Nothing is sent.";
  return "Releases the approved form draft for download. Nothing is filed.";
}

function Row({ item }: { item: Proposal }) {
  const commit = useCommit(item.proposal_id);
  const status = STATUS_LABEL[item.status];
  return (
    <li className="rounded-xl border border-[var(--line)] p-3.5">
      <p>
        <b>{KIND_LABEL[item.kind]}</b> <span className="font-mono">{item.proposal_id}</span> <Chip tone={status.tone}>{status.text}</Chip>
      </p>
      <p className="text-sm">
        <Link to={`/cases/${item.case_id}`} className="font-semibold underline">
          {item.client_name ?? item.case_id}
        </Link>{" "}
        approved by {item.reviewed_by}, {item.reviewed_at && formatStamp(item.reviewed_at)}
      </p>
      <p className="mt-1 text-sm text-[var(--muted)]">{effect(item)}</p>
      {item.status === "APPROVED" ? (
        <div className="mt-2">
          <PrimaryButton disabled={commit.isPending} onClick={() => commit.mutate()}>
            {commit.isPending ? "Applying..." : "Apply"}
          </PrimaryButton>
        </div>
      ) : (
        <p className="mt-1 text-sm">Applied by {item.committed_by}.</p>
      )}
      {commit.isError && (
        <p className="mt-2 text-[var(--bad)]" role="alert">
          {commit.error.message}
        </p>
      )}
    </li>
  );
}

// Operations applies what the attorney approved. Applying is separate from approving, and the server refuses anything not approved.
export default function ApplyPage() {
  const { role } = useRole();
  const proposals = useProposals();
  const ready = (proposals.data ?? []).filter((item) => item.status === "APPROVED");
  const done = (proposals.data ?? []).filter((item) => item.status === "COMMITTED").slice(0, 10);
  return (
    <main className="p-4">
      <section className="rounded-2xl bg-[var(--surface)] p-4" aria-label="Apply approved changes">
        <Breadcrumb items={[{ label: "Review", to: "/review" }, { label: "Apply" }]} />
        <h1 className="text-2xl font-bold">Apply approved changes</h1>
        <p className="mb-3 text-[var(--muted)]">Approved by legal and waiting for you. Nothing is filed or sent from this app.</p>
        {role !== "paralegal" && <p className="mb-3 rounded-xl bg-[var(--soft)] px-3 py-2 text-sm">Only the assigned operations user can apply a change.</p>}
        {proposals.isError && (
          <p className="text-[var(--bad)]" role="alert">
            {proposals.error.message}
          </p>
        )}
        {proposals.data && ready.length === 0 && <p className="rounded-xl border border-dashed border-[var(--line)] p-6 text-center text-[var(--muted)]">Nothing is waiting to be applied.</p>}
        <ul className="m-0 grid list-none gap-2 p-0">
          {ready.map((item) => (
            <Row key={item.proposal_id} item={item} />
          ))}
        </ul>
        {done.length > 0 && <h2 className="mb-2 mt-5 font-bold">Recently applied</h2>}
        <ul className="m-0 grid list-none gap-2 p-0">
          {done.map((item) => (
            <Row key={item.proposal_id} item={item} />
          ))}
        </ul>
      </section>
    </main>
  );
}
