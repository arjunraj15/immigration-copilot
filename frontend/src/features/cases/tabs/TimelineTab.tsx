import { useState } from "react";

import { Chip } from "../../../components/Stamp";
import { formatLongDate } from "../../review/format";
import Citation from "../Citation";
import { useAddCalendarEvent, useRemoveCalendarEvent, useTimeline, type CalendarEventType, type TimelineItem } from "../useCases";

type EventKind = Exclude<TimelineItem["kind"], "today">;

// Portal events are solid. Calendar entries are dashed because they are claims.
const KIND: Record<EventKind, string> = {
  verified: "border-2 border-solid border-[var(--ok)]",
  proposed: "border-2 border-solid border-[var(--accent)] bg-[var(--accent)] text-white shadow-[0_0_0_4px_var(--soft)]",
  wrong: "border-2 border-dashed border-[var(--bad)] bg-[var(--bad-soft)]",
  unverified: "border border-dashed border-[var(--muted)]",
  claim: "border border-dashed border-[var(--muted)] bg-[var(--soft)]",
  activity: "border border-solid border-[var(--line)] bg-[var(--surface)]",
  refused: "border border-solid border-[var(--bad)] bg-[var(--bad-soft)]",
};

const LABEL: Record<EventKind, string> = {
  verified: "Verified by portal",
  proposed: "Proposed, waiting for legal",
  wrong: "Not verified, does not match the portal",
  unverified: "Not verified",
  claim: "Claim, not evidence",
  activity: "Case activity",
  refused: "Refused, nothing changed",
};

type Lane = Exclude<TimelineItem["lane"], "today">;
const LANES: { lane: Lane; title: string }[] = [
  { lane: "portal", title: "Government portal" },
  { lane: "calendar", title: "Office calendar" },
  { lane: "communication", title: "Calls and messages" },
  { lane: "activity", title: "Case activity" },
];

// Portal events on the left lane, then calendar entries, logged calls and messages, and what staff did on the case.
// Only verified portal events can set a deadline.
export default function TimelineTab({ caseId }: { caseId: string }) {
  const timeline = useTimeline(caseId);
  const items = timeline.data?.items ?? [];
  // Events are the stored records. The proposed deadline is computed by the server and is not an event.
  const records = items.filter((item) => (item.lane === "portal" || item.lane === "calendar") && item.kind !== "proposed");
  const calls = items.filter((item) => item.lane === "communication").length;
  const actions = items.filter((item) => item.lane === "activity").length;
  const verified = records.filter((item) => item.kind === "verified").length;
  const calendar = records.filter((item) => item.lane === "calendar").length;
  const conflict = items.find((item) => item.kind === "wrong");

  return (
    <div className="pt-4">
      <h2 className="text-2xl font-bold">Case timeline</h2>
      <p className="mb-3 text-[var(--muted)]">Only verified portal events can set a deadline. Calendar entries, calls and messages are shown for comparison. Case activity lists what operations and legal users did.</p>
      <CalendarEntryForm caseId={caseId} />
      {timeline.data && (
        <div className="mb-3 flex flex-wrap items-center gap-2 text-sm" role="status">
          <Chip tone="muted">Events: {records.length}</Chip>
          <Chip tone="ok">{verified} verified portal</Chip>
          <Chip tone="muted">{calendar} calendar, not evidence</Chip>
          <Chip tone="muted">{calls} calls and messages, claims</Chip>
          <Chip tone="muted">{actions} staff actions</Chip>
          {conflict ? (
            <Chip tone="bad">Calendar conflict, {formatLongDate(conflict.date)} does not match</Chip>
          ) : (
            <Chip tone="muted">No calendar conflict</Chip>
          )}
        </div>
      )}
      <div className="mb-2 flex gap-4 text-xs text-[var(--muted)]">
        <span>
          <span aria-hidden className="mr-1 inline-block h-2.5 w-4 rounded-sm border-2 border-solid border-[var(--ok)] align-middle" />
          Solid border, verified by portal
        </span>
        <span>
          <span aria-hidden className="mr-1 inline-block h-2.5 w-4 rounded-sm border-2 border-dashed border-[var(--muted)] align-middle" />
          Dashed border, not verified
        </span>
      </div>
      <div className="grid grid-cols-[96px_1fr_1fr_1fr_1fr] gap-x-3.5 gap-y-2.5 text-sm">
        <span />
        {LANES.map(({ lane, title }, index) => (
          <h4 key={lane} className={`text-[var(--muted)] ${index > 0 ? "border-l border-dashed border-[var(--line)] pl-3.5" : ""}`}>
            {title}
          </h4>
        ))}
        {items.map((event, index) =>
          event.kind === "today" ? (
            <div key="today" className="col-span-5 border-t-2 border-dotted border-[#d79a1c] text-[13px] font-bold text-[var(--warn)]">
              Today {formatLongDate(event.date)}
            </div>
          ) : (
            <TimelineRow key={`${index}-${event.ref}-${event.kind}`} event={event} caseId={caseId} />
          ),
        )}
      </div>
      {timeline.isPending && <p className="py-3 text-[var(--muted)]">Loading timeline...</p>}
      {timeline.isError && (
        <p className="py-3 text-[var(--bad)]" role="alert">
          {timeline.error.message}
        </p>
      )}
    </div>
  );
}

