# Immigration Case Co-Pilot Work Plan

Phased build plan for Case Desk. Run one phase at a time. A phase is finished only when every item under "Done when" passes. Read `docs/PLAN.md` and `rules.md` first. This file orders the work, `PLAN.md` describes it.

Version 2. Updated after the frozen web UI landed (`design/variant-a-FROZEN.html`, `docs/FRONTEND_HANDOFF.md`, `plans/HANDOFF.md`). Every screen already exists in React on mock data. So there is no separate "build the UI" phase any more. Each backend phase now ends by wiring the screens that show its data.

## How to run a phase

1. Branch from `dev` as `track/short-topic` (for example `core/audit-ledger`).
2. Read the "Reads first" files for the phase.
3. Build the backend items in order. Write the test for each rule before or with the code.
4. Wire the listed UI files: replace the mock export in `src/features/cases/mockData.ts` with a TanStack Query hook that calls `src/api/client.ts`. Delete the mock once nothing uses it.
5. Run `make test` and `make lint`, check `/status` is green, and click through the wired screens in the browser.
6. Tick the "Done when" list, merge to `dev`, then start the next phase.

## Phase overview

| Phase | Name | Track | Depends on | UI wired in this phase | Score area |
|---|---|---|---|---|---|
| 0 | Foundations and contracts | Shared | none | none | all |
| 1 | Audit ledger | Core | 0 | Activity tab | approvals and audit (15) |
| 2 | Starter kit import, cases and workflow | Core | 1 | Case queue, case header, role switch, timeline events | case flow (15) |
| 3 | AI layer and prompt registry | AI | 1 | none | PDF understanding (25) |
| 4 | Document pipeline and analysis run | Upload | 2, 3 | Paralegal step 1, Documents tab, document drawer, upload wizard | PDF understanding (25), triage (20) |
| 5 | Facts and conflicts | Core | 4 | Paralegal step 2, attorney step 2 | consistency (20), citations (20) |
| 6 | Form draft, deadlines and client reply | Core and AI | 5 | Paralegal steps 3 to 5, attorney step 4, timeline deadline | consistency (20), case flow (15) |
| 7 | Review, approval and apply | Core | 6 | Paralegal step 6, attorney steps 1, 3 and 5, apply screen | approvals (15), case flow (15) |
| 9 | Traps, mutation tests and hardening | All | 4 to 7 | rerun banner | all |
| 10 | Demo and submission | All | 9 | polish | demo (5) |

Phases 1 to 3 can run in parallel once phase 0 is merged. Phase 4 needs 2 and 3. Phases 5 to 7 are sequential because each one reads the output of the one before.

## Decisions to settle before phase 2

`plans/HANDOFF.md` was written for a different stack in places. Where it disagrees with `rules.md`, this plan follows `rules.md` until the team agrees otherwise.

| # | Topic | HANDOFF says | This plan does | Needs |
|---|---|---|---|---|
| 1 | Database | SQLite | PostgreSQL with pgvector (rules.md 6.1) | confirm |
| 2 | Python, React | 3.11, React 18 | 3.12, React 19, as already built | confirm |
| 3 | AI library | Claude Agent SDK | Anthropic Python SDK with structured output (rules.md 3) | confirm |
| 4 | Animation | framer-motion | CSS transitions only, no new UI library (rules.md 5.7) | confirm |
| 5 | Analysis progress | Server-sent events stream | Background job polled by the UI, with per-document events in the job (rules.md 4.6). SSE only if polling feels slow | confirm |
| 6 | Document status | `ACCEPTED`, `EXPIRED`, `STALE`, `NEEDS_TRANSLATION`, `REVIEW_REQUIRED` as statuses | Keep `upload_outcome` and add a `reason_code` (EXPIRED, STALE, NEEDS_TRANSLATION, UNREADABLE, ROTATED, WRONG_CLIENT, MIXED_CLIENTS and so on). The UI maps the reason code to its stamp | confirm |
| 7 | Attorney "use a different date" | Allowed with a reason | **Decided.** The button stays. It becomes a rejection with a reason and the attorney's date saved as a note. Only the rule-computed date can ever be activated (rules.md 2.6). Built in phase 7 | decided |
| 8 | Actors | Role switch maps to `OPS-01` and `LEGAL-01` | **Decided and built in phase 2.** The two role pills stay. An Acting as picker beside them lists every OPS and LEGAL user from the data. The queue and every permission follow the chosen user. A case is open only to its assigned users | decided |
| 9 | Test oracle | `reference/build_seed.py` and `reference/expected_results.json` | These files are not in the repo. Ask the HANDOFF author to commit them, or phase 9 writes expected results by hand | find files |
| 10 | Review date | 2026-10-23 from the rules file | Same. All date checks use `review_as_of` from `rule_sets`, never the system clock | none |

