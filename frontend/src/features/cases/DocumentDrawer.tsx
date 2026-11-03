import { useEffect } from "react";

import { ApiError } from "../../api/client";
import { Chip, GhostButton } from "../../components/Stamp";
import { saveBlob } from "../review/format";
import FileViewer from "./FileViewer";
import JsonView from "./JsonView";
import { caseIdFromSource, sourceKind, type SourceKind } from "./sourceId";
import { useSourceRecord, useUploadFile } from "./useSource";

type Props = { sourceId: string | null; onClose: () => void };

const EXPLAIN: Record<Exclude<SourceKind, "file" | "unknown">, string> = {
  profile: "A profile value a team member verified earlier. It may be out of date, so it is checked against the documents.",
  note: "Intake call notes. An unverified claim until a document or the profile backs it up.",
  message: "A message from the client. A claim, never a fact on its own.",
  event: "A case event. Only verified portal events count as evidence.",
};

const EXPLAIN_TITLE = { profile: "Profile value (checked earlier, may be stale)", note: "Intake call notes", message: "Client message", event: "Case event" };

function Problem({ error, sample }: { error: Error; sample: boolean }) {
  const text = sample && error instanceof ApiError && error.status === 404 ? "This is sample data and has no file." : error.message;
  return (
    <p className="text-[var(--bad)]" role="alert">
      {text}
    </p>
  );
}

function FileSource({ id, onClose }: { id: string; onClose: () => void }) {
  const file = useUploadFile(id);
  const name = file.data?.fileName ?? id;
  return (
    <>
      <Header title={file.data ? name : "Uploaded file"} sub={id} onClose={onClose} onDownload={file.data && (() => saveBlob(file.data.blob, name))} />
      {file.isPending && <p className="text-[var(--muted)]">Loading...</p>}
      {file.isError && <Problem error={file.error} sample />}
      {file.data && <FileViewer blob={file.data.blob} name={name} />}
    </>
  );
}

function RecordSource({ id, onClose }: { id: string; onClose: () => void }) {
  const record = useSourceRecord(id);
  const kind = sourceKind(id) as keyof typeof EXPLAIN;
  const caseId = caseIdFromSource(id);
  const label = String(record.data?.source_kind ?? "").toUpperCase();
  return (
    <>
      <Header title={kind in EXPLAIN ? EXPLAIN_TITLE[kind] : "Source"} sub={`${id}, ${caseId}`} onClose={onClose} />
      {record.isLoading && <p className="text-[var(--muted)]">Loading...</p>}
      {record.isError && <Problem error={record.error} sample={false} />}
      {(record.data === null || caseId === null) && <p role="alert">No record for {id} was found on this case.</p>}
      {record.data && (
        <>
          <p className="mb-2 flex flex-wrap items-center gap-2 text-sm">
            <Chip tone={label === "EVIDENCE" ? "ok" : "warn"}>{label === "EVIDENCE" ? "Evidence" : "Claim"}</Chip>
            <span className="text-[var(--muted)]">{EXPLAIN[kind]}</span>
          </p>
          <JsonView value={record.data} />
        </>
      )}
    </>
  );
}

function Header({ title, sub, onClose, onDownload }: { title: string; sub: string; onClose: () => void; onDownload?: (() => void) | null }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2">
      <div className="min-w-0">
        <b className="break-all">{title}</b>
        <div className="break-all text-sm text-[var(--muted)]">{sub}</div>
      </div>
      {onDownload && <GhostButton onClick={onDownload}>Download</GhostButton>}
      <GhostButton onClick={onClose}>Close</GhostButton>
    </div>
  );
}

// Side drawer with the real source behind a citation. Files come from the upload route and records from the case sources route.
export default function DocumentDrawer({ sourceId, onClose }: Props) {
  useEffect(() => {
    if (!sourceId) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sourceId, onClose]);

  if (!sourceId) return null;
  const kind = sourceKind(sourceId);
  return (
    <>
      <div className="fixed inset-0 z-[9] bg-black/45" onClick={onClose} aria-hidden />
      <div role="dialog" aria-label="Document viewer" className="fixed inset-y-0 right-0 z-10 w-[min(760px,100%)] overflow-auto bg-[var(--soft)] p-4 shadow-2xl">
        {kind === "file" && <FileSource key={sourceId} id={sourceId} onClose={onClose} />}
        {kind !== "file" && kind !== "unknown" && <RecordSource key={sourceId} id={sourceId} onClose={onClose} />}
        {kind === "unknown" && (
          <>
            <Header title="Source" sub={sourceId} onClose={onClose} />
            <p role="alert">No details are available for {sourceId}.</p>
          </>
        )}
      </div>
    </>
  );
}
