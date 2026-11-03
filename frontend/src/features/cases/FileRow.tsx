import type { ReactNode } from "react";

import { Stamp } from "../../components/Stamp";
import { useDocViewer } from "./docViewer";

type Props = { name: string; id: string; summary: string; right?: ReactNode };

// One uploaded file. Click opens the document drawer. Right side defaults to a USABLE stamp.
export default function FileRow({ name, id, summary, right }: Props) {
  const open = useDocViewer();
  return (
    <button
      type="button"
      onClick={() => open(id)}
      className="mb-2 flex w-full items-center gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-3.5 py-2.5 text-left hover:bg-[var(--soft)]"
    >
      <span className="grid h-11 w-9 shrink-0 place-items-end justify-center rounded-md border border-[var(--line)] bg-[var(--soft)] pb-1 text-[9px] font-extrabold text-[var(--bad)]">
        PDF
      </span>
      <span className="w-40 shrink-0">
        <b className="block">{name}</b>
        <small className="text-[var(--muted)]">{id}</small>
      </span>
      <span className="min-w-0 flex-1 text-sm text-[var(--muted)]">{summary}</span>
      {right ?? <Stamp>USABLE</Stamp>}
    </button>
  );
}
