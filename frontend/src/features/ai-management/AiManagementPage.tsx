import { useState } from "react";

import Icon, { type IconName } from "../../components/Icon";
import KpiTiles from "./KpiTiles";
import PromptCreateForm from "./PromptCreateForm";
import PromptEditor, { type Tab } from "./PromptEditor";
import PromptList, { type ListFilter } from "./PromptList";
import RecentRuns from "./RecentRuns";
import NewTypeFromUpload from "./NewTypeFromUpload";
import ReviewList from "./ReviewList";
import TestPanel from "./TestPanel";
import VersionHistory from "./VersionHistory";
import { BUTTON, BUTTON_QUIET, INPUT } from "./fieldStyles";
import { useAiStats, useDeletePrompt, usePrompt, usePromptState, useRenamePrompt, useReview } from "./hooks";
import type { PromptHealth, VersionCreate } from "./types";

type Pending = "disable" | "delete" | null;

const CONFIRM_TEXT = {
  disable: "Disable this prompt? Reads fall back to the Unknown document type until it is enabled again.",
  delete: "Delete this prompt? Its versions and runs stay on record.",
};

// Disable and Delete ask first. Enable restores the prompt, so it does not.
function Controls({ promptKey, enabled, onDeleted }: { promptKey: string; enabled: boolean; onDeleted: () => void }) {
  const toggle = usePromptState(promptKey);
  const remove = useDeletePrompt(promptKey);
  const [pending, setPending] = useState<Pending>(null);
  const failure = toggle.error ?? remove.error;
  const confirm = () => {
    if (pending === "disable") toggle.mutate("disable", { onSuccess: () => setPending(null) });
    if (pending === "delete") remove.mutate(undefined, { onSuccess: onDeleted });
  };
  const busy = toggle.isPending || remove.isPending;
  return (
    <div className="flex flex-col items-end gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        {enabled ? (
          <button type="button" className={`${BUTTON_QUIET} inline-flex items-center gap-1.5`} disabled={busy} onClick={() => setPending("disable")}>
            <Icon name="pause" /> Disable
          </button>
        ) : (
          <button type="button" className={`${BUTTON_QUIET} inline-flex items-center gap-1.5`} disabled={busy} onClick={() => toggle.mutate("enable")}>
            <Icon name="play" /> Enable
          </button>
        )}
        <button type="button" className={`${BUTTON_QUIET} inline-flex items-center gap-1.5 text-[var(--bad)]`} disabled={busy} onClick={() => setPending("delete")}>
          <Icon name="trash" /> Delete
        </button>
      </div>
      {pending && (
        <div className="flex flex-wrap items-center justify-end gap-2 rounded-xl bg-[var(--soft)] px-3 py-2" role="alertdialog" aria-label="Confirm">
          <span className="text-sm">{CONFIRM_TEXT[pending]}</span>
          <button type="button" className={BUTTON} disabled={busy} onClick={confirm}>
            Confirm {pending}
          </button>
          <button type="button" className={BUTTON_QUIET} onClick={() => setPending(null)}>
            Cancel
          </button>
        </div>
      )}
      {failure && <p role="alert" className="text-sm text-[var(--bad)]">{failure.message}</p>}
    </div>
  );
}

function TypeName({ promptKey, title }: { promptKey: string; title: string }) {
  const rename = useRenamePrompt(promptKey);
  const [name, setName] = useState(title);
  return (
    <form
      className="mt-2 space-y-1.5"
      onSubmit={(e) => {
        e.preventDefault();
        rename.mutate(name.trim());
      }}
    >
      <label className="block text-xs text-[var(--muted)]" htmlFor="type-name">
        Document type name
      </label>
      <div className="flex gap-2">
        <input id="type-name" className={`${INPUT} max-w-xs`} value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
        <button type="submit" className={BUTTON} disabled={rename.isPending || !name.trim() || name.trim() === title}>
          Save name
        </button>
      </div>
      {rename.error && <p role="alert" className="text-sm text-[var(--bad)]">{rename.error.message}</p>}
    </form>
  );
}

