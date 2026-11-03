import { Chip } from "../../components/Stamp";
import { DraftBanner } from "../cases/replyUi";

export type MessageValue = { draft_id: string; body_hash: string; kind: string; channel: "WHATSAPP" | "EMAIL"; subject: string | null; body: string };

// The exact text the legal reviewer approves. Approving only marks the text approved, nothing is sent to the client.
export default function MessageView({ value }: { value: MessageValue }) {
  return (
    <div>
      <DraftBanner />
      <p className="mb-2 flex flex-wrap items-center gap-2 text-sm">
        <Chip tone="muted">{value.channel === "EMAIL" ? "Email" : "WhatsApp"}</Chip>
        <span className="font-mono text-xs text-[var(--muted)]">{value.draft_id}</span>
      </p>
      {value.subject && <p className="mb-1 text-sm">Subject: {value.subject}</p>}
      <p className="whitespace-pre-wrap rounded-xl bg-[var(--soft)] p-3.5">{value.body}</p>
    </div>
  );
}