---

## Phase 0. Foundations and contracts (done)

Merged on `dev`. The starter kit mount points at `project_requirmnt/`, `docs/schema.md` is drafted, `core/contracts.py`, the error shape, the `X-Actor` check, the offline test setup with a fake Claude client, and `make lint` are in place. 12 tests pass.

Still open: the core backend owner, the hackathon length and the model limits in `PLAN.md` section 17. The `vite.config.ts` type error (`process` needs `@types/node`) came from `main` and belongs to the UI track.

---

## Phase 1. Audit ledger (done)

**Goal.** The hash-chained ledger exists before any feature writes state, and the Activity tab shows it.

**Reads first.** `rules.md` section 12, `PLAN.md` section 6.1, `design/reference/7_activity_audit_log.png`.

**Backend.**
1. Migration: `audit_log`, `audit_heads`, the trigger that blocks UPDATE, DELETE and TRUNCATE, and an app role with only INSERT and SELECT on `audit_log`.
2. `backend/app/core/audit.py` with `record(...)`: lock the chain head, compute `seq` and `row_hash` from canonical JSON plus `prev_hash`, insert, update the head, all in the caller's transaction.
3. A helper for denied attempts that writes in a separate transaction after rollback, with outcome `DENIED` and the reason.
4. Chains: one per case plus `SYSTEM`. Genesis `prev_hash` is 64 zeros.
5. Add the audit actions the Activity tab needs to `docs/schema.md`: `CASE_CREATED`, `ANALYSIS_RUN`, `AI_DRAFT`, `SUBMITTED_FOR_REVIEW`, `INFO_REQUESTED`, `CONFLICT_RESOLVED`, `DUPLICATE_IGNORED`.
6. Routes `GET /api/cases/{id}/audit` (newest first, filter by kind, paged), `GET /api/cases/{id}/audit/verify`, `GET /api/audit/verify`.
7. Each entry returns a display label and tone for the UI (Applied, Approved, Refused, Duplicate ignored, AI draft, Analysis, Data import, Proposed). The mapping lives in one backend function.
8. Head checkpoint file written outside the database, compared during verify.

**UI.** `features/cases/tabs/ActivityTab.tsx` from `ACTIVITY`. Add a "Verify chain" button that shows valid or the first broken entry.

**Done when.**
- Tests: a recorded line exists, verify returns `valid`, a superuser edit of one row makes verify report that `seq` with expected and found hashes.
- A rolled-back change leaves no audit line, and the denied attempt shows as `DENIED`.
- Two concurrent writers on one chain produce gapless `seq` values.
- No code outside `audit.py` inserts into `audit_log` (grep check in a test).
- The Activity tab lists real entries for a case and Verify shows green.

---

## Phase 2. Starter kit import, cases and workflow (done)

**Goal.** All synthetic sources are in Postgres, scoped by case, and the case queue, header and role switch run on real data.

**Reads first.** `DATA_DICTIONARY.md`, kit files `01` to `17`, HANDOFF sections 6 and 8.3, `FRONTEND_HANDOFF.md`.

