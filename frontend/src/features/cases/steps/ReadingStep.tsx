import { useState } from "react";
import { LinkedText } from "../Citation";
import { useParams } from "react-router-dom";

import Icon from "../../../components/Icon";
import { useReadWithAi } from "../../documents/readWithAi";
import UploadWizard from "../../upload/UploadWizard";
import Pager from "../Pager";
import { ChecklistCells, OutcomePill, ReasonChips, reasonText, scannedNote } from "../documentUi";
import { DOCUMENT_PAGE_SIZE, useCaseDocuments, useChecklist, waitingCount } from "../useCaseDocuments";
import { useCaseInfo } from "../useCases";
import { usDay } from "./FieldConflict";
import StepFrame from "./StepFrame";
import { useStepKicker } from "./useSteps";

const ACTION = "inline-flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-xs font-semibold hover:bg-[var(--soft)] disabled:opacity-50";

// The files of the open case with what the server decided for each, and the six required categories.
export default function ReadingStep() {
  const kicker = useStepKicker("documents");
  const { caseId = "" } = useParams();
  const [page, setPage] = useState(1);
  const [uploading, setUploading] = useState(false);
  const docs = useCaseDocuments(caseId, { page });
  const waiting = waitingCount(docs.data?.counts) > 0;
  const checklist = useChecklist(caseId, waiting ? 4000 : false);
  const info = useCaseInfo(caseId);
  const readAgain = useReadWithAi();
  const items = docs.data?.items ?? [];

  return (
    <StepFrame
      kicker={kicker}
      title={info.data?.name ? `${info.data.name} documents` : "Documents"}
      actions={
        <button
          type="button"
          onClick={() => setUploading(true)}
          disabled={!info.data}
          className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--accent)]/10 px-3 py-1.5 text-sm font-semibold text-[var(--accent)] transition hover:bg-[var(--accent)]/20 disabled:opacity-50"
        >
          <Icon name="plus" /> Upload
        </button>
      }
      note="Each file is sorted by what is written inside it, not by its file name. Files that can't be used are set aside with a reason."
    >
      {uploading && info.data && (
        <UploadWizard
          onClose={() => setUploading(false)}
          forCase={{ case_id: info.data.case_id, initials: "", name: info.data.name, number: info.data.number, note: "", tone: "muted" }}
        />
      )}
      {checklist.data && <ChecklistCells items={checklist.data} />}
      {checklist.isError && <p className="mb-3 text-[var(--bad)]" role="alert">{checklist.error.message}</p>}
      {docs.isPending && <p className="py-3 text-[var(--muted)]">Loading files...</p>}
      {docs.isError && <p className="py-3 text-[var(--bad)]" role="alert">{docs.error.message}</p>}
      {docs.data && items.length === 0 && <p className="py-3 text-[var(--muted)]">No files have been uploaded to this case yet.</p>}
      {items.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-[var(--line)]">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="bg-[var(--soft)] text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr>
                <th className="px-3.5 py-2 font-semibold">File</th>
                <th className="px-3.5 py-2 font-semibold">What it is</th>
                <th className="px-3.5 py-2 font-semibold">Status</th>
                <th className="px-3.5 py-2 font-semibold">Uploaded</th>
                <th className="px-3.5 py-2 font-semibold"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {items.map((doc) => (
                <tr key={doc.upload_id} className="border-t border-[var(--line)] align-top">
                  <td className="max-w-64 break-all px-3.5 py-2.5">
                    <b className="block">{doc.original_filename}</b>
                    <ReasonChips doc={doc} />
                  </td>
                  <td className="px-3.5 py-2.5">
                    {doc.outcome !== "QUARANTINED" && doc.category_label && <b className="block">{doc.category_label}</b>}
                    <span className="text-[var(--muted)]">{doc.outcome === "READING" ? "Reading..." : doc.outcome === "PENDING" ? "Waiting to be read" : <LinkedText text={reasonText(doc) ?? ""} />}</span>
                    {scannedNote(doc) && <small className="block text-[var(--muted)]">{scannedNote(doc)}</small>}
                    {readAgain.isError && readAgain.variables === doc.upload_id && <small className="block text-[var(--bad)]" role="alert">{readAgain.error.message}</small>}
                  </td>
                  <td className="whitespace-nowrap px-3.5 py-2.5"><OutcomePill outcome={doc.outcome} /></td>
                  <td className="whitespace-nowrap px-3.5 py-2.5 text-[var(--muted)]">{usDay(doc.uploaded_at)}</td>
                  <td className="px-3.5 py-2.5 text-right">
                    {doc.outcome === "NEEDS_HUMAN_REVIEW" && (
                      <button type="button" className={ACTION} disabled={readAgain.isPending} onClick={() => readAgain.mutate(doc.upload_id)} aria-label={`Read ${doc.original_filename} with AI`}>
                        <Icon name="ai" /> {readAgain.isPending && readAgain.variables === doc.upload_id ? "Reading..." : "Read with AI"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager page={page} pageSize={DOCUMENT_PAGE_SIZE} total={docs.data?.total ?? 0} onPage={setPage} />
        </div>
      )}
    </StepFrame>
  );
}
