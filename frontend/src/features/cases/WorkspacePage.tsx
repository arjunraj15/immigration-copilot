import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { useRole, type Role } from "../../lib/role";
import LegalFeedback from "../review/LegalFeedback";
import CaseHeader, { type CaseTab } from "./CaseHeader";
import CaseQueue from "./CaseQueue";
import DeskOverview from "./DeskOverview";
import { INITIAL_STEP } from "./mockData";
import { useRefreshWhenReadingDone } from "./useCaseDocuments";
import { useCaseInfo } from "./useCases";
import StepBody from "./StepBody";
import { useSteps } from "./steps/useSteps";
import Stepper from "./Stepper";
import ActivityTab from "./tabs/ActivityTab";
import CommunicationTab from "./tabs/CommunicationTab";
import DocumentsTab from "./tabs/DocumentsTab";
import TimelineTab from "./tabs/TimelineTab";

const QUEUE_KEY = "casedesk.caseListOpen";

// The case list is hidden by default so the case gets the full width. The choice is remembered in this browser.
function readQueueOpen(): boolean {
  try {
    return localStorage.getItem(QUEUE_KEY) === "1";
  } catch {
    return false;
  }
}

const TAB_LABEL: Record<CaseTab, string> = {
  steps: "Steps",
  documents: "Documents",
  timeline: "Timeline",
  activity: "Activity",
  communication: "Communication",
};

// The home page has the full width. With a case open, the case queue sits on the left.
export default function WorkspacePage() {
  const { caseId } = useParams();
  const { role } = useRole();
  // A link such as /cases/CASE-0001?tab=documents opens that tab.
  const params = useSearchParams()[0];
  const requested = params.get("tab") ?? "";
  // A link such as ?step=reply opens that step of the current role on the Steps tab.
  const wantedStep = params.get("step") ?? "";
  const fromLink: CaseTab = (Object.keys(TAB_LABEL) as CaseTab[]).find((key) => key === requested) ?? "steps";
  const [tab, setTab] = useState<CaseTab>(fromLink);
  const [queueOpen, setQueueOpen] = useState(readQueueOpen);
  const toggleQueue = () =>
    setQueueOpen((open) => {
      try {
        localStorage.setItem(QUEUE_KEY, open ? "0" : "1");
      } catch {
        // Storage can be blocked. The choice then lasts until reload.
      }
      return !open;
    });
  const [steps, setSteps] = useState<Record<Role, number>>(INITIAL_STEP);
  // With no case in the address, show the desk overview instead of opening a case.
  const selectedId = caseId;
  // Show the case body only when the server has opened the case for this user.
  const info = useCaseInfo(selectedId);
  const opened = info.isSuccess;
  // The AI reads uploaded files after the upload finishes, so refresh every view of this case when the last one is done.
  useRefreshWhenReadingDone(opened ? selectedId : undefined);

  useEffect(() => {
    setTab(fromLink);
  }, [role, fromLink]);

  const roleSteps = useSteps();
  const stepIndex = Math.min(steps[role], roleSteps.length - 1);
  const setStep = (index: number) => setSteps((all) => ({ ...all, [role]: index }));

  useEffect(() => {
    const index = roleSteps.findIndex((step) => step.key === wantedStep);
    if (index < 0) return;
    setTab("steps");
    setSteps((all) => ({ ...all, [role]: index }));
  }, [role, wantedStep, roleSteps.length]);

  return (
    <>
      <main className={`grid grid-cols-[minmax(0,1fr)] items-start gap-4 p-4 ${selectedId ? `lg:h-[calc(100dvh-55px)] lg:items-stretch lg:overflow-hidden ${queueOpen ? "lg:grid-cols-[300px_minmax(0,1fr)]" : ""}` : ""}`}>
        {selectedId && queueOpen && <CaseQueue selectedId={selectedId} />}
        {selectedId ? (
          <section className="flex min-h-0 min-w-0 flex-col rounded-2xl bg-[var(--surface)] px-4 pb-3" aria-label="Case view">
            <div className="sticky top-0 z-[5] shrink-0 bg-[var(--surface)] pt-3 lg:static">
              <CaseHeader
                caseId={selectedId}
                tab={tab}
                onTab={setTab}
                queueOpen={queueOpen}
                onToggleQueue={toggleQueue}
                crumbs={[{ label: "Cases", to: "/" }, { label: info.data?.name ?? selectedId }, { label: TAB_LABEL[tab] }]}
              />
              {opened && <LegalFeedback caseId={selectedId} />}
              {opened && tab === "steps" && <Stepper current={stepIndex} onSelect={setStep} />}
            </div>
            <div className={`min-h-0 flex-1 ${tab === "steps" ? "overflow-hidden" : "overflow-auto"}`}>
              {opened && tab === "steps" && <StepBody current={stepIndex} onChange={setStep} />}
              {opened && tab === "documents" && <DocumentsTab />}
              {opened && tab === "timeline" && <TimelineTab caseId={selectedId} />}
              {opened && tab === "activity" && <ActivityTab caseId={selectedId} />}
              {opened && tab === "communication" && <CommunicationTab caseId={selectedId} />}
            </div>
          </section>
        ) : (
          <DeskOverview />
        )}
      </main>
    </>
  );
}