**Backend.**
1. Migrations for `cases`, `intake_notes`, `messages`, `profile_fields`, `case_events`, `uploads` (from the manifest, outcome `PENDING`), `review_decisions` and `rule_sets` (document rules, deadline rules, form field map, form template). Two items moved: `jobs` is created in phase 4 where it is first used, and the PDF title to category map from HANDOFF section 1 is added in phase 4 with the reader.
2. New table `case_workflows`: `case_id`, `status` (`NEW`, `ANALYSING`, `IN_PROGRESS`, `WITH_ATTORNEY`, `INFO_REQUESTED`, `APPROVED`, `REJECTED`, `APPLIED`), `wizard_step`, `submitted_by`, `submitted_to`, `submitted_at`, `note`. Add it to `docs/schema.md`.
3. An idempotent loader keyed by source ids (`make seed`). Duplicate identical events are stored once. Seeded review decisions load as real rejections with an audit line.
4. A repository layer where every case data query requires `case_id`.
5. Replace `GET /api/actor` with `GET /api/me` (label, role, case count) and add `GET /api/actors` for the picker. A case is open only to its assigned OPS and LEGAL users. Anyone else gets 403 and a `DENIED` audit line. The case audit routes use the same check. Decision 8 is resolved here.
6. `GET /api/cases?q=&group=` returns the queue grouped for the actor's role. Paralegal groups: Approved ready to apply, Working on now, Sent back to you, New not started, With attorney. Attorney groups: Waiting for your decision, Decided this week. Each card has id, initials, name, short number, one-line note and tone. The backend writes the note text, the UI only shows it.
7. `GET /api/cases/{id}` for the header (name, case id, archetype, assigned users, portal status with its source event id). `GET /api/cases/{id}/sources`. `GET /api/cases/{id}/timeline` with portal and calendar lanes and a `kind` per event (verified, unverified, today).

**UI.** `lib/role.tsx` (calls `/api/me`), `features/cases/CaseQueue.tsx` from `QUEUE`, `CaseHeader.tsx` from `CASE_INFO`, `tabs/TimelineTab.tsx` from `TIMELINE` (events only, the proposed deadline comes in phase 6). Search in the queue box calls the API.

**Done when.**
- Running the loader twice gives the same row counts (100 cases, 603 uploads, 305 events and so on).
- Search by case id, client ref and receipt number works.
- A test asks for case A's sources with case B's id and gets nothing from A.
- Each claim source (Zoom, message, calendar event) is stored as `CLAIM`, each profile row and verified portal event as `EVIDENCE`.
- Switching Paralegal and Attorney in the header reloads the queue for that role from the API. No mock data is left in the queue, header or timeline.

---

## Phase 3. AI layer and prompt registry (done)

**Goal.** Any part of the backend can call Claude by prompt key, get validated JSON back, and every call is recorded.

**Reads first.** `rules.md` section 3, `PLAN.md` section 7, HANDOFF section 5, the `claude-api` skill for current SDK usage.

**Backend.**
1. Migrations for `prompts`, `prompt_versions`, `prompt_runs`.
2. YAML seeds in `backend/app/ai/prompts/` for the three roles in HANDOFF section 5: `doc.read` (one generic reader plus per-category variants), `case.consistency` (explains conflicts, never picks a winner), `reply.client` (client reply with intent, refusal reason and refs), plus `form.suggest_fields` and `chat.case_assistant`. Seeds load on first start when a key is missing, with a `SYSTEM` audit line.
3. Registry validation: reject any extraction schema whose fields lack `quote` and `page`.
4. Claude wrapper: build the client through `anthropic.Anthropic(...)` so the test fake works. Structured output with the version's schema, explicit `effort`, no temperature or prefill, `stop_reason` check, retry with backoff for transient errors, one bounded retry on schema failure, timeouts and token caps from config.
5. Untrusted-data envelope `<untrusted_content source="UP-000100">` for all document and message text, plus an `injection_flags` field in every reading schema. Pass `review_as_of` in the system prompt.
6. Cache by file sha256 plus prompt version. `AI_RUN_CAPTURE` switches between full capture and hashes only.
7. Every call writes a `prompt_runs` row with key, version, model, tokens, latency, input hash and status.

**UI.** None in this phase.

**Done when.**
- Tests with the fake client cover success, refusal, max tokens, malformed JSON and timeout. Each ends in a stored labelled result ("needs human review" on failure).
- A second call with the same sha256 and version hits the cache, a new version misses it.
- `grep` finds no prompt text, model id or schema in Python code outside the seed loader.
- Creating or activating a version writes a `SYSTEM` audit line.

---

## Phase 4. Document pipeline and analysis run

**Goal.** Every PDF, from the kit or a new upload, ends in exactly one outcome with a reason code, and the paralegal sees each file get its stamp as the analysis runs.

