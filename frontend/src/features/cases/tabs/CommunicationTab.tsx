import { useState } from "react";
import { Link } from "react-router-dom";

import Icon from "../../../components/Icon";
import { Chip, SourceRef } from "../../../components/Stamp";
import { usDate, usDateTime, usTime } from "../../../lib/dates";
import Citation from "../Citation";
import { DRAFT_STATUS } from "../replyUi";
import { useAddCommunication, useCommunications, type Communication, type CommunicationKind } from "../useCommunications";

const CHANNELS: { value: "ALL" | CommunicationKind; label: string }[] = [
  { value: "ALL", label: "All" },
  { value: "ZOOM", label: "Zoom" },
  { value: "WHATSAPP", label: "WhatsApp" },
  { value: "EMAIL", label: "Email" },
];
const DIRECTIONS = [
  { value: "ALL", label: "All" },
  { value: "CLIENT", label: "From the client" },
  { value: "DRAFT", label: "Drafts from the office" },
] as const;
type DirectionFilter = (typeof DIRECTIONS)[number]["value"];

const WHO: Record<string, string> = { CLIENT: "Client", OPERATIONS: "Operations", INTAKE_COORDINATOR: "Intake coordinator" };
const CHANNEL_LABEL: Record<CommunicationKind, string> = { ZOOM: "Zoom call notes", WHATSAPP: "WhatsApp", EMAIL: "Email" };
const FILE_NAME: Record<CommunicationKind, string> = { ZOOM: "zoom-notes.txt", WHATSAPP: "whatsapp-message.txt", EMAIL: "email-message.txt" };


// Display only. The server decides drafts, questions and claim counts.
function matchesDirection(item: Communication, filter: DirectionFilter): boolean {
  if (filter === "ALL") return true;
  return filter === "DRAFT" ? item.is_draft : !item.is_draft;
}

type Day = { label: string; threads: { id: string | null; items: Communication[] }[] };

function groupByDay(items: Communication[]): Day[] {
  const days: Day[] = [];
  for (const item of items) {
    const label = usDate(item.occurred_at);
    let day = days[days.length - 1];
    if (!day || day.label !== label) {
      day = { label, threads: [] };
      days.push(day);
    }
    const thread = day.threads.find((t) => t.id !== null && t.id === item.thread_id);
    if (thread) thread.items.push(item);
    else day.threads.push({ id: item.thread_id, items: [item] });
  }
  return days;
}

// Zoom notes, WhatsApp messages and emails of one case. They are claims until a document backs them up.
export default function CommunicationTab({ caseId }: { caseId: string }) {
  const list = useCommunications(caseId);
  const [channel, setChannel] = useState<"ALL" | CommunicationKind>("ALL");
  const [direction, setDirection] = useState<DirectionFilter>("ALL");
  const [adding, setAdding] = useState(false);
  const items = list.data ?? [];
  const intake = items.find((i) => i.role === "INTAKE_CALL");
  const thread = items.filter((i) => i.role !== "INTAKE_CALL");
  const shown = thread.filter((i) => (channel === "ALL" || i.kind === channel) && matchesDirection(i, direction));

  return (
    <div className="pt-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold">Communication</h2>
          <p className="mb-2 text-[var(--muted)]">Calls and messages are claims until a document backs them up. Replies are drafts and are never sent.</p>
        </div>
        <button
          type="button"
          onClick={() => setAdding((open) => !open)}
          className="inline-flex items-center gap-1.5 rounded-lg border-2 border-[var(--accent)] bg-[var(--surface)] px-3.5 py-1.5 text-sm font-semibold text-[var(--accent)] hover:bg-[var(--soft)]"
        >
          <Icon name="plus" />
          Add communication
        </button>
      </div>
      {adding && <AddForm caseId={caseId} onDone={() => setAdding(false)} />}
      {intake && <IntakeCall item={intake} />}
      {list.data && !intake && <p className="mb-3 text-sm text-[var(--muted)]">No intake call is recorded yet</p>}
      {list.data && (
        <div className="mb-3 flex flex-wrap gap-x-6 gap-y-2" role="group" aria-label="Filters">
          <FilterRow label="Channel" options={CHANNELS} value={channel} onChange={setChannel} count={(v) => thread.filter((i) => v === "ALL" || i.kind === v).length} />
          <FilterRow
            label="Direction"
            options={DIRECTIONS}
            value={direction}
            onChange={setDirection}
            count={(v) => thread.filter((i) => matchesDirection(i, v)).length}
          />
        </div>
      )}
      {list.isPending && <p className="py-3 text-[var(--muted)]">Loading communication...</p>}
      {list.isError && (
        <p className="py-3 text-[var(--bad)]" role="alert">
          {list.error.message}
        </p>
      )}
      {list.data && items.length === 0 && <p className="py-3 text-[var(--muted)]">No calls or messages are recorded for this case yet.</p>}
      {list.data && thread.length > 0 && shown.length === 0 && <p className="py-3 text-[var(--muted)]">Nothing matches these filters.</p>}
      <ol className="grid gap-4 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-3 sm:p-4" aria-label="Conversation">
        {groupByDay(shown).map((day) => (
          <li key={day.label} className="grid gap-2">
            <h3 className="mx-auto rounded-full bg-[var(--soft)] px-3 py-0.5 text-xs font-semibold text-[var(--muted)]">{day.label}</h3>
            {day.threads.map((thread, index) => (
              <div key={`${thread.id}-${index}`} className="grid gap-2">
                {thread.id && thread.items.length > 1 && <p className="text-center text-xs text-[var(--muted)]">Thread {thread.id}</p>}
                {thread.items.map((item) => (
                  <Bubble key={item.source_id} item={item} caseId={caseId} />
                ))}
              </div>
            ))}
          </li>
        ))}
      </ol>
    </div>
  );
}