function TimelineRow({ event, caseId }: { event: TimelineItem; caseId: string }) {
  const remove = useRemoveCalendarEvent(caseId);
  if (event.kind === "today") return null;
  const card = (
    <div className={`rounded-xl px-3 py-2 ${KIND[event.kind]}`}>
      <b className={event.kind === "wrong" ? "line-through" : ""}>{event.title}</b>
      <br />
      {event.note}
      {event.ref && (
        <span className="ml-1 text-[var(--ink)]">
          <Citation source={event.ref} showTitle={false} />
        </span>
      )}
      <small className="block text-xs font-semibold opacity-90">{LABEL[event.kind]}</small>
      {event.why && <small className="block text-xs opacity-80">{event.why}</small>}
      {event.manual && event.ref && (
        <button
          type="button"
          onClick={() => remove.mutate(event.ref as string)}
          disabled={remove.isPending}
          className="mt-1 text-xs font-semibold underline disabled:opacity-50"
        >
          {remove.isPending ? "Removing..." : "Remove demo entry"}
        </button>
      )}
    </div>
  );
  return (
    <>
      <span className="text-right font-semibold">{formatLongDate(event.date)}</span>
      {LANES.map(({ lane }, index) => {
        const side = index > 0 ? "border-l border-dashed border-[var(--line)] pl-3.5" : "";
        return event.lane === lane ? (
          <div key={lane} className={side}>
            {card}
          </div>
        ) : (
          <span key={lane} className={side} />
        );
      })}
    </>
  );
}

const ENTRY_TYPES: { value: CalendarEventType; label: string }[] = [
  { value: "CALENDAR_DEADLINE", label: "Deadline" },
  { value: "CALENDAR_REMINDER", label: "Reminder" },
  { value: "CALENDAR_NOTE", label: "Note" },
];

// Demo control. It mocks someone typing an entry into the office calendar. The entry is always unverified.
function CalendarEntryForm({ caseId }: { caseId: string }) {
  const add = useAddCalendarEvent(caseId);
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState("");
  const [type, setType] = useState<CalendarEventType>("CALENDAR_DEADLINE");
  const [details, setDetails] = useState("");
  const ready = date !== "" && details.trim() !== "";

  function save() {
    add.mutate(
      { event_date: date, event_type: type, details: details.trim() },
      {
        onSuccess: () => {
          setDetails("");
          setOpen(false);
        },
      },
    );
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="mb-3 rounded-lg border border-dashed border-[var(--muted)] px-3 py-1.5 text-sm font-semibold">
        Add calendar entry (demo)
      </button>
    );
  }
  return (
    <div className="mb-3 rounded-xl border border-dashed border-[var(--muted)] p-3 text-sm">
      <p className="mb-2 text-[var(--muted)]">Mock a hand-typed office calendar entry. It is saved as not verified, so it cannot set a deadline.</p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="date"
          aria-label="Date"
          value={date}
          onChange={(event) => setDate(event.target.value)}
          className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5"
        />
        <select
          aria-label="Entry type"
          value={type}
          onChange={(event) => setType(event.target.value as CalendarEventType)}
          className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5 font-semibold"
        >
          {ENTRY_TYPES.map((entry) => (
            <option key={entry.value} value={entry.value}>
              {entry.label}
            </option>
          ))}
        </select>
        <input
          aria-label="Details"
          value={details}
          onChange={(event) => setDetails(event.target.value)}
          maxLength={500}
          placeholder="Details, for example Manually-entered due date"
          className="min-w-[260px] flex-1 rounded-lg border border-[var(--line)] px-3 py-1.5"
        />
      </div>
      {add.isError && (
        <p className="mt-1 text-[var(--bad)]" role="alert">
          {add.error.message}
        </p>
      )}
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          onClick={save}
          disabled={!ready || add.isPending}
          className="rounded-lg bg-[var(--accent)] px-3.5 py-1.5 font-semibold text-white disabled:opacity-50"
        >
          {add.isPending ? "Saving..." : "Save"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="rounded-lg px-3.5 py-1.5 font-semibold text-[var(--muted)] underline">
          Cancel
        </button>
      </div>
    </div>
  );
}