**Reads first.** `plans/Case Desk Flow.md` figure 2, HANDOFF sections 4.1 and 4.2, `04_case_document_rules.json`, reference screens 1, 5, 9 and 10.

**Backend.**
1. Text per page with `pdfplumber` (words and their boxes) or `pypdf`. When the text layer is empty or poor, render with `pdftoppm` and run Tesseract. Record the text source per page.
2. A deterministic `Label: value` parser runs first. The Claude reader runs second. When they disagree on a field, the field is unverified and the document needs review (rules R-25).
3. Category from content using the title map in `rule_sets`. Filenames and `client_supplied_type` never decide it. Add `TRANSLATION` and `UNKNOWN` categories.
4. Owner per page from the `Synthetic Matter:` line. All pages foreign gives `QUARANTINED` with reason `WRONG_CLIENT`. Some pages foreign gives `QUARANTINED` with reason `MIXED_CLIENTS` and the foreign page list. The owner case id is stored, the foreign name is never shown.
5. Status checks in the order of HANDOFF 4.1, first failing check wins: unreadable or rotated, duplicate sha256, wrong client, superseded, expired passport, stale letter, pay period, missing reference, missing translation, orphan translation. Injection text adds a `SECURITY` flag and keeps evaluating. Rule values come from `rule_sets`.
6. The `uploads` table already has `reason_code`, `owner_case_id` and `flags` (migration 0003). Add a `document_pages` table (page number, owner case id, text source, word boxes) and the `jobs` table, and the PDF title to category map as a rule set. Update `docs/schema.md`.
7. Checklist per required category: `SATISFIED`, `NOT_USABLE` with reasons, or `MISSING`. `GET /api/cases/{id}/checklist`.
8. `POST /api/cases/{id}/analyse` starts a background job and moves the workflow to `ANALYSING`. `GET /api/jobs/{id}` returns progress and one event per finished document (upload id, outcome, reason code, one-line summary).
9. `POST /api/cases` creates a case for the upload wizard. `POST /api/cases/{id}/documents` takes multipart PDFs and queues a rerun.
10. `GET /api/cases/{id}/documents`, `GET /api/cases/{id}/documents/{upload_id}/page/{n}` (page image), `.../highlights` (field boxes with confidence). A quarantined file from another client returns 403.
11. Audit lines for upload received, duplicate detected, document read, quarantined, injection flagged and analysis run.

**UI.** `steps/ReadingStep.tsx` from `READ_FILES` (polls the job, stamps land per file), `Stepper.tsx` documents result from `STEP_RESULTS`, `tabs/DocumentsTab.tsx` from `REQUIRED_DOCS` and `SET_ASIDE_REASONS`, `DocumentDrawer.tsx`, `docViewer.tsx`, `FileRow.tsx`, the upload wizard (screen 5) in `features/upload/`, and `review/ExceptionsPage.tsx`.

**Done when.**
- All 603 kit PDFs process to one outcome each, and the exceptions page shows duplicates, quarantined and superseded files with reasons.
- Pure function tests for each status check, for dedupe, for page ownership and for quote verification.
- A scanned PDF (image only) is read through OCR.
- In the browser, opening a new case runs the analysis and every file gets its stamp. The drawer opens a page with highlight boxes.
- CASE-0003, CASE-0026 quarantine works and no foreign name appears anywhere in the UI.

---

## Phase 5. Facts and conflicts

**Goal.** One fact table holds every value from every source with its citation, conflicts are shown side by side, and only a human resolves them.

**Reads first.** Crash course chapters 6 and 7, HANDOFF section 4.3, `08_form_field_map.json`, reference screen 2.

**Backend.**
1. Migration for `facts`, `conflicts`, `review_requests`.
2. Fact writers for each source: verified document fields from usable documents, profile rows, Zoom notes, messages, portal and calendar events. Each fact has field, value, normalized value, source kind, source id, quote, page and verification.
3. Field state per case and field: `AGREE`, `CONFLICT`, `UNVERIFIED` (only claims, "needs a document"), `HUMAN_DECIDED`. Severity high for name, date of birth and identifiers, medium for the rest.
4. `case.consistency` adds a plain-words explanation. Code checks that every cited id exists in the conflict.
5. `POST /api/cases/{id}/conflicts/{field}/suggest` (paralegal suggests a value with a reason, or leaves it to the attorney). `POST /api/cases/{id}/conflicts/{field}/resolve` (attorney decision, written to `review_decisions`, insert-only).
6. A human decision wins over extraction on every rerun (CASE-0012).
7. Routes `GET /api/cases/{id}/facts`, `GET /api/cases/{id}/conflicts`.

