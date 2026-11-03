import Icon from "../../components/Icon";
import { KPIS, type KpiKey } from "./useHome";

const NUMBER_TONE = { ok: "", bad: "text-[var(--bad)]", warn: "text-[var(--warn)]", ai: "text-[var(--ai)]", muted: "" };

// Five tiles. Each one filters the table and a second click clears it.
export default function KpiStrip({ counts, active, onPick }: { counts: Record<KpiKey, number>; active: KpiKey | ""; onPick: (kpi: KpiKey | "") => void }) {
  return (
    <div className="mb-3 flex flex-wrap gap-1.5" role="group" aria-label="Summary tiles. Each tile filters the table">
      {KPIS.map((kpi) => (
        <button
          key={kpi.key}
          type="button"
          aria-pressed={active === kpi.key}
          onClick={() => onPick(active === kpi.key ? "" : kpi.key)}
          className={`flex min-w-[6.5rem] items-center gap-2 rounded-xl border px-2.5 py-1.5 text-left hover:bg-[var(--soft)] ${
            active === kpi.key ? "border-[var(--accent)] bg-[var(--soft)]" : "border-[var(--line)] bg-[var(--surface)]"
          }`}
        >
          <Icon name={kpi.icon} className={`h-3.5 w-3.5 shrink-0 ${NUMBER_TONE[kpi.tone]}`} />
          <b className={`text-lg leading-none ${NUMBER_TONE[kpi.tone]}`}>{counts[kpi.key]}</b>
          <span className="text-xs">{kpi.label}</span>
        </button>
      ))}
    </div>
  );
}
