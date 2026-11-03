// One list of steps per role. Add or reorder steps here. The stepper and the step body both read it.
import type { ComponentType } from "react";

import type { Role } from "../../../lib/role";
import ClientReplyReviewStep from "./ClientReplyReviewStep";
import ClientReplyStep from "./ClientReplyStep";
import DeadlineDecisionStep from "./DeadlineDecisionStep";
import DeadlinesStep from "./DeadlinesStep";
import DecisionStep from "./DecisionStep";
import DocumentsFactsStep from "./DocumentsFactsStep";
import ExceptionsStep from "./ExceptionsStep";
import FormDraftStep from "./FormDraftStep";
import OverviewStep from "./OverviewStep";
import PacketStep from "./PacketStep";
import ReadingStep from "./ReadingStep";
import SendStep from "./SendStep";

export type StepDef = { key: string; label: string; Component: ComponentType };

export const STEPS: Record<Role, StepDef[]> = {
  paralegal: [
    { key: "documents", label: "Documents", Component: ReadingStep },
    { key: "exceptions", label: "Exceptions", Component: ExceptionsStep },
    { key: "form", label: "Form draft", Component: FormDraftStep },
    { key: "deadlines", label: "Deadlines", Component: DeadlinesStep },
    { key: "reply", label: "Client reply", Component: ClientReplyStep },
    { key: "packet", label: "Packet", Component: PacketStep },
    { key: "send", label: "Send", Component: SendStep },
  ],
  attorney: [
    { key: "overview", label: "Overview", Component: OverviewStep },
    { key: "docs-facts", label: "Documents and facts", Component: DocumentsFactsStep },
    { key: "exceptions", label: "Exceptions", Component: ExceptionsStep },
    { key: "deadline", label: "Deadline", Component: DeadlineDecisionStep },
    { key: "reply", label: "Client reply", Component: ClientReplyReviewStep },
    { key: "decision", label: "Decision", Component: DecisionStep },
  ],
};