**UI.** `steps/FactsStep.tsx` (conflict card, odd source in red, suggest or leave to attorney, matching facts collapsed) and `steps/DocumentsFactsStep.tsx`. Every value shows a claim or evidence chip.

**Done when.**
- CASE-0001 shows the surname conflict with the Zoom note, the profile and `UP-000001` cited, and a review request is open.
- CASE-0002 (date of birth) and CASE-0023 (employment start) show conflicts. CASE-0013's address claim stays unverified.
- Changing a profile value in a test opens a new conflict.
- No claim is ever stored as a verified fact (test over all claim sources).
- Fact written, conflict opened, review requested and conflict resolved are audited.

---

## Phase 6. Form draft, deadlines and client reply

**Goal.** The case produces a cited form draft, a deadline proposal from the rule, and a client reply draft that never predicts or sends.

**Reads first.** Crash course chapter 8, HANDOFF sections 4.4 and 4.5, `10_deadline_rules.json`, `13_synthetic_form_template.json`, reference screens 8 and 11.

**Backend.**
1. Migration for `drafts` (form and client message, versioned).
2. Form draft from the template and field map. Each field is `PROPOSED`, `HELD_FOR_REVIEW` (conflict, value null) or `NOT_AVAILABLE`, with evidence refs, confidence from measurable signals and `needs_legal_review`. Status `DRAFT_NOT_FOR_FILING`. `GET /api/cases/{id}/form-draft` and a JSON download. The watermarked PDF is optional (cut line).
3. Deadline service as a pure function: only `MOCK_EVIDENCE_REQUEST_RECEIVED` from `MOCK_PORTAL` with `source_verified` true, plus the offset from `rule_sets`, no weekend shift. Flags: `DEADLINE_CONFLICT` when a calendar date differs, `OVERDUE` when the due date is before `review_as_of`, `UNVERIFIED_STATUS` when a calendar note claims a status.
4. The timeline route gains the proposed deadline and the flags, so the UI draws the crossed-out calendar entry.
5. Client reply with `reply.client`: grounded only in portal events and the checklist, marked `DRAFT_NOT_SENT`. A code check rejects drafts that predict an outcome or a timeline, or mention another case id. `GET` and `POST /api/cases/{id}/reply-draft` (regenerate, or "ask the client for" a missing item).
6. Audit lines for AI drafts.

**UI.** `steps/FormDraftStep.tsx` from `FORM_SECTIONS`, `steps/DeadlinesStep.tsx`, the proposed deadline in `tabs/TimelineTab.tsx`, `steps/ClientReplyStep.tsx`, `steps/ClientReplyReviewStep.tsx`.

**Done when.**
- CASE-0009 proposes 2026-10-24 under `SYN-DEADLINE-V1`, cites `EV-0009-RFE`, and flags the calendar date 2026-10-27.
- CASE-0001 gets no deadline. CASE-0015 shows overdue. CASE-0016 keeps the portal status.
- CASE-0010's reply declines to predict and states only the portal status.
- The form draft shows the CASE-0001 legal name as held with both citations.

---

## Phase 7. Review, approval and apply

**Goal.** The paralegal sends a case to the attorney, the attorney decides in five steps, and the paralegal applies approved changes exactly once.

**Reads first.** Crash course chapter 9, HANDOFF sections 4.6 and 8.5, `12_mock_operations_api.json`, reference screens 3, 4 and 6.

