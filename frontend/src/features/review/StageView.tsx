import { STAGE_LABEL } from "./useProposals";

export type StageValue = { from_stage: string; to_stage: string; reason: string };

// Which stage the case moves from and to, and why. Approval only allows the change, the operations user applies it.
export default function StageView({ value }: { value: StageValue }) {
  return (
    <div className="rounded-xl bg-[var(--soft)] p-3.5 text-sm">
      <p className="text-lg font-bold">
        {STAGE_LABEL[value.from_stage] ?? value.from_stage} <span aria-hidden="true">to</span> {STAGE_LABEL[value.to_stage] ?? value.to_stage}
      </p>
      <p className="mt-1">Reason: {value.reason}</p>
    </div>
  );
}
