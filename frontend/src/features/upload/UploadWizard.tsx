import { useEffect, useRef, useState, type DragEvent } from "react";
import { useNavigate } from "react-router-dom";

import { Chip, GhostButton, PrimaryButton, type Tone } from "../../components/Stamp";
import { reasonText } from "../cases/documentUi";
import { useCaseDocuments, type CaseDocument } from "../cases/useCaseDocuments";
import { useCaseInfo, useQueue, type QueueItem } from "../cases/useCases";
import { outcomeLabel } from "../documents/readWithAi";
import { ACCEPT, collectDropped, fromFileList, MAX_BYTES, MAX_FILES, screenFile, TYPE_HINT, type Picked, type Rejected } from "./fileRules";
import NameStep from "./NameStep";
import ProcessingStep from "./ProcessingStep";
import { useAddDocuments, useChecklist, useCreateDraft, useDiscardDraft, type DraftResult, type FileResult } from "./useIntake";

type Entry = { id: number; name: string; size: number; file: File };
type CaseRef = Pick<QueueItem, "case_id" | "name">;
// "create" belongs to new cases only. Both flows end at "done", the result of the upload.
type Step = "client" | "documents" | "processing" | "name" | "done";
type Mode = "new" | "existing";

const STEP_LABELS: Record<Step, string> = {
  client: "Choose case", documents: "Documents", processing: "AI processing", name: "Client name", done: "Upload result",
};
const STEP_ORDER: Record<Mode, Step[]> = {
  new: ["documents", "processing", "name", "done"],
  existing: ["client", "documents", "done"],
};

function formatSize(bytes: number): string {
  return bytes >= 1_000_000 ? `${(bytes / 1_000_000).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1000))} KB`;
}

function StepPills({ current, mode }: { current: Step; mode: Mode }) {
  const order = STEP_ORDER[mode];
  const at = order.indexOf(current);
  return (
    <ol className="my-1 flex py-1 flex-wrap items-center gap-x-1.5 gap-y-1 text-base" aria-label="Steps">
      {order.map((step, index) => (
        <li key={step} aria-current={index === at ? "step" : undefined} className="flex items-center gap-1.5">
          {index > 0 && (
            <span aria-hidden="true" className="text-[var(--line)]">
              &rsaquo;
            </span>
          )}
          <span
            className={`grid h-5 w-5 place-items-center rounded-full text-xs font-semibold ${
              index < at ? "bg-[var(--ok)] text-white" : index === at ? "bg-[var(--accent)] text-white" : "border border-[var(--line)] text-[var(--muted)]"
            }`}
          >
            {index < at ? "✓" : index + 1}
          </span>
          <span className={index === at ? "font-semibold" : "text-[var(--muted)]"}>
            {step === "done" && mode === "existing" ? "Results" : STEP_LABELS[step]}
          </span>
        </li>
      ))}
    </ol>
  );
}

function ModeCard({ title, note, selected, onSelect }: { title: string; note: string; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`rounded-2xl border-2 p-4 text-left ${selected ? "border-[var(--accent)] bg-[var(--soft)]" : "border-[var(--line)]"}`}
    >
      <b className="block text-lg">{title}</b>
      <small className="text-[var(--muted)]">{note}</small>
    </button>
  );
}

