import Icon from "../../../components/Icon";
import { Chip } from "../../../components/Stamp";
import { TYPE_LABEL } from "../../review/ExceptionsTable";
import { useCaseExceptions } from "../../review/useExceptions";
import Citation from "../Citation";
import { sourceKind } from "../sourceId";

const TEXT = { HIGH: "text-[var(--bad)]", MEDIUM: "text-[var(--warn)]", LOW: "text-[var(--muted)]" } as const;

// The case's missing and defective documents and its other exceptions, one small line each with an icon. A missing document
// gets a red flag. Field conflicts are not listed here, they have their own cards below with the actions to settle them.
export default function DocumentExceptions({ caseId }: { caseId: string }) {
  const list = useCaseExceptions(caseId);
  const items = (list.data?.items ?? []).filter((item) => item.type !== "FACT_CONFLICT");
  if (items.length === 0) return null;
  return (
    <section className="mb-3 rounded-2xl border border-[var(--line)] px-3.5 py-2" aria-label="Documents and other exceptions">
      <h3 className="mb-0.5 text-sm font-bold">Documents and other exceptions</h3>
      <ul>
        {items.map((item) => {
          const missing = item.type === "MISSING_DOCUMENT";
          return (
            <li key={`${item.type}-${item.title}-${item.source_ids.join(",")}`} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 border-t border-[var(--line)] py-1.5 text-sm first:border-t-0">
              <Icon name={missing ? "flag" : "exceptions"} className={`h-4 w-4 shrink-0 ${missing ? "text-[var(--bad)]" : TEXT[item.severity]}`} />
              <b className={missing ? "text-[var(--bad)]" : ""}>{item.title}</b>
              <Chip tone="muted">{TYPE_LABEL[item.type] ?? item.type}</Chip>
              <span className="min-w-0 flex-1 truncate text-xs text-[var(--muted)]" title={item.reason}>
                {item.reason}
              </span>
              {item.source_ids.filter((id) => sourceKind(id) !== "unknown").map((id) => (
                <Citation key={id} source={id} showTitle={false} />
              ))}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
