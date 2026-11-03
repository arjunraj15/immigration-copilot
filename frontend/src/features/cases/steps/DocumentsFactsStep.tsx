import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import Icon from "../../../components/Icon";
import FormView from "../../review/FormView";
import { useFormDraft } from "../../review/useProposals";
import { Chip, GhostButton, type Tone } from "../../../components/Stamp";
import { outcomeLabel } from "../../documents/readWithAi";
import FileRow from "../FileRow";
import Pager from "../Pager";
import { DOCUMENT_PAGE_SIZE, useCaseDocuments } from "../useCaseDocuments";
import StepFrame from "./StepFrame";
import { useStepKicker } from "./useSteps";

const OUTCOME_TONE: Record<string, Tone> = {
  USABLE: "ok",
  PENDING: "muted",
  READING: "ai",
  CLAIM_SOURCE: "ai",
  NEEDS_HUMAN_REVIEW: "warn",
};

// Files and the form values read from them. The server built both lists, this only shows them with their citations.
export default function DocumentsFactsStep() {
  const kicker = useStepKicker("docs-facts");
  const { caseId = "" } = useParams();
  const [page, setPage] = useState(1);
  const docs = useCaseDocuments(caseId, { page });
  const draft = useFormDraft(caseId);
  const [showFiles, setShowFiles] = useState(false);
  useEffect(() => {
    if (!showFiles) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setShowFiles(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showFiles]);
  return (
    <StepFrame
      kicker={kicker}
      note="Check each value and its source. Open Files to see what was uploaded. Fields where sources disagree are decided in the Exceptions step."
    >
      <div className="mb-3">
        <GhostButton onClick={() => setShowFiles(true)}>
          <Icon name="documents" /> Files{docs.data ? ` (${docs.data.total})` : ""}
        </GhostButton>
      </div>
      <section aria-label="Form values">
        {draft.isError && (
          <p className="text-[var(--bad)]" role="alert">
            {draft.error.message}
          </p>
        )}
        {draft.data && <FormView value={draft.data} />}
      </section>
      {showFiles && (
        <>
          <div className="fixed inset-0 z-[4] bg-black/45" onClick={() => setShowFiles(false)} aria-hidden />
          <aside aria-label="Files" className="fixed inset-y-0 right-0 z-[5] w-[min(480px,100%)] overflow-auto bg-[var(--soft)] p-4 shadow-2xl">
            <div className="mb-3 flex items-center justify-between gap-2">
              <h3 className="flex items-center gap-2 text-lg font-bold">
                <Icon name="documents" /> Files
              </h3>
              <GhostButton onClick={() => setShowFiles(false)}>Close</GhostButton>
            </div>
            {docs.isPending && <p className="text-[var(--muted)]">Loading files...</p>}
            {docs.isError && (
              <p className="text-[var(--bad)]" role="alert">
                {docs.error.message}
              </p>
            )}
            {docs.data?.items.length === 0 && <p className="mb-3 text-[var(--muted)]">No files are uploaded to this case.</p>}
            {docs.data?.items.map((item) => (
              <FileRow
                key={item.upload_id}
                name={item.original_filename}
                id={item.upload_id}
                summary={item.outcome_reason ?? item.category_label ?? "Not read yet"}
                right={<Chip tone={OUTCOME_TONE[item.outcome] ?? "muted"}>{outcomeLabel(item.outcome)}</Chip>}
              />
            ))}
            <div className="overflow-hidden rounded-2xl">
              <Pager page={page} pageSize={DOCUMENT_PAGE_SIZE} total={docs.data?.total ?? 0} onPage={setPage} />
            </div>
          </aside>
        </>
      )}
    </StepFrame>
  );
}
