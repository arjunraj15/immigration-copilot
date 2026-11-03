// Mock data for the design phase only. Replace each export with an API call (docs/PLAN.md section 8).
// Names and ids are samples from the design. Never rely on them in real code.
import type { Role } from "../../lib/role";

// Result text shown in each step stamp once the step is done. issue marks a red stamp.
export type StepResult = { text?: string; issue?: boolean };
export const STEP_RESULTS: Record<Role, StepResult[]> = {
  paralegal: [{}, {}, {}, {}, {}, {}, {}],
  attorney: [{}, {}, {}, {}, {}, {}],
};

export const INITIAL_STEP: Record<Role, number> = { paralegal: 2, attorney: 2 };
