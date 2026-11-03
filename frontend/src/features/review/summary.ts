import { formatLongDate } from "./format";
import { STAGE_LABEL, type FormValue, type PacketValue, type Proposal } from "./useProposals";

export type Flag = { text: string; tone: "warn" | "ai" };

// One line saying what is proposed, read from the stored value. Display only.
export function summarize(proposal: Proposal): string {
  const value = proposal.value;
  switch (proposal.kind) {
    case "DEADLINE_ACTIVATE": {
      const due = typeof value.due_date === "string" ? formatLongDate(value.due_date) : null;
      return due ? `Activate response deadline ${due}` : "Activate a response deadline";
    }
    case "FORM_EXPORT": {
      const form = value as unknown as FormValue;
      const held = (form.fields ?? []).filter((field) => field.status === "HELD_FOR_REVIEW").length;
      return held > 0 ? `Export the form draft, ${held} fields held for review` : "Export the form draft";
    }
    case "PACKET_APPROVE": {
      const packet = value as unknown as PacketValue;
      return `Approve packet, ${packet.usable_count ?? 0} usable documents`;
    }
    case "MESSAGE_APPROVE":
      return "Approve client message text (DRAFT, NOT SENT)";
    case "STAGE_CHANGE": {
      const from = String(value.from_stage ?? "");
      const to = String(value.to_stage ?? "");
      return `Move stage from ${STAGE_LABEL[from] ?? from} to ${STAGE_LABEL[to] ?? to}`;
    }
  }
}

// Care flags that follow from the stored value. Nothing is guessed.
export function flagsFor(proposal: Proposal): Flag[] {
  const flags: Flag[] = [];
  if (proposal.kind === "PACKET_APPROVE") {
    const packet = proposal.value as unknown as PacketValue;
    if (packet.complete === false) flags.push({ text: "Missing or unusable document", tone: "warn" });
  }
  if (proposal.kind === "FORM_EXPORT") {
    const form = proposal.value as unknown as FormValue;
    if ((form.fields ?? []).some((field) => field.status === "HELD_FOR_REVIEW")) flags.push({ text: "Field held for review", tone: "warn" });
  }
  if (proposal.kind === "MESSAGE_APPROVE") flags.push({ text: "DRAFT, NOT SENT", tone: "ai" });
  return flags;
}
