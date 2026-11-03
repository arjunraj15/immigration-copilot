import { useState } from "react";

import Icon from "../../components/Icon";
import { useRole } from "../../lib/role";
import {
  useImportData,
  type ImportBody,
  type ImportResult,
} from "./useImportData";

type Kind = ImportBody["kind"];

const FIELD =
  "w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1.5 text-sm";
const LABEL = "block text-xs font-semibold text-[var(--muted)]";
const KINDS: { value: Kind; label: string }[] = [
  { value: "EVENT", label: "Portal or calendar event" },
  { value: "ZOOM_NOTE", label: "Zoom call note" },
  { value: "MESSAGE", label: "Client message" },
];

// datetime-local gives no zone, so the entry is read as local time and sent as UTC.
const isoMoment = (local: string) => new Date(local).toISOString();

function Summary({ result }: { result: ImportResult }) {
  const stored = result.result === "INSERTED" || result.result === "UPDATED";
  return (
    <div
      className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--soft)] p-3 text-sm"
      role="status"
    >
      <p className="font-bold">New data arrived</p>
      <p>
        {stored
          ? `Saved as ${result.record_id} (${result.result.toLowerCase()}).`
          : result.result === "DUPLICATE_CONTENT"
            ? `Already on the case as ${result.duplicate_of}, nothing was saved.`
            : `${result.record_id} is already on the case with the same content, nothing changed.`}
      </p>
      {result.deadline && (
        <p>
          Deadline: {result.deadline.before ?? "none"} (
          {result.deadline.before_state ?? "none"}) to{" "}
          {result.deadline.after ?? "none"} (
          {result.deadline.after_state ?? "none"}).
        </p>
      )}
      {result.changes.length > 0 && (
        <ul className="mt-1 list-disc pl-5">
          {result.changes.map((c) => (
            <li key={c.field}>
              {c.label}: {c.before_state ?? "new"} to {c.after_state}
              {c.after_value ? ` (${c.after_value})` : ""}
            </li>
          ))}
        </ul>
      )}
      {stored && !result.deadline && result.changes.length === 0 && (
        <p className="text-[var(--muted)]">
          No field state or deadline changed.
        </p>
      )}
    </div>
  );
}

