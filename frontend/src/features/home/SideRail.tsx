import { Link } from "react-router-dom";

import { Chip, SourceRef } from "../../components/Stamp";
import { DUE_LABEL, DUE_TONE, formatLong, formatStamp, relativeDays, type Activity, type Deadline } from "./useHome";

// scroll makes the body of the card scroll inside the space it is given instead of growing the card.
function Card({ title, children, scroll = false }: { title: string; children: React.ReactNode; scroll?: boolean }) {
  return (
    <section className={`rounded-2xl border border-[var(--line)] bg-[var(--surface)] ${scroll ? "flex min-h-0 flex-col" : ""}`} aria-label={title}>
      <h2 className="px-3 pb-1.5 pt-2.5 text-sm font-bold">{title}</h2>
      <div className={`px-3 pb-3 ${scroll ? "max-h-96 min-h-0 overflow-y-auto xl:max-h-none" : ""}`}>{children}</div>
    </section>
  );
}

// Deadlines for the next 14 days and the recent audit lines. Both lists come from the server as is.
// From the xl width the rail is as tall as the case table beside it and the activity list scrolls inside it, so a long
// activity list never makes the page taller than the table. Below that the rail stacks and the list is capped.
export default function SideRail({ deadlines, activity }: { deadlines: Deadline[]; activity: Activity[] }) {
  return (
    <aside className="relative min-h-0" aria-label="Deadlines and recent activity">
      <div className="grid gap-3 xl:absolute xl:inset-0 xl:grid-rows-[auto_minmax(0,1fr)] xl:overflow-y-auto">
      <Card title="Deadlines, next 14 days">
        {deadlines.length === 0 && <p className="text-sm text-[var(--muted)]">Nothing is due.</p>}
        <ul>
          {deadlines.map((item) => (
            <li key={item.case_id} className="border-t border-[var(--line)] py-1.5 first:border-t-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <b className="text-sm">{formatLong(item.date)}</b>
                <Link to={`/cases/${item.case_id}`} className="font-mono text-xs font-bold underline">
                  {item.case_id}
                </Link>
                <Chip tone={DUE_TONE[item.state]}>{DUE_LABEL[item.state]}</Chip>
              </div>
              <span className="block text-xs text-[var(--muted)]">{`${item.name}, ${relativeDays(item.days_left)}`}</span>
            </li>
          ))}
        </ul>
        <p className="mt-1.5 text-xs text-[var(--muted)]">Proposals only. Legal approval required. Calendar entries never set a deadline.</p>
      </Card>
      <Card title="Recent activity" scroll>
        {activity.length === 0 && <p className="text-sm text-[var(--muted)]">No activity on your cases yet.</p>}
        <ul>
          {activity.map((item, index) => (
            <li key={`${item.occurred_at}-${index}`} className="border-t border-[var(--line)] py-1.5 text-sm first:border-t-0">
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-[var(--muted)]">
                <span>{formatStamp(item.occurred_at)}</span>
                <Chip tone={item.tone}>{item.label}</Chip>
              </div>
              <div>
                {item.case_id && (
                  <Link to={`/cases/${item.case_id}`} className="mr-1 font-mono text-xs font-bold underline">
                    {item.case_id}
                  </Link>
                )}
                {item.title}
                {item.note && <SourceRef>{item.note}</SourceRef>}
              </div>
            </li>
          ))}
        </ul>
      </Card>
      </div>
    </aside>
  );
}
