import Icon from "../../components/Icon";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useRole } from "../../lib/role";
import UploadWizard from "../upload/UploadWizard";
import { useQueue, type QueueItem } from "./useCases";

const DOT: Record<QueueItem["tone"], string> = {
  info: "bg-[var(--accent)]",
  warn: "bg-[#d79a1c]",
  bad: "bg-[var(--bad)]",
  ok: "bg-[var(--ok)]",
  ai: "bg-[var(--ai)]",
  muted: "bg-[#9aa3b8]",
};

// Left column. Upload drop card, search, then cases grouped by what the role needs to do.
export default function CaseQueue({ selectedId }: { selectedId: string }) {
  const { role } = useRole();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const [uploading, setUploading] = useState(false);
  const queue = useQueue(term);

  // Wait for a pause in typing before asking the server.
  useEffect(() => {
    const timer = setTimeout(() => setTerm(search.trim()), 250);
    return () => clearTimeout(timer);
  }, [search]);

  return (
    <aside className="min-w-0 rounded-2xl bg-[var(--surface)] p-4 lg:h-full lg:overflow-auto" aria-label="Case queue">
      {role === "paralegal" && (
        <button
          type="button"
          onClick={() => setUploading(true)}
          className="w-full rounded-xl bg-[var(--accent)] px-4 py-2.5 font-semibold text-white hover:opacity-90"
        >
          <Icon name="plus" /> Create new case
        </button>
      )}
      <input
        className="my-2.5 w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5"
        placeholder="Search by name, case or receipt number"
        aria-label="Search cases"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      {queue.isPending && <p className="px-1 text-sm text-[var(--muted)]">Loading cases...</p>}
      {queue.isError && (
        <p className="px-1 text-sm text-[var(--bad)]" role="alert">
          Could not load cases: {queue.error.message}
        </p>
      )}
      {queue.data?.groups.length === 0 && (
        <p className="px-1 text-sm text-[var(--muted)]">
          {term
            ? "No cases match your search."
            : role === "attorney"
              ? "Nothing has been sent to you yet."
              : "No cases are assigned to this user."}
        </p>
      )}
      {queue.data?.groups.map((group) => (
        <div key={group.key}>
          <div className="mx-1 mb-1.5 mt-3.5 flex justify-between text-sm font-semibold text-[var(--muted)]">
            <span>{group.title}</span>
            <span>{group.items.length}</span>
          </div>
          {group.items.map((item) => (
            <button
              key={item.case_id}
              type="button"
              onClick={() => navigate(`/cases/${item.case_id}`)}
              aria-current={item.case_id === selectedId ? "true" : undefined}
              className={`mb-1.5 flex w-full items-start gap-2.5 rounded-2xl border-2 p-2.5 text-left hover:bg-[var(--soft)] ${
                item.case_id === selectedId ? "border-[var(--accent)]" : "border-transparent"
              }`}
            >
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[var(--soft)] text-xs font-bold">
                {item.initials}
              </span>
              <span className="min-w-0 flex-1">
                <b className="flex justify-between">
                  {item.name}
                  <span className="font-normal text-[var(--muted)]">{item.number}</span>
                </b>
                <small className="block leading-snug text-[var(--muted)]">
                  <i className={`mr-1.5 inline-block h-2 w-2 rounded-full ${DOT[item.tone]}`} />
                  {item.note}
                </small>
              </span>
            </button>
          ))}
        </div>
      ))}
      {uploading && <UploadWizard onClose={() => setUploading(false)} />}
    </aside>
  );
}