// A demo control for new mock data on one case. The server stores each record once, keeps notes and messages as claims and audits the import.
export default function ImportData({ caseId }: { caseId: string }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<Kind>("EVENT");
  const [form, setForm] = useState<Record<string, string | boolean>>({
    event_source: "MOCK_PORTAL",
    event_type: "MOCK_EVIDENCE_REQUEST_RECEIVED",
    channel: "EMAIL",
    source_verified: true,
  });
  const { role } = useRole();
  // Only the legal reviewer can vouch for a portal record. The server refuses it from anyone else.
  const canVerify = role === "attorney";
  const send = useImportData(caseId);
  const set = (key: string, value: string | boolean) =>
    setForm((f) => ({ ...f, [key]: value }));
  const text = (key: string) => String(form[key] ?? "");

  const body = (): ImportBody | null => {
    if (kind === "EVENT") {
      if (
        !text("event_date") ||
        !text("source_reference").trim() ||
        !text("details").trim()
      )
        return null;
      return {
        kind,
        event_date: text("event_date"),
        event_type: text("event_type").trim().toUpperCase(),
        event_source: text("event_source") as "MOCK_PORTAL",
        source_reference: text("source_reference").trim(),
        details: text("details").trim(),
        source_verified:
          form.event_source === "MOCK_PORTAL" && form.source_verified === true,
      };
    }
    if (!text("when") || !text("text").trim()) return null;
    if (kind === "ZOOM_NOTE")
      return {
        kind,
        recorded_at: isoMoment(text("when")),
        summary: text("text").trim(),
      };
    return {
      kind,
      created_at: isoMoment(text("when")),
      channel: text("channel") as "EMAIL",
      subject: text("subject").trim(),
      body: text("text").trim(),
    };
  };
  const ready = body();

  const button = (
    <button
      type="button"
      onClick={() => setOpen((v) => !v)}
      aria-expanded={open}
      title="Add new mock data to this case"
      className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line)] px-2.5 py-1 text-sm font-semibold hover:bg-[var(--soft)]"
    >
      <Icon name="upload" />
      Add data
    </button>
  );
  if (!open) return button;
  return (
    <span className="relative">
      {button}
      <section
        className="fixed inset-x-4 top-32 z-30 max-h-[calc(100vh-9rem)] overflow-y-auto sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:max-h-[70vh] sm:w-[34rem] rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3 shadow-xl"
        aria-label="Add new case data"
      >
        <form
          className="grid gap-2 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) send.mutate(ready);
          }}
        >
          <label className={LABEL}>
            Kind
            <select
              className={FIELD}
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as Kind);
                send.reset();
              }}
            >
              {KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
          </label>
          {kind === "EVENT" ? (
            <>
              <label className={LABEL}>
                Event date
                <input
                  className={FIELD}
                  type="date"
                  value={text("event_date")}
                  onChange={(e) => set("event_date", e.target.value)}
                />
              </label>
              <label className={LABEL}>
                Source
                <select
                  className={FIELD}
                  value={text("event_source")}
                  onChange={(e) => set("event_source", e.target.value)}
                >
                  <option value="MOCK_PORTAL">Mock portal</option>
                  <option value="GOOGLE_CALENDAR_MOCK">
                    Calendar (always a claim)
                  </option>
                </select>
              </label>
              <label className={LABEL}>
                Event type
                <input
                  className={FIELD}
                  value={text("event_type")}
                  onChange={(e) => set("event_type", e.target.value)}
                />
              </label>
              <label className={LABEL}>
                Reference
                <input
                  className={FIELD}
                  value={text("source_reference")}
                  onChange={(e) => set("source_reference", e.target.value)}
                />
              </label>
              <label className={LABEL}>
                Details
                <input
                  className={FIELD}
                  value={text("details")}
                  onChange={(e) => set("details", e.target.value)}
                />
              </label>
              {form.event_source === "MOCK_PORTAL" && (
                <label className="flex flex-wrap items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    disabled={!canVerify}
                    checked={canVerify && form.source_verified === true}
                    onChange={(e) => set("source_verified", e.target.checked)}
                  />
                  Verified portal record
                  {!canVerify && <small className="text-[var(--muted)]">Only the legal reviewer can verify. It is saved as a claim.</small>}
                </label>
              )}
            </>
          ) : (
            <>
              <label className={LABEL}>
                When
                <input
                  className={FIELD}
                  type="datetime-local"
                  value={text("when")}
                  onChange={(e) => set("when", e.target.value)}
                />
              </label>
              {kind === "MESSAGE" && (
                <>
                  <label className={LABEL}>
                    Channel
                    <select
                      className={FIELD}
                      value={text("channel")}
                      onChange={(e) => set("channel", e.target.value)}
                    >
                      <option value="EMAIL">Email</option>
                      <option value="WHATSAPP">WhatsApp</option>
                    </select>
                  </label>
                  <label className={LABEL}>
                    Subject
                    <input
                      className={FIELD}
                      value={text("subject")}
                      onChange={(e) => set("subject", e.target.value)}
                    />
                  </label>
                </>
              )}
              <label className={`${LABEL} sm:col-span-2`}>
                {kind === "ZOOM_NOTE" ? "Call summary" : "Message text"}
                <textarea
                  className={FIELD}
                  rows={3}
                  value={text("text")}
                  onChange={(e) => set("text", e.target.value)}
                />
              </label>
            </>
          )}
          <div className="flex items-center gap-2 sm:col-span-2">
            <button
              type="submit"
              disabled={!ready || send.isPending}
              className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
            >
              {send.isPending ? "Importing..." : "Import"}
            </button>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                send.reset();
              }}
              className="rounded-lg border border-[var(--line)] px-3 py-1.5 text-sm font-semibold"
            >
              Close
            </button>
            <small className="text-[var(--muted)]">
              Notes and messages stay claims. Nothing is sent to a client.
            </small>
          </div>
        </form>
        {send.isError && (
          <p className="mt-2 text-sm text-[var(--bad)]" role="alert">
            {send.error.message}
          </p>
        )}
        {send.data && <Summary result={send.data} />}
      </section>
    </span>
  );
}
