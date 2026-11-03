import { Chip, type Tone } from "../../components/Stamp";
import Citation from "../cases/Citation";
import type { PacketValue } from "./useProposals";

const STATUS: Record<string, { text: string; tone: Tone }> = {
  SATISFIED: { text: "Usable", tone: "ok" },
  NOT_USABLE: { text: "Not usable", tone: "bad" },
  MISSING: { text: "Missing", tone: "muted" },
};

// The evidence index as the server built it from the checklist. Each required category lists the usable documents filed under it.
export default function PacketView({ value }: { value: PacketValue }) {
  return (
    <div>
      <div className="mb-3 rounded-xl border-2 border-dashed border-[var(--bad)] bg-[var(--bad-soft)] px-3.5 py-2.5 text-sm">
        <b className="whitespace-nowrap font-mono tracking-widest text-[var(--bad)]">DRAFT - NOT FOR FILING</b>
        <span className="ml-3">
          Evidence index {value.packet_id}. {value.usable_count} usable {value.usable_count === 1 ? "document" : "documents"}
          {value.complete ? ", every required category is covered." : `, ${value.items.filter((item) => item.status !== "SATISFIED").length} categories are not covered.`}
        </span>
      </div>
      <ul className="m-0 list-none p-0">
        {value.items.map((item) => {
          const status = STATUS[item.status];
          return (
            <li key={item.category + item.label} className="flex flex-wrap items-start gap-3 border-t border-[var(--line)] py-2.5 first:border-t-0">
              <span className="w-56 shrink-0 text-sm font-semibold">{item.label}</span>
              <div className="min-w-0 flex-1 text-sm">
                {item.documents.map((doc) => (
                  <span key={doc.upload_id} className="mr-3 inline-flex items-center gap-1.5">
                    <Citation source={doc.upload_id} showTitle={false} />
                    <span className="text-[var(--muted)]">{doc.filename}</span>
                  </span>
                ))}
                {item.status === "MISSING" && <span className="text-[var(--muted)]">Nothing received for this category.</span>}
                {item.not_usable.map((reason) => (
                  <span key={reason.upload_id} className="block text-[var(--muted)]">
                    {reason.upload_id}: {reason.reason ?? reason.outcome}
                  </span>
                ))}
              </div>
              <Chip tone={status.tone}>{status.text}</Chip>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
