import Icon, { type IconName } from "../../components/Icon";
import type { AiStats } from "./types";

type Tone = "plain" | "ai" | "warn" | "bad";

const BADGE: Record<Tone, string> = {
  plain: "bg-[var(--soft)] text-[var(--accent)]",
  ai: "bg-[var(--ai-soft)] text-[var(--ai)]",
  warn: "bg-[var(--warn-soft)] text-[var(--warn)]",
  bad: "bg-[var(--bad-soft)] text-[var(--bad)]",
};
const TILE = "flex flex-col gap-3.5 rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-[18px] py-4 text-left";

type TileProps = { icon: IconName; title: string; value: string; note: string; noteClass?: string; tone: Tone; onClick?: () => void };

function Tile({ icon, title, value, note, noteClass = "text-[var(--muted)]", tone, onClick }: TileProps) {
  const body = (
    <>
      <span className="flex items-center gap-2.5 text-sm">
        <span className={`grid h-[34px] w-[34px] place-items-center rounded-full ${BADGE[tone]}`}>
          <Icon name={icon} className="h-[17px] w-[17px]" />
        </span>
        {title}
      </span>
      <span className="flex flex-wrap items-baseline gap-2.5">
        <b className="text-[32px] font-semibold leading-none">{value}</b>
        <span className={`text-xs ${noteClass}`}>{note}</span>
      </span>
    </>
  );
  if (!onClick) return <div className={TILE}>{body}</div>;
  return (
    <button type="button" onClick={onClick} className={`${TILE} hover:border-[var(--accent)]`}>
      {body}
    </button>
  );
}

function weekChange(now: number, prev: number): string {
  if (!prev) return "last 7 days";
  const change = Math.round(((now - prev) / prev) * 100);
  return `${change >= 0 ? "↑" : "↓"} ${Math.abs(change)}% vs last week`;
}

function failedChange(now: number, prev: number): { text: string; className: string } {
  if (now === prev) return { text: "same as last week", className: "text-[var(--muted)]" };
  const down = now < prev;
  return { text: `${down ? "↓" : "↑"} ${Math.abs(now - prev)} vs last week`, className: down ? "text-[var(--ok)]" : "text-[var(--bad)]" };
}

type Props = { stats: AiStats | undefined; needType: number; onFailed: () => void; onNeedType: () => void };

export default function KpiTiles({ stats, needType, onFailed, onNeedType }: Props) {
  const failed = stats ? failedChange(stats.failed, stats.failed_prev) : null;
  return (
    <div className="mb-3.5 grid grid-cols-2 gap-3.5 lg:grid-cols-4">
      <Tile icon="documents" title="Prompts" tone="plain" value={String(stats?.prompts ?? "")} note={`${stats?.enabled ?? 0} enabled`} />
      <Tile icon="ai" title="AI calls" tone="ai" value={(stats?.runs ?? 0).toLocaleString("en-US")} note={stats ? weekChange(stats.runs, stats.runs_prev) : ""} noteClass={stats && stats.runs >= stats.runs_prev ? "text-[var(--ok)]" : "text-[var(--muted)]"} />
      <Tile icon="exceptions" title="Failed runs" tone="warn" value={String(stats?.failed ?? "")} note={failed?.text ?? ""} noteClass={failed?.className} onClick={onFailed} />
      <Tile icon="tag" title="Need a type" tone="bad" value={String(needType)} note="documents waiting" onClick={onNeedType} />
    </div>
  );
}
