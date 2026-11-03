import { SourceRef } from "../../components/Stamp";
import { useDocViewer } from "./docViewer";
import { sourceKind } from "./sourceId";

const TITLE = {
  file: "Uploaded document",
  profile: "Profile (checked earlier, may be stale)",
  note: "Intake call notes",
  message: "Client message",
  event: "Case event",
  unknown: "",
};

// A source chip. Click opens the real source in the document drawer.
// The source can carry a detail after the id, such as "UP-000001 page 1".
export default function Citation({ source, showTitle = true }: { source: string; showTitle?: boolean }) {
  const open = useDocViewer();
  const [id] = source.split(" ");
  const title = TITLE[sourceKind(id)];

  return (
    <span className="mr-3 inline-block align-middle">
      <button type="button" onClick={() => open(id)} className="inline-flex items-center gap-1 hover:underline">
        <SourceRef>{source}</SourceRef>
        {showTitle && title && <small className="text-[var(--muted)]">{title}</small>}
      </button>
    </span>
  );
}

// Plain text where each upload id (such as UP-000116) opens that file in the document drawer.
export function LinkedText({ text }: { text: string }) {
  const open = useDocViewer();
  return (
    <>
      {text.split(/(UP-\d+)/).map((part, i) =>
        /^UP-\d+$/.test(part) ? (
          <button key={i} type="button" onClick={() => open(part)} className="font-mono font-semibold text-[var(--ink)] underline">
            {part}
          </button>
        ) : (
          part
        ),
      )}
    </>
  );
}