**Backend.**
1. Migration for `proposals`. Kinds: `DEADLINE_ACTIVATE`, `FORM_EXPORT`, `PACKET_APPROVE`, `MESSAGE_APPROVE`, `CASE_FIELD_UPDATE`, `STAGE_CHANGE`. Update `contracts.py` and `docs/schema.md`.
2. State machine as a pure service: OPS proposes, the assigned LEGAL user approves or rejects with a reason, OPS commits only from `APPROVED`. Anything else is refused and logged as `DENIED`. Forbidden kinds (filing, external send) are never created.
3. Idempotency key `{case_id}:{kind}:{ref}:{value}`. The same key returns the same proposal marked replayed. A rejected key is never proposed again.
4. Deadline proposals are recomputed with the deadline service and refused when the value differs.
5. `POST /api/cases/{id}/submit`: proposals plus a note, workflow to `WITH_ATTORNEY`.
6. `POST /api/cases/{id}/decision`: the attorney's choices from steps 2 to 4 are saved together in step 5. Approve, reject with a reason, or ask for more info (to the client or the paralegal), which moves the workflow to `INFO_REQUESTED` and shows in "Sent back to you".
7. `POST /api/cases/{id}/apply` commits every approved proposal and returns before and after rows. A second call changes nothing and writes `DUPLICATE_IGNORED`.
8. `GET /api/cases/{id}/export` in the `18_submission_schema.json` shape.

**UI.** `steps/SendStep.tsx`, `steps/OverviewStep.tsx`, `steps/DeadlineDecisionStep.tsx`, `steps/DecisionStep.tsx`, and a new apply screen built to match reference screen 6 (not yet in React). The paralegal reply to an attorney question and the rejected case view are still to design (HANDOFF 8.5), build them in the same style.

**Done when.**
- Tests: double propose gives one proposal, commit before approval is refused, OPS approval is refused, an unassigned LEGAL user is refused, reject then rerun keeps the rejection (CASE-0012), apply twice gives one commit.
- The full browser walk works for CASE-0009: paralegal sends, attorney approves the deadline, paralegal applies, Activity shows Proposed, Refused, Approved, Applied and Duplicate ignored.
- Every transition writes one audit line and the case chain verifies.

---

## Phase 9. Traps, mutation tests and hardening

**Goal.** The app passes every hidden scenario and works on cases it was not built against.

**Reads first.** `PLAN.md` sections 12, 13 and 15, HANDOFF section 9.

**Build.**
1. An automated trap suite for every case in HANDOFF section 9: 0001, 0002, 0003, 0004, 0005, 0006, 0007, 0008, 0009, 0010, 0012, 0013, 0014, 0015, 0016, 0017, 0019, 0021, 0023, 0024, 0025, 0026, using recorded Claude replies so it runs offline. The other cases must come out satisfied with no conflicts. Use the oracle files if decision 9 finds them.
2. The 12 mutation tests in `PLAN.md` section 13, run on a case not used during development.
3. `POST /api/import` re-imports pack files, keeps human decisions and returns the changed cases. Build the "New data arrived, run again" banner with a short diff of what changed.
4. Grep checks for hardcoded case ids, names, prompts, models and rule values in backend and frontend code.
5. Cache warm-up of all 603 practice PDFs. Full run under 10 minutes with a concurrency limit and rate limit handling.
6. Decide the final `AI_RUN_CAPTURE` value and record it.
7. `/status` covers db, OCR, embeddings, AI key and audit chain validity.

**Done when.**
- Every trap and every mutation test passes.
- At least 5 cases are fully processed end to end in the browser.
- `make reset-db` then a full run gives the same outcomes and a valid chain.

---

## Phase 10. Demo and submission

**Goal.** One clean, rehearsed run of the demo, and a submission a judge can start from the README.

**Build.**
1. Demo reset script, a prepared unseen PDF and an event change for the live mutation step.
2. README: setup, commands, architecture, trust zones, how to verify the chain.
3. Architecture diagram showing trust zones and the pipeline.
4. Rehearse the HANDOFF section 11 script (queue, CASE-0001 analysis, conflict, form draft, unseen PDF, attorney approves CASE-0009, apply twice, Activity, assistant refusals on 0010, 0017 and 0003, architecture). Time it and fix rough edges. Code freeze.

**Done when.**
- A clean clone, `cp .env.example .env`, key added, `make up`, and the demo runs in 5 to 7 minutes.

---

## Cut line

If time runs short, cut in this order: form PDF, AI management diff view, payment view (CASE-0020), rerun diff detail. Never cut the audit ledger and verify, the approval gate, case scoping, quarantine and duplicate handling, injection handling, or the deadline rule.
