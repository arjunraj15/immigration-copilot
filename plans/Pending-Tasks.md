# Pending tasks

Tick a box when the work is merged and its check passes. Source: the plans folder review on Oct 23, 2026. Owner in brackets.

## 1. Document pipeline (phase 4)

- [x] Loader supplies `LoadedUpload(sha256, pages)` to `read_document` (Giri)
- [x] Text layer per page with the text source stored (OCR deferred by decision)
- [x] Scanned PDF auto detected and the page image sent to the AI (Giri)
- [x] Image reads stay UNVERIFIED and never auto accept a document (Giri)
- [x] Owner per page from the `Synthetic Matter:` line, wrong client and mixed bundle quarantined (Giri)
- [x] Document status rules in order: unreadable, duplicate, wrong client, superseded, expired, stale, pay period, prior notice, translation (Giri)
- [x] Outcome and reason saved on the upload row, `Human review` shown when not cleanly read (Giri)
- [x] `POST /api/uploads/{id}/read` and a Read with AI button on Documents and the AI Review tab (Giri)
- [x] `document_reads` row written for every read (Giri)
- [x] Checklist route per required category (Giri)
- [x] `POST /api/cases/{id}/analyse` and a job with progress events (Giri)
- [x] Auto read on upload: call `ensure_case_read` from the real upload route, which the wizard needs (Giri and Arjun)
- [x] Analyse moves the case workflow to ANALYSING and jobs survive a restart (Giri)
- [x] Superseded wording and a missing Synthetic Matter line rules, confirm with the team (team)
- [x] Real `POST /api/cases` and document upload in the wizard, replacing the mocked read (Giri and Arjun)
- [x] Audit lines: received, duplicate, read, quarantined, injection flagged (Giri)
- [x] Draft case lifecycle: DRAFT status hidden from queue, home, documents, actor counts and review lists, discard route (Giri)
- [x] `POST /api/cases/draft` from files only, a pasted call or message becomes a text file (Giri)
- [x] Call and message documents (Zoom notes, WhatsApp chat, email) read by the same pipeline, outcome CLAIM_SOURCE, claims table, never evidence (Giri)
- [x] `GET /api/cases/{id}/name-candidates` with source ids and a conflict flag (Giri)
- [x] `POST /api/cases/{id}/submit` with extracted or manual client name and duplicate client check (Giri)
- [x] New case wizard: documents, confirm, AI processing, client name, form draft (Giri)

## 2. Facts and conflicts (phase 5)

- [x] Fact table with source, quote and page (Arjun)
- [x] Conflict detector and field states AGREE, CONFLICT, UNVERIFIED, HUMAN_DECIDED (Arjun)
- [x] Suggest route for operations and resolve route for the attorney (Arjun)
- [x] Conflict card in the operations step and the attorney Documents and facts step (Giri)
- [x] Form fields become HELD_FOR_REVIEW on a conflict (Arjun)

- [x] Operations resolves a MEDIUM conflict with a required reason, a HIGH conflict stays with the legal reviewer, `can_resolve` per conflict, the decision records user and role (Giri)
- [x] Home and exceptions: medium conflict next action Resolve conflict for OPS, attorney To review lists only pending legal proposals, cases with the attorney and open HIGH conflicts (Giri)
- [ ] Apply migration 0013 with `docker exec teamecho-backend-1 alembic upgrade head` (Giri)
- [ ] Zoom note prompt skips an approximate date such as "Start date about 2025-06-01", so the CASE-0023 employment start conflict does not show yet (Giri and Arjun)
- [ ] Facts shown on the home page only count claims already read, open the case once to read the notes and messages (team)
- [ ] Remove the unused `rowsFromProfile` helper in `cases/formDraft.ts` (Giri)

## Communication

- [x] Communication tab at case level with channel and direction filters, day and thread grouping (Giri)
- [x] `GET /api/cases/{id}/communications` merging notes, messages and communication uploads with claim counts, case scoped (Giri)
- [x] Add communication form saves pasted text or a chosen file as a document upload (Giri)
- [x] Communication roles INTAKE_CALL, UPDATE and OFFICE_DRAFT, with the intake call pinned at the top of the tab (Giri)
- [x] Fact sources carry a phase (BASELINE, UPDATE, DOCUMENT, PROFILE) and a field has a `change` flag when a later message differs from the call (Giri)
- [x] Conflict cards show the phase pill and the changed after the intake call line (Giri)
- [x] Wizard Documents help line about call notes, chats, emails and Zoom note drafts (Giri)
- [x] Approximate employment start dates count as claims, prompt version 2 active for the Zoom, WhatsApp and email read prompts, CASE-0023 now shows the conflict (Giri)
- [x] Outbound email drafts that ask for missing fields, a template over conflicts, unverified fields, missing fields and unusable documents (Giri)
- [x] Office drafts appear in the Communication tab with the DRAFT, NOT SENT pill and a link to the Client reply step (Giri)

## 2b. Operations screens with real data (WS2 and WS5)

- [x] Shared exceptions module and `GET /api/exceptions` with type and search filters and counts (Giri)
- [x] Home reasons from real document defects, in the precedence set for the home page (Giri)
- [x] Case documents route returns reason code, duplicate original, injection flag, foreign page numbers and page sources (Giri)
- [x] Operations Documents step and the case Documents tab show the real checklist and outcomes (Giri)
- [x] Operations Deadlines step shows the real timeline and the proposed date, display only (Giri)
- [x] Exceptions page with filters, counts and links to the case and its documents (Giri)
- [ ] Propose for legal approval button on the Deadlines step, built with WS4 (Giri)
- [ ] Actions for a wrong client file, such as asking the client for the right file, have no backend yet (later)
- [ ] Missing document items need a Haiku browser check at desktop and mobile widths (Giri)