type Option<T extends string> = { value: T; label: string };

function FilterRow<T extends string>({ label, options, value, onChange, count }: { label: string; options: readonly Option<T>[]; value: T; onChange: (v: T) => void; count: (v: T) => number }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-sm">
      <span className="text-[var(--muted)]">{label}</span>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={`rounded-full border px-2.5 py-0.5 ${value === option.value ? "border-[var(--accent)] bg-[var(--soft)] font-semibold" : "border-[var(--line)] text-[var(--muted)]"}`}
        >
          {option.label} {count(option.value)}
        </button>
      ))}
    </div>
  );
}

// The first call of the case. Everything said in it is a claim until a document backs it up.
function IntakeCall({ item }: { item: Communication }) {
  return (
    <details open className="mb-3 rounded-xl border border-[var(--accent)] bg-[var(--soft)] px-3 py-2" aria-label="Intake call">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2">
        <span className="font-bold">Intake call, starting point</span>
        <Chip tone="warn">Claim</Chip>
        <span className="text-sm text-[var(--muted)]">{usDateTime(item.occurred_at)}</span>
        {item.claim_rows.length > 0 && <span className="text-xs text-[var(--muted)]">{item.claim_rows.length} claims read</span>}
        <span className="ml-auto">
          <Citation source={item.source_id} showTitle={false} />
        </span>
      </summary>
      <p className="mt-2 text-sm text-[var(--muted)]">Everything said here is a claim until a document backs it up.</p>
      {item.body && <p className="mt-1 whitespace-pre-wrap text-sm">{item.body}</p>}
      {item.claim_rows.length > 0 && (
        <ul className="mt-2 grid gap-1.5 text-sm sm:grid-cols-2" aria-label="Claims from the intake call">
          {item.claim_rows.map((row, index) => (
            <li key={`${row.field}-${index}`} className="rounded-lg bg-[var(--surface)] px-2.5 py-1.5">
              <b>{row.field.replace(/_/g, " ")}</b> {row.value}
              <small className="block italic text-[var(--muted)]">&ldquo;{row.quote}&rdquo;</small>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

const initials = (name: string) => name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

// Chat bubble. The client is on the left, the office on the right. Display only, nothing here can send a message.
function Bubble({ item, caseId }: { item: Communication; caseId: string }) {
  const office = item.sender_role !== "CLIENT";
  const who = WHO[item.sender_role] ?? item.sender_role;
  return (
    <article className={`flex items-start gap-2 ${office ? "flex-row-reverse" : ""}`}>
      <span
        aria-hidden="true"
        className={`grid h-8 w-8 shrink-0 place-items-center rounded-full text-xs font-bold ${office ? "bg-[var(--accent)] text-white" : "bg-[var(--soft)] text-[var(--ink)]"}`}
      >
        {initials(who)}
      </span>
      <div className={`flex max-w-[78%] flex-col ${office ? "items-end" : "items-start"}`}>
        <p className="mb-0.5 flex flex-wrap items-center gap-x-2 px-1 text-xs text-[var(--muted)]">
          <b className="text-[var(--ink)]">{who}</b>
          <span>{CHANNEL_LABEL[item.kind]}</span>
          <span>{usTime(item.occurred_at)}</span>
        </p>
        <div
          className={`rounded-2xl px-3.5 py-2 text-sm ${
            office ? "rounded-br-sm border border-[var(--accent)] bg-[var(--surface)]" : "rounded-bl-sm bg-[var(--soft)]"
          } ${item.is_draft ? "border-dashed" : ""}`}
        >
          {item.subject && <p className="mb-1 font-semibold">{item.subject}</p>}
          {item.body && <p className="whitespace-pre-wrap leading-relaxed">{item.body}</p>}
          {item.draft_status && (
            <p className="mt-1.5 text-xs">
              <Link to={`/cases/${caseId}?step=reply`} className="font-semibold underline">
                Open the Client reply step
              </Link>
            </p>
          )}
          {item.client_question && <p className="mt-1.5 text-xs text-[var(--muted)]">The answer is drafted in the Client reply step. It never predicts an outcome.</p>}
        </div>
        <div className={`mt-1 flex flex-wrap items-center gap-1.5 px-1 ${office ? "justify-end" : ""}`}>
          {item.is_draft ? <Chip tone="bad">DRAFT, NOT SENT</Chip> : <Chip tone="warn">Claim</Chip>}
          {item.draft_status && <Chip tone={DRAFT_STATUS[item.draft_status].tone}>{DRAFT_STATUS[item.draft_status].text}</Chip>}
          {item.role === "UPDATE" && <Chip tone="muted">Update after the call</Chip>}
          {item.client_question && <Chip tone="ai">Client question</Chip>}
          {item.claims > 0 && <span className="text-xs text-[var(--muted)]">{item.claims} claims read</span>}
          {item.draft_status ? <SourceRef>{item.source_id}</SourceRef> : <Citation source={item.source_id} showTitle={false} />}
        </div>
      </div>
    </article>
  );
}

// The pasted text is saved as a .txt document. A chosen file is sent as it is. Both go through the normal read.
function AddForm({ caseId, onDone }: { caseId: string; onDone: () => void }) {
  const add = useAddCommunication(caseId);
  const [kind, setKind] = useState<CommunicationKind>("ZOOM");
  const [body, setBody] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const ready = file !== null || body.trim() !== "";
  const save = () => {
    const chosen = file ?? new File([body.trim()], FILE_NAME[kind], { type: "text/plain" });
    add.mutate(chosen, { onSuccess: onDone });
  };
  return (
    <div className="mb-4 rounded-2xl border border-[var(--line)] p-3">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <select
          aria-label="Source"
          value={kind}
          onChange={(event) => setKind(event.target.value as CommunicationKind)}
          className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5 font-semibold"
        >
          <option value="ZOOM">Zoom call notes</option>
          <option value="WHATSAPP">WhatsApp message</option>
          <option value="EMAIL">Email</option>
        </select>
        <label className="text-sm text-[var(--muted)]">
          Or choose a file{" "}
          <input type="file" accept=".txt,.eml,.vtt,.json" onChange={(event) => setFile(event.target.files?.[0] ?? null)} className="text-[var(--ink)]" />
        </label>
      </div>
      <textarea
        aria-label="Text"
        value={body}
        onChange={(event) => setBody(event.target.value)}
        disabled={file !== null}
        rows={4}
        placeholder="Paste the text here"
        className="w-full rounded-xl border border-[var(--line)] px-3 py-2"
      />
      {add.isError && (
        <p className="mt-1 text-sm text-[var(--bad)]" role="alert">
          {add.error.message}
        </p>
      )}
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          onClick={save}
          disabled={!ready || add.isPending}
          className="rounded-lg bg-[var(--accent)] px-3.5 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
        >
          {add.isPending ? "Saving..." : "Save"}
        </button>
        <button type="button" onClick={onDone} className="rounded-lg px-3.5 py-1.5 text-sm font-semibold text-[var(--muted)] underline">
          Cancel
        </button>
      </div>
    </div>
  );
}
