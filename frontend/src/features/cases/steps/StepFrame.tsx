// Shared wrapper for one step body. Kicker, big title, lead text, content, then the footer is added by StepBody.
import type { ReactNode } from "react";

type Props = {
  kicker: ReactNode;
  title?: string;
  note?: string;
  actions?: ReactNode;
  children?: ReactNode;
};

export default function StepFrame({ kicker, title, note, actions, children }: Props) {
  return (
    <div>
      <div className="flex items-center justify-between gap-3 text-sm text-[var(--muted)]">
        <span>{kicker}</span>
        {actions && <div className="flex gap-1.5">{actions}</div>}
      </div>
      {title && <h2 className="my-1 text-2xl font-bold leading-tight">{title}</h2>}
      {note && <p className="mb-3 text-sm text-[var(--muted)]">{note}</p>}
      {children}
    </div>
  );
}
