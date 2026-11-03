# Frontend handoff

Design is frozen. Build the React app to match `design/variant-a-FROZEN.html`. Open that file in a browser and click through it first. The 11 target screens are in `design/reference/`.

## What exists now

Every screen from the frozen design is built in React and runs on mock data from `src/features/cases/mockData.ts`. Nothing calls the API yet. The remaining work is to replace each mock export with a TanStack Query call through `src/api/client.ts` and to add the real behavior (upload, propose, approve, chat).

Shared pieces: `src/components/Stamp.tsx` has the stamp, status chip, source chip and buttons. `src/features/cases/docViewer.tsx` opens the document drawer from any file row.

- Header with the Paralegal and Attorney switch. The switch sets the accent color and the acting user (`OPS-01` or `LEGAL-01`) through `src/lib/role.tsx`.
- Three column page in `src/features/cases/WorkspacePage.tsx`: case queue, case view, case assistant.
- Stepper and step body driven by one list in `src/features/cases/steps/registry.ts`.
- One file per step, per tab and per panel, so people can work in parallel without merge conflicts.
- Design tokens as CSS variables in `src/index.css`. Light and dark both work.

## Run it

```bash
cp .env.example .env
make up
```

Open the frontend port from `.env.example`. Do not install Node locally (rules.md section 7).

## Files to wire to the API

Each row is one file. Different people can take different rows without merge conflicts.

| File | Build from (function in the design file) | Data |
|---|---|---|
| `features/cases/CaseQueue.tsx` | `queue()` | `GET /api/cases` |
| `features/cases/CaseHeader.tsx` | `render()` header block | `GET /api/cases/{id}` |
| `features/cases/Stepper.tsx` | `steppers()` | step results from the case |
| `features/cases/steps/ReadingStep.tsx` | `P.paralegal0` | documents and read status |
| `features/cases/steps/FactsStep.tsx` | `P.paralegal1` | `GET /api/cases/{id}/facts` and `/conflicts` |
| `features/cases/steps/FormDraftStep.tsx` | `P.paralegal2` | form draft |
| `features/cases/steps/DeadlinesStep.tsx` | `P.paralegal3` | events and deadline proposal |
| `features/cases/steps/ClientReplyStep.tsx` | `P.paralegal4` | reply draft |
| `features/cases/steps/SendStep.tsx` | `P.paralegal5` | `POST /api/proposals` |
| `features/cases/steps/OverviewStep.tsx` | `P.attorney0` | case summary |
| `features/cases/steps/DocumentsFactsStep.tsx` | `P.attorney1` | documents and facts |
| `features/cases/steps/DeadlineDecisionStep.tsx` | `P.attorney2` | `POST /api/proposals/{id}/review` |
| `features/cases/steps/ClientReplyReviewStep.tsx` | `P.attorney3` | reply draft |
| `features/cases/steps/DecisionStep.tsx` | `P.attorney4` | `POST /api/proposals/{id}/review` |
| `features/cases/tabs/DocumentsTab.tsx` | `docs()` | documents with outcomes |
| `features/cases/tabs/TimelineTab.tsx` | `time()` | events |
| `features/cases/tabs/ActivityTab.tsx` | `act()` | `GET /api/cases/{id}/audit` and `/audit/verify` |
| `features/cases/DocumentDrawer.tsx` | `openDoc()` and the drawer markup | page image and read fields |
| `features/chat/AssistantPanel.tsx` | `chatPane()` | chat endpoint |

API shapes are in `docs/PLAN.md` section 8. Change them there in the same commit as the code.

## Rules that matter most for this work

1. All API calls go through `src/api/client.ts`. No `fetch` in components.
2. Server state uses TanStack Query. Local UI state uses `useState` or context.
3. Every status shows a pill or stamp with a reason. Never color alone. Show a source chip (claim or evidence) next to every value.
4. No component computes a date, a conflict or a permission. The backend does. The UI only shows results.
5. Client replies always show `DRAFT, NOT SENT`. Form drafts always show `DRAFT - NOT FOR FILING`.
6. No outcome prediction or legal advice in any copy.
7. No new UI library. Tailwind plus small hand-made components.
8. Never use em-dashes or semicolons in UI copy, comments or commit messages.
9. Never hardcode case ids, names or dates. The sample names in the design are only examples.

## Open questions

- The design header has no menu for Upload, Exceptions, Review and Status. The scaffold adds plain text links on the right. Confirm or replace.
- Real login does not exist. The role switch maps to `OPS-01` and `LEGAL-01`. Add more actors if the demo needs them.
- Pages that stay as they are for now: `upload`, `exceptions`, `review`, `status`.
