import { useState } from "react";
import { LinkedText } from "../Citation";
import { useParams } from "react-router-dom";

import { Chip } from "../../../components/Stamp";
import { usDay } from "../steps/FieldConflict";
import { useDocViewer } from "../docViewer";
import { ChecklistCells, OutcomePill, ReasonChips, reasonText, scannedNote } from "../documentUi";
import Pager from "../Pager";
import { DOCUMENT_PAGE_SIZE, useCaseDocuments, useChecklist, waitingCount, type CaseDocument } from "../useCaseDocuments";

const SET_ASIDE = ["DUPLICATE", "QUARANTINED", "SUPERSEDED", "INVALID", "NEEDS_HUMAN_REVIEW"];

function PdfIcon() {
  return (
    <span className="grid h-9 w-7 shrink-0 place-items-end justify-center rounded-md border border-[var(--line)] bg-[var(--soft)] pb-0.5 text-[8px] font-extrabold text-[var(--bad)]" aria-hidden>
      PDF
    </span>
  );
}

function DocTable({ docs, aside, page, total, onPage }: { docs: CaseDocument[]; aside: boolean; page: number; total: number; onPage: (page: number) => void }) {
  const open = useDocViewer();
  return (
    <div className="mb-3 overflow-hidden rounded-2xl border border-[var(--line)]">
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-[var(--soft)] text-xs uppercase tracking-wide text-[var(--muted)]">
          <tr>
            <th className="px-3.5 py-2 font-semibold">File</th>
            <th className="px-3.5 py-2 font-semibold">{aside ? "Why it was set aside" : "What it is"}</th>
            <th className="px-3.5 py-2 font-semibold">Status</th>
            <th className="px-3.5 py-2 font-semibold">Uploaded</th>
          </tr>
        </thead>
        <tbody>
          {docs.map((doc) => {
            const hidden = doc.outcome === "QUARANTINED";
            return (
              <tr key={doc.upload_id} className={`border-t border-[var(--line)] align-top ${hidden ? "bg-[var(--ai-soft)]" : ""}`}>
                <td className="max-w-72 px-3.5 py-2.5">
                  <div className="flex items-start gap-2.5">
                    <PdfIcon />
                    <span className="min-w-0 break-all">
                      {hidden ? <b className="block">&#128274; {doc.original_filename}</b> : (
                        <button type="button" onClick={() => open(doc.upload_id)} className="block text-left font-bold hover:underline">
                          {doc.original_filename}
                        </button>
                      )}
                      <ReasonChips doc={doc} />
                    </span>
                  </div>
                </td>
                <td className="px-3.5 py-2.5">
                  {!hidden && doc.category_label && <b className="block">{doc.category_label}</b>}
                  {(aside || hidden) && <span className="text-[var(--muted)]"><LinkedText text={reasonText(doc) ?? ""} /></span>}
                  {scannedNote(doc) && <small className="block text-[var(--muted)]">{scannedNote(doc)}</small>}
                </td>
                <td className="whitespace-nowrap px-3.5 py-2.5"><OutcomePill outcome={doc.outcome} /></td>
                <td className="whitespace-nowrap px-3.5 py-2.5 text-[var(--muted)]">{usDay(doc.uploaded_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
      <Pager page={page} pageSize={DOCUMENT_PAGE_SIZE} total={total} onPage={onPage} />
    </div>
  );
}

// The six required categories, the files that can be used and the files set aside, all from the server.
export default function DocumentsTab() {
  const { caseId = "" } = useParams();
  const [usablePage, setUsablePage] = useState(1);
  const [asidePage, setAsidePage] = useState(1);
  const usable = useCaseDocuments(caseId, { page: usablePage, outcome: ["USABLE"] });
  const aside = useCaseDocuments(caseId, { page: asidePage, outcome: SET_ASIDE });
  const checklist = useChecklist(caseId);
  const counts = usable.data?.counts;
  const total = Object.values(counts ?? {}).reduce((sum, n) => sum + n, 0);
  const waiting = waitingCount(counts);
  const claims = counts?.CLAIM_SOURCE ?? 0;

  return (
    <div className="pt-4">
      <h2 className="text-2xl font-bold">{counts ? `${total} files uploaded, ${counts.USABLE ?? 0} can be used` : "Documents"}</h2>
      <p className="mb-3 text-[var(--muted)]">Files are sorted by what is written inside them. A file that belongs to a different client shows no details.</p>
      {(usable.isPending || checklist.isPending) && <p className="py-3 text-[var(--muted)]">Loading documents...</p>}
      {usable.isError && <p className="py-3 text-[var(--bad)]" role="alert">{usable.error.message}</p>}
      {checklist.data && <ChecklistCells items={checklist.data} />}
      {usable.data && (
        <>
          <h3 className="mb-1.5 font-bold">Usable files</h3>
          {usable.data.total === 0 && <p className="mb-3 text-sm text-[var(--muted)]">No file can be used yet.</p>}
          {usable.data.total > 0 && <DocTable docs={usable.data.items} aside={false} page={usablePage} total={usable.data.total} onPage={setUsablePage} />}
          {(aside.data?.total ?? 0) > 0 && <h3 className="mb-1.5 mt-4 font-bold">Set aside</h3>}
          {aside.data && aside.data.total > 0 && <DocTable docs={aside.data.items} aside page={asidePage} total={aside.data.total} onPage={setAsidePage} />}
          {(waiting > 0 || claims > 0) && (
            <p className="mt-3 flex flex-wrap gap-1.5 text-sm text-[var(--muted)]">
              {waiting > 0 && <Chip tone="muted">{`${waiting} waiting to be read`}</Chip>}
              {claims > 0 && <Chip tone="ai">{`${claims} call or message notes, claims only`}</Chip>}
            </p>
          )}
        </>
      )}
    </div>
  );
}