// Search box and results for picking one of the firm's existing cases.
function ClientPicker({ picked, onPick }: { picked: CaseRef | null; onPick: (item: QueueItem) => void }) {
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const queue = useQueue(term);

  useEffect(() => {
    const timer = setTimeout(() => setTerm(search.trim()), 250);
    return () => clearTimeout(timer);
  }, [search]);

  const items = queue.data?.groups.flatMap((group) => group.items) ?? [];
  return (
    <div className="mt-4">
      <input
        className="w-full rounded-xl border border-[var(--line)] px-3 py-2.5"
        placeholder="Search by case number or client name"
        aria-label="Search cases"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <ul className="mt-2 max-h-56 overflow-auto">
        {queue.isPending && <li className="px-1 text-sm text-[var(--muted)]">Loading cases...</li>}
        {queue.isError && (
          <li className="px-1 text-sm text-[var(--bad)]" role="alert">
            Could not load cases: {queue.error.message}
          </li>
        )}
        {queue.data && items.length === 0 && <li className="px-1 text-sm text-[var(--muted)]">No cases match your search.</li>}
        {items.map((item) => (
          <li key={item.case_id}>
            <button
              type="button"
              onClick={() => onPick(item)}
              aria-pressed={picked?.case_id === item.case_id}
              className={`mb-1 flex w-full items-center gap-3 rounded-xl border-2 p-2 text-left hover:bg-[var(--soft)] ${
                picked?.case_id === item.case_id ? "border-[var(--accent)]" : "border-transparent"
              }`}
            >
              <span className="grid h-8 w-8 place-items-center rounded-full bg-[var(--soft)] text-xs font-bold">{item.initials}</span>
              <b className="font-mono">{item.case_id}</b>
              <span className="flex-1 text-[var(--muted)]">{item.name}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join("");
}

// SYNTH_WORK_STATUS_RENEWAL becomes "Work status renewal".
function matterLabel(archetype: string): string {
  const words = archetype.replace(/^SYNTH_/, "").replace(/_/g, " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

// The case is the unique number. The client sits inside it and shows once the name is known.
function CaseRow({ picked, onEdit }: { picked: CaseRef | null; onEdit: () => void }) {
  const info = useCaseInfo(picked?.case_id);
  const name = picked?.name ?? "";
  const detail = info.data ? `${matterLabel(info.data.archetype)} · Legal: ${info.data.legal_reviewer}` : "";
  return (
    <div className="mb-3 flex items-center gap-3 rounded-2xl border border-[var(--line)] px-4 py-3">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[var(--soft)] text-xs font-bold">{name ? initialsOf(name) : "?"}</span>
      <span className="min-w-0 flex-1">
        <b className={picked ? "font-mono" : ""}>{picked ? picked.case_id : "New case"}</b>{" "}
        <small className="text-[var(--muted)]">
          {picked ? "" : "Number assigned when created. "}
          {name ? `Client: ${name}` : "Client name is entered next"}
          {detail && ` · ${detail}`}
        </small>
      </span>
      <button type="button" onClick={onEdit} className="rounded-lg border border-[var(--line)] px-3 py-1.5 text-sm font-semibold hover:bg-[var(--soft)]">
        Edit case
      </button>
    </div>
  );
}

function FileLine({ entry, onRemove }: { entry: Entry; onRemove: () => void }) {
  return (
    <li className="flex items-center gap-3 border-b border-[var(--line)] py-2.5">
      <span className="grid h-11 w-9 shrink-0 place-items-end justify-center rounded-md border border-[var(--line)] bg-[var(--soft)] pb-1 text-[9px] font-extrabold text-[var(--bad)]">
        {(entry.name.split(".").pop() ?? "FILE").slice(0, 4).toUpperCase()}
      </span>
      <span className="min-w-0 flex-1">
        <b className="block truncate" title={entry.name}>{entry.name}</b>
        <small className="text-[var(--muted)]">{formatSize(entry.size)}</small>
      </span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${entry.name}`}
        className="rounded-lg border border-[var(--line)] px-2.5 py-1 text-sm font-semibold hover:bg-[var(--soft)]"
      >
        Remove
      </button>
    </li>
  );
}

// What the server said about one file. The server decides, this only words it.
function resultChip(result: FileResult): { label: string; tone: Tone } {
  if (result.status === "refused") return { label: "REFUSED", tone: "bad" };
  if (result.outcome === "DUPLICATE") return { label: "DUPLICATE", tone: "warn" };
  return { label: "UPLOADED", tone: "ok" };
}

// One small pill per required category, done or missing. Only mounted once every file is settled.
function Checklist({ caseId }: { caseId: string }) {
  const checklist = useChecklist(caseId);
  if (!checklist.data) return null;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Required documents">
      {checklist.data.map((item) => {
        const done = item.status === "SATISFIED";
        const label = item.category.replace(/_/g, " ").toLowerCase();
        return (
          <li key={item.category}>
            <Chip tone={done ? "ok" : "muted"}>
              <span className="capitalize">{label}</span> {done ? "added" : item.status === "NOT_USABLE" ? "not usable" : "missing"}
            </Chip>
          </li>
        );
      })}
    </ul>
  );
}

function ResultLine({ result }: { result: FileResult }) {
  const chip = resultChip(result);
  return (
    <li className="flex items-center gap-3 border-b border-[var(--line)] py-2.5">
      <span className="min-w-0 flex-1">
        <b className="block truncate" title={result.original_filename}>{result.original_filename}</b>
        <small className="text-[var(--muted)]">{result.reason ?? "Waiting to be read"}</small>
      </span>
      <Chip tone={chip.tone}>{chip.label}</Chip>
    </li>
  );
}

const READING = ["PENDING", "READING"];

// One uploaded file with its live reading state. The server decides the outcome and the AI document type.
function ReadingLine({ doc }: { doc: CaseDocument }) {
  const tone: Tone = READING.includes(doc.outcome) ? "muted" : doc.outcome === "USABLE" ? "ok" : doc.outcome === "NEEDS_HUMAN_REVIEW" ? "warn" : "bad";
  return (
    <li className="flex items-center gap-3 border-b border-[var(--line)] py-2.5">
      <span className="min-w-0 flex-1">
        <b className="block truncate" title={doc.original_filename}>{doc.original_filename}</b>
        <small className="text-[var(--muted)]">
          {READING.includes(doc.outcome) ? "AI is reading this file" : [doc.category_label, doc.outcome_reason].filter(Boolean).join(". ")}
        </small>
      </span>
      <Chip tone={tone}>{outcomeLabel(doc.outcome).toUpperCase()}</Chip>
    </li>
  );
}

// One file that is not usable as uploaded, with the reason the server saved. Wrong client files show here too.
function ExceptionLine({ doc }: { doc: CaseDocument }) {
  const wrong = doc.reason_code === "WRONG_CLIENT" || doc.reason_code === "MIXED_CLIENTS";
  return (
    <li className="flex items-center gap-3 border-b border-[var(--line)] py-2.5">
      <span className="min-w-0 flex-1">
        <b className="block truncate" title={doc.original_filename}>{doc.original_filename}</b>
        <small className="text-[var(--muted)]">{reasonText(doc) ?? doc.category_label ?? "Needs a decision"}</small>
      </span>
      <Chip tone={doc.outcome === "NEEDS_HUMAN_REVIEW" || doc.outcome === "DUPLICATE" ? "warn" : "bad"}>{wrong ? "WRONG CLIENT" : outcomeLabel(doc.outcome).toUpperCase()}</Chip>
    </li>
  );
}

// One status line with live reading progress, a Files panel closed by default, the checklist once settled and the exceptions this upload raised.
// Only the files of this upload. The case Exceptions step stays the server list of everything open on the case, the form draft is reviewed there.
function Done({ caseId, results }: { caseId: string; results: FileResult[] }) {
  const [showFiles, setShowFiles] = useState(false);
  const docs = useCaseDocuments(caseId, { pageSize: 100 });
  const uploaded = new Set(results.map((result) => result.upload_id));
  const items = (docs.data?.items ?? []).filter((doc) => uploaded.has(doc.upload_id));
  const refused = results.filter((result) => result.status === "refused");
  // A file the AI service could not read stays pending with a reason. It is not being read, so the wizard must not wait for it.
  const unread = items.filter((doc) => doc.outcome === "PENDING" && doc.outcome_reason);
  const waiting = items.filter((doc) => READING.includes(doc.outcome) && !unread.includes(doc)).length;
  const finished = items.length > 0 && waiting === 0;
  const review = items.filter((doc) => doc.outcome === "NEEDS_HUMAN_REVIEW").length;
  const exceptions = finished ? items.filter((doc) => doc.outcome !== "USABLE" && !READING.includes(doc.outcome)) : [];
  const noun = items.length === 1 ? "file" : "files";
  const status = finished && unread.length > 0
    ? `The AI service is not available right now. ${unread.length} ${unread.length === 1 ? "file is" : "files are"} saved and not read yet. Press Read with AI on the Documents page when it is back.`
    : finished
    ? `AI finished reading ${items.length} ${noun}${review > 0 ? `, ${review} ${review === 1 ? "needs" : "need"} human review` : ""}.`
    : items.length > 0
      ? `AI is reading ${waiting} of ${items.length} ${noun}`
      : refused.length === results.length
        ? "No file was accepted."
        : "Starting to read...";
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="relative flex items-center gap-3 rounded-xl bg-[var(--soft)] px-3 py-2">
        <span className="flex-1 font-semibold" role="status">{status}</span>
        <GhostButton onClick={() => setShowFiles((open) => !open)}>Files ({results.length})</GhostButton>
        {showFiles && (
          <ul className="absolute right-0 top-full z-10 mt-1 max-h-60 w-full overflow-y-auto rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 shadow-lg" aria-label="Uploaded files">
            {items.map((doc) => (
              <ReadingLine key={doc.upload_id} doc={doc} />
            ))}
            {refused.map((result, index) => (
              <ResultLine key={`${result.original_filename}-${index}`} result={result} />
            ))}
          </ul>
        )}
      </div>
      {finished && <Checklist caseId={caseId} />}
      <section className="min-h-0 flex-1 overflow-y-auto" aria-label="Upload result">
        <h3 className="mb-1 text-lg font-bold">Upload result{finished && exceptions.length + refused.length > 0 ? ` · ${exceptions.length + refused.length} to resolve` : ""}</h3>
        {!finished && <p className="text-[var(--muted)]">Issues with these files appear here when the AI finishes reading.</p>}
        {finished && exceptions.length + refused.length === 0 && <p className="text-[var(--muted)]">Every file was usable. No issues found.</p>}
        <ul>
          {exceptions.map((doc) => (
            <ExceptionLine key={doc.upload_id} doc={doc} />
          ))}
          {finished && refused.map((result, index) => (
            <ResultLine key={`${result.original_filename}-${index}`} result={result} />
          ))}
        </ul>
      </section>
    </div>
  );
}

// Modal from the frozen design. A new client is created with the files, an existing client is picked from the firm's list.
// forCase opens the wizard on Add documents for that one case, so files can be added to it later.
// The server checks and reads the files after they are uploaded. Nothing is read in the browser.
export default function UploadWizard({ onClose, forCase }: { onClose: () => void; forCase?: QueueItem }) {
  const [step, setStep] = useState<Step>(forCase ? "documents" : "client");
  const [mode, setMode] = useState<Mode>(forCase ? "existing" : "new");
  const [picked, setPicked] = useState<CaseRef | null>(forCase ?? null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [dragging, setDragging] = useState(false);
  // The draft case that exists on the server until it is submitted or discarded.
  const [draft, setDraft] = useState<DraftResult | null>(null);
  const [results, setResults] = useState<FileResult[]>([]);
  const createDraft = useCreateDraft();
  const discard = useDiscardDraft();
  const addDocuments = useAddDocuments();
  const nextId = useRef(1);
  const navigate = useNavigate();
  const entriesCount = useRef(0);
  const [rejected, setRejected] = useState<Rejected[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);

  // Closing on a draft asks first, then deletes the draft on the server.
  const requestClose = () => {
    if (!draft) return onClose();
    if (window.confirm("Discard this draft case? The notes and files you added are deleted.")) discard.mutate(draft.case_id, { onSettled: onClose });
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && requestClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  // Every file is screened first. Refused files are listed with the reason and never uploaded. The server checks again.
  const addFiles = async (picked: Picked[]) => {
    const refused: Rejected[] = [];
    for (const item of picked) {
      const reason = entriesCount.current >= MAX_FILES ? `More than ${MAX_FILES} files` : await screenFile(item);
      if (reason) {
        refused.push({ path: item.path, reason });
        continue;
      }
      entriesCount.current += 1;
      const id = nextId.current++;
      setEntries((all) => [...all, { id, name: item.path, size: item.file.size, file: item.file }]);
    }
    if (refused.length > 0) setRejected((all) => [...all, ...refused]);
  };

  const removeEntry = (entry: Entry) => {
    entriesCount.current -= 1;
    setEntries((all) => all.filter((item) => item.id !== entry.id));
    if (entries.length === 1) setRejected([]);
  };

  const onDrop = async (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    addFiles(await collectDropped(event.dataTransfer));
  };

  const isNew = mode === "new";
  const files = entries.map((entry) => entry.file);
  const failure = [createDraft.error, addDocuments.error].find(Boolean);
  const busy = createDraft.isPending || addDocuments.isPending;

  const back: Partial<Record<Step, Step>> = { documents: "client" };
  // Any document starts a case, and adding to an existing case needs a file too.
  const canLeaveDocuments = entries.length > 0;

  const onDone = (caseId: string, caseName: string, list: FileResult[]) => {
    setPicked({ case_id: caseId, name: caseName });
    setResults(list);
    setStep("done");
  };
  // Back to Add documents for the case that was just created, so more files go to the same case.
  const addMore = () => {
    setMode("existing");
    setEntries([]);
    setRejected([]);
    setResults([]);
    entriesCount.current = 0;
    addDocuments.reset();
    setStep("documents");
  };
  const confirm = () =>
    createDraft.mutate(files, { onSuccess: (data) => { setDraft(data); setStep("processing"); } });
  const addToCase = () =>
    picked && addDocuments.mutate({ caseId: picked.case_id, files }, { onSuccess: (data) => onDone(data.case_id, picked.name, data.results) });
  const submitted = (name: string) => {
    if (!draft) return;
    setPicked({ case_id: draft.case_id, name });
    setResults(draft.results);
    setDraft(null);
    setStep("done");
  };
  const advance = () => setStep((current) => (current === "processing" ? "name" : current));

  const documentsPane = (
    <>
              {!isNew && <CaseRow picked={picked} onEdit={() => setStep("client")} />}
              <div
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={`flex flex-wrap items-center gap-3 rounded-2xl border-2 border-dashed p-3 ${
                  dragging ? "border-[var(--accent)] bg-[var(--soft)]" : "border-[var(--line)]"
                }`}
              >
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[var(--accent)] text-white" aria-hidden>
                  &#8679;
                </span>
                <span className="min-w-0 flex-1">
                  <b className="block">{isNew ? "Drop any documents or a folder" : "Drop the client's files or a folder"}</b>
                  <small className="text-[var(--muted)]">{TYPE_HINT}, up to {MAX_BYTES / 1024 / 1024} MB each. Other files are left out.</small>
                </span>
                <button
                  type="button"
                  onClick={() => input.current?.click()}
                  className="rounded-lg border-2 border-[var(--accent)] bg-[var(--surface)] px-3.5 py-1.5 text-sm font-semibold text-[var(--accent)] hover:bg-[var(--soft)]"
                >
                  Browse files
                </button>
                <button
                  type="button"
                  onClick={() => folderInput.current?.click()}
                  className="rounded-lg border-2 border-[var(--accent)] bg-[var(--surface)] px-3.5 py-1.5 text-sm font-semibold text-[var(--accent)] hover:bg-[var(--soft)]"
                >
                  Browse a folder
                </button>
                <input
                  ref={input}
                  type="file"
                  multiple
                  accept={ACCEPT}
                  hidden
                  onChange={(event) => {
                    if (event.target.files) addFiles(fromFileList(event.target.files));
                    event.target.value = "";
                  }}
                />
                <input
                  ref={folderInput}
                  type="file"
                  hidden
                  {...({ webkitdirectory: "" } as object)}
                  onChange={(event) => {
                    if (event.target.files) addFiles(fromFileList(event.target.files));
                    event.target.value = "";
                  }}
                />
              </div>
              {rejected.length > 0 && (
                <div className="mt-3 rounded-xl bg-[var(--bad-soft)] px-3 py-2 text-sm text-[var(--bad)]" role="alert">
                  <b>
                    {rejected.length} {rejected.length === 1 ? "file" : "files"} left out
                  </b>
                  <ul className="mt-1 max-h-24 overflow-auto">
                    {rejected.map((item, index) => (
                      <li key={`${item.path}-${index}`} className="flex gap-3">
                        <span className="min-w-0 flex-1 truncate" title={item.path}>
                          {item.path}
                        </span>
                        <span>{item.reason}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="mt-3 text-sm text-[var(--muted)]">
                {isNew ? "The AI reads the files as soon as you start processing. Documents are evidence." : "The files are read automatically after they are uploaded."} Call notes, chats and emails are read as claims, and a Zoom note can start a new client draft. The server checks each file again.
              </p>
              <ul className="mt-2 min-h-24 flex-1 overflow-y-auto" aria-label="Added files">
                {entries.map((entry) => (
                  <FileLine key={entry.id} entry={entry} onRemove={() => removeEntry(entry)} />
                ))}
              </ul>
              {failure && (
                <p className="mt-3 rounded-xl bg-[var(--bad-soft)] px-3 py-2 text-sm text-[var(--bad)]" role="alert">
                  Could not add the documents: {failure.message}
                </p>
              )}
            </>
  );

  return (
    <div className="fixed inset-0 z-30 grid place-items-center bg-[#14213a]/60 p-4">
      <div role="dialog" aria-modal="true" aria-labelledby="upload-title" className="flex h-[min(44rem,calc(100vh-2rem))] w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-[var(--surface)] shadow-xl">
        <div className={`min-h-0 flex-1 p-6 pb-3 ${step === "done" || step === "documents" || step === "processing" || step === "name" ? "flex flex-col overflow-hidden" : "overflow-auto"}`}>
          <div className="flex items-start justify-between">
            <div>
              <h2 id="upload-title" className="text-2xl font-bold">
                {forCase ? "Add documents" : "Create new case"}
              </h2>
              <p className="text-[var(--muted)]">
                {isNew ? "Add any document, including call notes, WhatsApp chats and emails. The AI reads everything as soon as you start processing." : "Add documents to the case. Anything missing stays marked."}
              </p>
            </div>
            <button type="button" onClick={requestClose} className="text-[var(--muted)]">
              Cancel
            </button>
          </div>
          <StepPills current={step} mode={mode} />

          {step === "client" && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <ModeCard title="New case" note="Add any document you have, or none. The server assigns the case number. Missing documents are marked and can be added later." selected={isNew} onSelect={() => setMode("new")} />
                <ModeCard title="Existing case" note="Pick a case by its number or the client name and add more documents." selected={!isNew} onSelect={() => setMode("existing")} />
              </div>
              {!isNew && <ClientPicker picked={picked} onPick={setPicked} />}
            </>
          )}

          {step === "documents" && documentsPane}

          {step === "processing" && draft && <ProcessingStep draft={draft} onContinue={advance} />}

          {step === "name" && draft && <NameStep caseId={draft.case_id} onSubmitted={submitted} />}

          {step === "done" && picked && <Done caseId={picked.case_id} results={results} />}
        </div>

        <div className="flex items-center gap-3 border-t border-[var(--line)] px-6 py-3">
          {back[step] && <GhostButton onClick={() => setStep(back[step] as Step)}>&larr; Back</GhostButton>}
          <span className="ml-auto text-sm text-[var(--muted)]">
            {step === "documents" && (busy ? (isNew ? "Starting..." : "Uploading...") : `${entries.length} ${entries.length === 1 ? "file" : "files"} added`)}
          </span>
          {step === "client" && (
            <PrimaryButton disabled={!isNew && picked === null} onClick={() => setStep("documents")}>
              {isNew ? "Next: intake and documents" : "Next: add documents"}
            </PrimaryButton>
          )}
          {step === "documents" && (
            <PrimaryButton disabled={!canLeaveDocuments || busy} onClick={isNew ? confirm : addToCase}>
              {isNew ? "Upload & Process" : "Add documents"}
            </PrimaryButton>
          )}
          {step === "done" && picked && (
            <>
              <GhostButton onClick={addMore}>&larr; Add more files</GhostButton>
              <GhostButton onClick={onClose}>Close</GhostButton>
              <PrimaryButton
                onClick={() => {
                  navigate(`/cases/${picked.case_id}`);
                  onClose();
                }}
              >
                Open case
              </PrimaryButton>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
