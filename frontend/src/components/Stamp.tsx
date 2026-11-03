import type { ReactNode } from "react";

export type Tone = "ok" | "bad" | "warn" | "ai" | "muted";

const TEXT: Record<Tone, string> = {
  ok: "text-[var(--ok)]",
  bad: "text-[var(--bad)]",
  warn: "text-[var(--warn)]",
  ai: "text-[var(--ai)]",
  muted: "text-[var(--muted)]",
};

const CHIP_BG: Record<Tone, string> = {
  ok: "bg-[var(--ok-soft)]",
  bad: "bg-[var(--bad-soft)]",
  warn: "bg-[var(--warn-soft)]",
  ai: "bg-[var(--ai-soft)]",
  muted: "bg-[var(--soft)]",
};

// Document outcome such as USABLE or WRONG CLIENT. Same straight pill as Chip, so it matches the upload popup. Always carries text, never color alone.
export function Stamp({ tone = "ok", children }: { tone?: Tone; children: ReactNode }) {
  return <Chip tone={tone}>{children}</Chip>;
}

// Small rounded status pill. Status is shown with words, not color alone.
export function Chip({ tone = "ok", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2.5 text-xs font-semibold ${TEXT[tone]} ${CHIP_BG[tone]}`}>
      {children}
    </span>
  );
}

// Source chip such as UP-000001 page 1. Shows where a value came from.
export function SourceRef({ children }: { children: ReactNode }) {
  return (
    <span className="mr-1 inline-block rounded-md bg-[var(--soft)] px-1.5 font-mono text-xs font-semibold">
      {children}
    </span>
  );
}

export function OkRow({ label, value, note }: { label: string; value?: string; note?: string }) {
  return (
    <div className="mb-1.5 flex gap-4 rounded-lg bg-[var(--soft)] px-3.5 py-2.5">
      <span className="font-bold text-[var(--ok)]" aria-hidden>
        &#10003;
      </span>
      <b>{label}</b>
      {value && <span>{value}</span>}
      {note && <span className="ml-auto text-[var(--muted)]">{note}</span>}
    </div>
  );
}

export function PrimaryButton({ children, onClick, disabled }: { children: ReactNode; onClick?: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-xl bg-[var(--accent)] px-4 py-2.5 font-semibold text-white disabled:opacity-45"
    >
      {children}
    </button>
  );
}

export function GhostButton({ children, onClick }: { children: ReactNode; onClick?: () => void }) {
  return (
    <button type="button" onClick={onClick} className="rounded-xl border border-[var(--line)] bg-[var(--surface)] px-4 py-2.5 font-semibold">
      {children}
    </button>
  );
}