const TABS: { id: Tab; label: string; icon: IconName }[] = [
  { id: "prompt", label: "Prompt", icon: "form" },
  { id: "fields", label: "Output fields", icon: "steps" },
  { id: "model", label: "Model", icon: "cpu" },
  { id: "hist", label: "History", icon: "clock" },
  { id: "runs", label: "Recent runs", icon: "status" },
];

function DisabledBanner({ promptKey }: { promptKey: string }) {
  const toggle = usePromptState(promptKey);
  return (
    <div role="status" className="my-2.5 flex flex-none items-center gap-2.5 rounded-xl bg-[#e4e6ec] px-3 py-2 font-semibold text-[#454c5e]">
      <Icon name="ban" className="h-[22px] w-[22px]" />
      <span>Disabled. Reads fall back to the Unknown document type until it is enabled again.</span>
      <button type="button" className={`${BUTTON} ml-auto inline-flex items-center gap-1.5`} disabled={toggle.isPending} onClick={() => toggle.mutate("enable")}>
        <Icon name="play" /> Enable
      </button>
    </div>
  );
}

function Detail({ promptKey, health, onDeleted, onDraft }: { promptKey: string; health: PromptHealth | undefined; onDeleted: () => void; onDraft: (draft: VersionCreate | null) => void }) {
  const { data, isLoading, error } = usePrompt(promptKey);
  const [tab, setTab] = useState<Tab>("prompt");
  if (isLoading) return <p className="text-sm text-[var(--muted)]">Loading prompt</p>;
  if (error || !data) return <p className="text-sm text-[var(--bad)]">Could not load this prompt.</p>;
  const failed = health?.failed ?? 0;
  return (
    <>
      <header className="flex flex-none flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div>
          <h1 className={`text-[22px] font-bold ${data.enabled ? "" : "text-[var(--muted)]"}`}>
            {data.title}
            {data.category === "UNKNOWN" && <small className="ml-2 rounded border border-[var(--line)] px-1.5 text-xs font-normal text-[var(--muted)]">Unknown fallback</small>}
          </h1>
          <p className="font-mono text-xs text-[var(--muted)]">
            {data.key} · {data.step} · {!data.enabled ? "disabled" : data.active_version ? `active v${data.active_version}` : "no active version"}
          </p>
          {data.recognition_hint && <p className="mt-1 text-sm text-[var(--muted)]">{data.recognition_hint}</p>}
        </div>
        {!data.protected && <Controls promptKey={data.key} enabled={data.enabled} onDeleted={onDeleted} />}
      </header>
      {!data.enabled && <DisabledBanner promptKey={data.key} />}
      <div className={`flex min-h-0 flex-1 flex-col ${data.enabled ? "" : "pointer-events-none select-none opacity-50 grayscale"}`}>
        {data.enabled && failed > 0 && (
          <p className="mt-2.5 flex-none rounded-[10px] bg-[var(--warn-soft)] px-2.5 py-[7px] text-[13px] text-[var(--warn)]">
            {failed} failed {failed === 1 ? "run" : "runs"} in the last 7 days. Open Recent runs to see why.
          </p>
        )}
        <div className="mt-2.5 flex flex-none gap-0.5 self-start rounded-xl bg-[var(--soft)] p-[3px]" role="tablist">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              onClick={() => setTab(item.id)}
              className={`inline-flex items-center gap-1.5 rounded-[9px] px-3 py-1 text-sm ${tab === item.id ? "bg-[var(--surface)] font-semibold shadow-sm" : "text-[var(--muted)]"}`}
            >
              <Icon name={item.icon} /> {item.label}
            </button>
          ))}
        </div>
        {/* The key remounts the editor after each activation so it reloads the active version. */}
        <PromptEditor
          key={`${data.key}-${data.active_version}`}
          prompt={data}
          tab={tab}
          onDraft={onDraft}
          top={data.key !== "doc.classify" ? <TypeName key={data.title} promptKey={data.key} title={data.title} /> : undefined}
        >
          {tab === "hist" ? <VersionHistory promptKey={data.key} activeVersion={data.active_version} /> : <RecentRuns promptKey={data.key} />}
        </PromptEditor>
      </div>
    </>
  );
}