## 3. Form draft, deadline and client reply (phase 6)

- [ ] Preview JSON button, Download JSON and Download PDF at the top right of the form step (Giri)
- [x] Form step reads `GET /form-draft` instead of computing in the browser (Giri)
- [x] Form values sourced from documents: passport number and expiry, prior receipt (Arjun)
- [x] Client reply draft backend, marked DRAFT, NOT SENT: AI triage of the latest client question, plain templates, `message_drafts` table, edit, submit for legal review (Giri)
- [x] Operations and attorney Client reply steps use real data, the sample flags and notice are gone from both (Giri)
- [x] Review proposal page shows the message draft, channel and cited ids for a message approval (Giri)
- [ ] Apply migration 0014 with `docker exec teamecho-backend-1 alembic upgrade head` (Giri)
- [ ] Triage and templates gap: another client's name is caught only when the client writes a case id or a phrase such as another client, never by matching names in the database (Giri)
- [ ] A passport that arrived for someone else is listed as not received in the missing information email, because the set aside file has no category (Giri)
- [ ] Haiku browser check of the Client reply step, the proposal page and the Communication tab at desktop and mobile widths (Giri)
- [ ] Delete the unused `features/cases/SampleNotice.tsx` (Giri)

## 4. Approval gaps (phase 7)

- [ ] Proposal creators for deadline and packet in the UI (Giri)
- [x] Message approval proposal created from a reply draft, with the approve and reject result copied to the draft status (Giri)
- [ ] Packet index built by code from the checklist, with a packet approval proposal (Giri and Arjun)
- [ ] Case stage update as an approval gated proposal using the six stages (Giri and Arjun)
- [ ] Attorney deadline choice: approve, different date as a note, ask a question (Giri and Arjun)
- [ ] Cancel button on Reject (Giri)
- [ ] Sent back to you view and rejected case view (Giri)
- [ ] Apply approved changes screen (Giri)
- [ ] Decide what happens when late documents arrive after a case reaches legal (team)

## 5. Trap tests and hardening (phase 9)

- [ ] Trap suite for cases 0001 to 0026 with recorded model replies (Arjun)
- [ ] Twelve mutation tests on a case not used in development (Arjun)
- [x] Import route `POST /api/cases/{id}/import` and the Add data panel with a what-changed summary (Giri)
- [x] Delete an uploaded file with a reason, soft delete, `UPLOAD_DELETED` on the audit trail, migration 0025 (Giri)
- [ ] Grep check for hardcoded case ids, names and rule values (Giri)
- [ ] Full run over all 603 files with a concurrency limit (Giri)

## 6. Demo and submission (phase 10)

- [ ] Demo reset script and a prepared unseen PDF (team)
- [x] README with run steps and how to verify the audit chain (team)
- [x] Architecture diagram with trust zones, `docs/ARCHITECTURE.md` (team)
- [x] Demo script written, `docs/DEMO-SCRIPT.md` (team)
- [ ] Rehearse the six minute script (team)

## 7. Loose ends

- [ ] Rebuild the backend image so reportlab is permanent, check VPN first (Giri)
- [ ] Remove unused `FactsStep.tsx` and `UploadPage.tsx` (Giri)
- [ ] Fix the Passport type name saved as "Password" (Giri)
- [ ] Tell the team about the frozen design changes (Giri)
- [ ] Commit or delete the two home design drafts (Giri)

## Deterministic validation layer (WS2b)

- [x] Cross check clean `Label: value` lines against the AI values, a disagreement goes to Human review (Giri)
- [x] Date parsing with US formats, ambiguous dates go to review (Giri)
- [x] Plausibility checks: birth date in the past, passport expiry after birth date, employment start not after the review date (Giri)
- [x] Reference number pattern check from the rule data (Giri)
- [x] Applicant name consistent across a document's pages and compared with the case's known name (Giri)
- [x] Deadline candidate, calendar contradiction and overdue checks move into the same validation layer, one implementation used by home, timeline and the deadline steps (Giri)
- [x] Plain reason code on every failed check for the Exceptions page (Giri)
- [x] Keep the AI as the primary reader, no call skipped (Giri)
- [ ] Reference and receipt number pattern: the rule data defines none (kit documents show SYN-RCPT-00007 and DOCREF-000001 but no rule states them), so the check is skipped until a `reference_patterns` entry (field key to regex) is added to the document rules (Giri)
- [ ] Show the unverified APPROVED calendar note as an Exceptions item and a home reason, today only the timeline explains it (Giri)
- [ ] The proposal deadline check is wired to the create route only, the attorney deadline step still has no propose button until WS4 (Giri)

## Investigation agent with tools (WS3b)

- [ ] Read only case scoped tools for documents, facts, events, communications, checklist and audit (Giri)
- [ ] Deterministic comparison tools for dates, names and values that reuse the validation layer (Giri)
- [ ] Answers cite tool results and code checks the cited ids exist (Giri)
- [ ] Why is this blocked, client question triage and exception explanations use the agent (Giri)
