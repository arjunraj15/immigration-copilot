import type { Tone } from "../../components/Stamp";

// The colour code of a category tile is its number and a small dot, from the tone the server gives its reason.
// The tile itself keeps the plain border of every other card.
export const TILE: Record<Tone, { number: string; dot: string }> = {
  bad: { number: "text-[var(--bad)]", dot: "bg-[var(--bad)]" },
  warn: { number: "text-[var(--warn)]", dot: "bg-[var(--warn)]" },
  ok: { number: "text-[var(--ok)]", dot: "bg-[var(--ok)]" },
  ai: { number: "text-[var(--ai)]", dot: "bg-[var(--ai)]" },
  muted: { number: "text-[var(--muted)]", dot: "bg-[var(--line)]" },
};
