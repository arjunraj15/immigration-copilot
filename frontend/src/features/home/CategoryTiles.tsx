import type { Option } from "./useHome";
import { TILE } from "./categoryTones";

// One tile for each category of case, with how many cases are in it. The colour code is the dot and the number. A tile filters the table
// and a second click clears it. The counts and the order come from the server, most urgent first.
export default function CategoryTiles({ reasons, active, onPick }: { reasons: Option[]; active: string; onPick: (reason: string) => void }) {
  const shown = reasons.filter((option) => option.count > 0 || option.value === active);
  return (
    <div className="mb-2 flex flex-wrap gap-1.5" role="group" aria-label="Case categories. Each tile filters the table">
      {shown.map((option) => {
        const look = TILE[option.tone ?? "muted"];
        const picked = active === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={picked}
            onClick={() => onPick(picked ? "" : option.value)}
            title={`${option.count} ${option.count === 1 ? "case" : "cases"}: ${option.label}`}
            className={`flex min-w-[6.5rem] items-center gap-2 rounded-xl border px-2.5 py-1.5 text-left hover:bg-[var(--soft)] ${
              picked ? "border-[var(--accent)] bg-[var(--soft)]" : "border-[var(--line)] bg-[var(--surface)]"
            }`}
          >
            <span className={`h-2 w-2 shrink-0 rounded-full ${look.dot}`} aria-hidden />
            <b className={`text-lg leading-none ${look.number}`}>{option.count}</b>
            <span className="text-xs">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}
