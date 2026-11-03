import { useParams } from "react-router-dom";

import { Chip, PrimaryButton } from "../../../components/Stamp";
import { useCaseExceptions } from "../../review/useExceptions";
import { newKey } from "../../review/format";
import PacketView from "../../review/PacketView";
import { STATUS_LABEL, useCaseProposals, usePacket, useProposeKind, type Proposal } from "../../review/useProposals";
import StepFrame from "./StepFrame";
import { useStepKicker } from "./useSteps";

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

const LIVE = ["PENDING_LEGAL_REVIEW", "APPROVED", "COMMITTED"];

function Status({ proposal }: { proposal: Proposal }) {
  const status = STATUS_LABEL[proposal.status];
  return (
    <p className="mb-2 text-sm" role="status">
      <b className="font-mono">{proposal.proposal_id}</b> <Chip tone={status.tone}>{status.text}</Chip>
    </p>
  );
}

// The evidence index, sent to the attorney through the approval gate. The case stage lives in the case header.
export default function PacketStep() {
  const kicker = useStepKicker("packet");
  const { caseId = "" } = useParams();
  const packet = usePacket(caseId);
  const existing = useCaseProposals(caseId);
  const propose = useProposeKind(caseId);
  const exceptions = useCaseExceptions(caseId);
  const live = (kind: Proposal["kind"]) => (existing.data ?? []).find((item) => item.kind === kind && LIVE.includes(item.status));
  const sentPacket = live("PACKET_APPROVE");
  // Same rule as the server: open blocking exceptions and missing or unusable required documents hold the send.
  const holds = [
    plural((exceptions.data?.items ?? []).filter((item) => item.blocks_send).length, "open exception"),
    plural(packet.data?.missing.length ?? 0, "missing document"),
    plural(packet.data?.not_usable_labels.length ?? 0, "unusable document"),
  ].filter((text) => !text.startsWith("0 "));
  const holdReason = holds.length > 0 ? `Resolve ${holds.join(" and ")} first` : "";
  const checking = exceptions.isPending;

  return (
    <StepFrame kicker={kicker} title="Evidence packet" note="The index is built by code from the checklist. Legal approves it before it is used. Nothing is filed.">
      {packet.isPending && <p className="text-[var(--muted)]">Loading the packet...</p>}
      {packet.isError && (
        <p className="text-[var(--bad)]" role="alert">
          {packet.error.message}
        </p>
      )}
      {packet.data && (
        <>
          <PacketView value={packet.data} />
          <div className="mt-3">
            {sentPacket && <Status proposal={sentPacket} />}
            <PrimaryButton
              disabled={!!sentPacket || packet.data.usable_count === 0 || propose.isPending || checking || holdReason !== ""}
              onClick={() => propose.mutate({ kind: "PACKET_APPROVE", key: newKey() })}
            >
              Send packet for legal approval
            </PrimaryButton>
            {!sentPacket && packet.data.usable_count > 0 && holdReason && (
              <p className="mt-1 text-sm text-[var(--muted)]" role="status">
                {holdReason}
              </p>
            )}
            {packet.data.usable_count === 0 && <p className="mt-1 text-sm text-[var(--muted)]">No usable document yet, so there is nothing to approve.</p>}
          </div>
        </>
      )}
    </StepFrame>
  );
}