const PANE = "min-h-0 rounded-[14px] bg-[var(--surface)] p-3 shadow-sm max-lg:max-h-[70vh] max-lg:min-h-[20rem]";

export default function AiManagementPage() {
  const [selected, setSelected] = useState<string | null>("doc.classify");
  const [creating, setCreating] = useState(false);
  const [view, setView] = useState<"prompts" | "review">("prompts");
  // The upload a new document type is being drafted from. Set from the review queue.
  const [newTypeFor, setNewTypeFor] = useState<string | null>(null);
  const [filter, setFilter] = useState<ListFilter>("all");
  const [draft, setDraft] = useState<VersionCreate | null>(null);
  const stats = useAiStats().data;
  // Only the counts are needed for the tiles, so ask for one row.
  const counts = useReview({ kind: "all", q: "", page: 1, pageSize: 1 }).data?.counts;
  const needType = counts ? counts.missed + counts.quarantined : 0;
  const pick = (key: string | null) => {
    setSelected(key);
    setCreating(false);
    setDraft(null);
  };
  const openReview = () => setView("review");
  const showFailed = () => {
    setView("prompts");
    setFilter("attn");
  };
  return (
    <main className="flex flex-col p-4 lg:h-[calc(100vh-3.75rem)]">
      <KpiTiles stats={stats} needType={needType} onFailed={showFailed} onNeedType={openReview} />
      {view === "review" ? (
        <section className="min-h-0 flex-1 overflow-auto rounded-[14px] bg-[var(--surface)] p-4" aria-label="Review">
          <button type="button" className={`${BUTTON_QUIET} mb-3 inline-flex items-center gap-1.5`} onClick={() => setView("prompts")}>
            <Icon name="arrow" className="h-4 w-4 rotate-180" /> Back to prompts
          </button>
          {newTypeFor ? (
            <NewTypeFromUpload
              uploadId={newTypeFor}
              onClose={() => setNewTypeFor(null)}
              onOpenType={(key) => {
                setNewTypeFor(null);
                setView("prompts");
                pick(key);
              }}
            />
          ) : (
            <ReviewList onAddType={setNewTypeFor} />
          )}
        </section>
      ) : (
        <div className="grid min-h-0 flex-1 items-stretch gap-3 lg:grid-cols-[280px_minmax(0,1fr)_400px] max-lg:grid-cols-1">
          <aside className={`${PANE} flex flex-col gap-2 overflow-hidden`} aria-label="Prompts">
            <PromptList
              selected={selected}
              onSelect={pick}
              onAdd={() => setCreating(true)}
              stats={stats}
              filter={filter}
              onFilter={setFilter}
              needType={needType}
              onReview={openReview}
            />
          </aside>
          <section className={`${PANE} flex flex-col overflow-auto`} aria-label="Editor">
            {creating ? (
              <PromptCreateForm onCreated={pick} onCancel={() => setCreating(false)} />
            ) : selected ? (
              <Detail key={selected} promptKey={selected} health={stats?.by_prompt[selected]} onDeleted={() => pick(null)} onDraft={setDraft} />
            ) : (
              <p className="text-sm text-[var(--muted)]">Pick a prompt to edit, test or roll back.</p>
            )}
          </section>
          <aside className={`${PANE} overflow-auto`} aria-label="Test panel">
            {selected && !creating ? (
              <TestPanel key={selected} promptKey={selected} draft={draft} health={stats?.by_prompt[selected]} onClearDraft={() => setDraft(null)} />
            ) : (
              <p className="text-sm text-[var(--muted)]">Pick a prompt to test it here.</p>
            )}
          </aside>
        </div>
      )}
    </main>
  );
}
