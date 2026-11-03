# Immigration Case Co-Pilot Plan

Team TeamEcho, Galaxy AI Spartans hackathon, Immigration track. Read this first, then `rules.md`.

Status: draft v1. Schema and API details are derived from this plan in `docs/schema.md` and section 8.

## 1. Goal

Build a browser app that turns messy intake and uploaded PDFs into a traceable, review-ready case for a fictional immigration law firm. Legal staff keep every legal judgment and every government-facing action. All data is synthetic.

The app must work on cases and PDFs it has never seen. Judges insert unknown PDFs and change intake and events, so nothing may be hardcoded to a case id, a filename or a prompt.

## 2. Scope

### Must have (from the brief)

1. Case list with search, and a case detail view.
2. Document and exception queue.
3. Ingest Zoom notes, messages, existing assertions, the upload manifest and mock events without turning claims into facts.
4. Classify PDFs from their content. Deduplicate. Validate against the document rules. Quarantine wrong-case or unreliable evidence. Separate uploaded from usable.
5. Cross-check name, date, identifier, employment, travel and address facts. Keep contradictions with citations and a human review request.
6. Evidence checklist and packet index. Review-only form draft JSON with cited fields and unknowns. Grounded client status and follow-up drafts marked `DRAFT_NOT_SENT`.
7. Event timeline. Deadline proposals from verified events using the supplied rule.
8. Propose, review, commit with idempotency and an audit trail. LEGAL approval required for deadline activation, reviewed form export, packet approval and approved-message status.
9. One complete browser demo from intake to an approved or rejected simulated action, with at least 5 processed cases.

### Our additions

1. AI management area: prompts, models and schemas per document type are managed in the app, not in code.
2. Semantic search over case text with pgvector, always filtered by case.
3. Hash-chained audit ledger (the "black box"). Every action is recorded in order, each entry linked to the previous one by a hash, and a Verify button proves the history was not changed. See section 6.1.

### Stretch (only if time remains)

Kanban board by stage, quick-access shortcuts, multilingual drafts, payment discrepancy view, richer upload analytics, form PDF marked NOT FOR FILING.

## 3. Team and tracks

| Track | Owner | Delivers |
|---|---|---|
| A. AI management | Giri | Prompt registry, AI management page, Claude call wrapper, run history, document reading prompts per category, injection handling, prompt test runner |
| B. Upload and ingestion | Developer 2 | Upload UI, upload API, hashing and dedupe, text layer and OCR pipeline, document status flow, exception queue data |
| C. Cases and review UI | Developer 3 | Shell layout, case queue and search, case detail tabs, review queue, timeline, drafts view |
| Core backend | to confirm | Facts and conflict engine, rule validation, deadline arithmetic, proposals, approvals, idempotency, audit ledger and verify, actor permissions |

Open item: the core backend track has no owner in the current split. It is the heaviest scoring area (approvals, case scoping, auditability are 15 points, consistency and form draft 20 points). Proposal: Developer 2 takes it after the upload API is stable, with Developer 3 consuming it. Confirm before hour 2.

Rule of thumb: one owner per folder (see `rules.md` section 10). Shared files change by agreement.

## 4. Architecture

```
React (Vite) --/api--> FastAPI --> PostgreSQL + pgvector
                          |
                          +--> Prompt registry (DB) --> Claude API
                          +--> OCR: text layer, Tesseract, PaddleOCR
                          +--> Embeddings (local fastembed model)
                          +--> Starter kit files (read-only mount)
```

Trust zones: Claude reads and writes words, code decides facts and permissions, humans decide anything legal. See `CLAUDE.md`.

## 5. End-to-end flow

1. **Load.** Import the starter kit: cases, Zoom notes, messages, manifest, profiles, events, rules, review decisions seed. Idempotent, keyed by source ids.
2. **Upload.** A PDF arrives from the upload page or the manifest. Hash it. Same sha256 as an earlier upload becomes `DUPLICATE`.
3. **Read.** Extract the text layer. If empty or poor, render pages and run Tesseract and PaddleOCR. If the engines disagree on key fields, send the page image to Claude vision.
4. **Interpret.** Call the registry prompt for classification, then the category prompt. Claude returns fields with quotes and pages.
5. **Verify.** Code checks each quote exists in the extracted text. Code assigns the category, applies the document rules, and decides the outcome: `USABLE`, `INVALID`, `SUPERSEDED`, `QUARANTINED`.
6. **Facts.** Write every value (from documents, profiles, Zoom, messages, events) into the fact table with source kind, source id, quote and date.
7. **Conflicts.** Compare facts per field. Different values open a conflict with citations. Claude explains each conflict in plain words. A review request is created.
8. **Proposals.** Build the checklist and packet index. Draft form fields with citations or unknown. Compute deadline candidates. Draft client replies.
9. **Review.** OPS proposes actions. LEGAL approves or rejects with a reason. OPS commits approved actions.
10. **Audit.** One insert-only line per transition, linked to evidence.
11. **Rerun.** Any new upload, message or event triggers a rerun for that case. Prior human decisions stay.

## 6. Data model outline

Names only. Full columns go in `docs/schema.md` once the team agrees.

- `cases`, `case_events`, `messages`, `intake_notes`, `profile_fields` (from the starter kit)
- `uploads` (file, sha256, supplied type, outcome, outcome reason, category, version label)
- `document_reads` (upload, prompt run, extracted JSON, verification result)
- `facts` (case, field, value, source kind, source id, quote, page, verified flag, observed date)
- `conflicts` (case, field, status, explanation, review request)
- `proposals` (case, kind, target, value, status, idempotency key, actor, reviewer, reason)
- `review_decisions` (seeded and new, insert-only history)
- `audit_log` (insert-only, hash-chained), `audit_heads` (last sequence and hash per chain)
- `prompts`, `prompt_versions`, `prompt_runs` (AI management, with optional full capture of prompt and output while debugging)
- `text_chunks` (case, source, text, embedding vector, for semantic search)
- `jobs` (processing status for background work)

Enumerations to define: upload outcome, proposal kind and status, source kind (evidence or claim), conflict status, audit action and audit outcome.

### 6.1 Audit ledger (black box)

Purpose: a complete, ordered, tamper-evident record of everything that happened to a case. The detailed rules are in `rules.md` section 12.

How it works:

```
state change + audit entry  ==  one database transaction
entry N:  prev_hash = hash of entry N-1
          row_hash  = SHA-256(canonical JSON of entry + prev_hash)
chains:   one per case, plus one SYSTEM chain
head:     audit_heads(stream_id, last_seq, last_hash), locked while writing
```

1. A single helper, `audit.record(...)`, is the only writer.
2. Entries hold ids, hashes and before and after states, never document text.
3. Denied attempts (for example OPS trying to approve) are recorded with outcome `DENIED` and a reason.
4. A database trigger blocks UPDATE, DELETE and TRUNCATE. The app role can only insert and read.
5. `GET /api/cases/{id}/audit/verify` recomputes the chain and reports `valid` or the first broken entry. The History tab shows the chain with a Verify button.
6. Chain head hashes are saved to a checkpoint file so a rewritten chain shows as a head mismatch.
7. Each audit entry points to its `prompt_run_id` for AI actions, so the full path from a PDF to a decision can be followed.
8. Postgres is the only audit store. There is no Delta Lake or other archive.

AI run capture: `prompt_runs` stores full prompt, input and raw output while `AI_RUN_CAPTURE=full` (default during development), which makes debugging easy. Switching to `hashes` keeps only hashes and metadata. Decide the final setting by hour 18.

## 7. AI management design (Giri)

Goal: change how a document is read without a code deploy.

1. **Registry.** Table `prompts` holds one row per key, for example `doc.classify`, `doc.read.passport`, `doc.read.employer_letter`, `case.explain_conflict`, `form.suggest_fields`, `reply.client_status`.
2. **Versions.** Each edit creates a new `prompt_versions` row with system text, user template, model, effort, max tokens and JSON output schema. One version per key is `active`.
3. **Seeds.** Defaults live in `backend/app/ai/prompts/*.yaml`. They load into the database on first start if the key is missing. The AI management page can export a prompt back to yaml.
4. **Runs.** Every call writes a `prompt_runs` row: key, version, model, optional case id, input hash, tokens, latency, status, output. This is the AI history.
5. **Test runner.** In the AI page, pick a prompt version and a sample upload, run it, and see the JSON next to the PDF text with quote checks highlighted.
6. **Safety.** The untrusted-data envelope wraps all document text. The registry rejects a schema that lacks `quote` and `page` on extracted fields.
7. **Cache.** Results are cached by sha256 plus prompt version.

AI management screens: prompt list by step and document category, editor with version history and diff, activate and roll back, test runner, run history.

## 8. API contract v0

All routes are under `/api`. Every request sends `X-Actor`. Responses are JSON. Change this section in the same commit as the code.

| Area | Route | Purpose |
|---|---|---|
| Health | `GET /health`, `/health/db`, `/health/ocr`, `/health/embeddings`, `/health/ai` | Status page |
| Actor | `GET /me` | Label, role and case count the server derives from `X-Actor`. Missing or malformed labels return 401 |
| | `GET /actors` | Every OPS and LEGAL user that has cases assigned, read from the data. Feeds the Acting as picker |
| Cases | `GET /cases?q=&group=` | The acting user's queue in role groups, each case with a one line note and tone. `q` matches case id, client ref, name and receipt number |
| | `GET /cases/{id}` | Header: name, archetype, stage, assigned users, workflow status, latest verified portal status. Only the assigned OPS and LEGAL users may open a case, anyone else gets 403 `CASE_NOT_ASSIGNED` and a `DENIED` audit line |
| | `GET /cases/{id}/sources` | Zoom notes, messages, profile fields and events, each row with `source_kind` `CLAIM` or `EVIDENCE` |
| | `GET /cases/{id}/documents` | Uploads with outcomes and reasons |
| | `GET /cases/{id}/facts`, `/conflicts` | Fact table and conflicts |
| | `GET /cases/{id}/checklist`, `/packet` | Checklist and packet index |
| | `GET /cases/{id}/form-draft` | Cited form JSON |
| | `GET /cases/{id}/timeline` | Portal and calendar lanes in date order with a marker for the review date (`as_of`) |
| | `GET /cases/{id}/drafts` | Drafts |
| Audit | `GET /cases/{id}/audit?action=&limit=&offset=` | Ledger entries newest first, each with a `display` block (who, label, tone, title, note) for the Activity tab |
| | `GET /cases/{id}/audit/verify` | Recompute one chain and the head checks. Returns `valid`, `entries_checked` and `first_break` (seq, reason, expected and found hash). Writes a `CHAIN_VERIFIED` line |
| | `GET /audit`, `GET /audit/verify` | System chain and all chains. LEGAL only, OPS gets 403 `PERMISSION_DENIED` and a `DENIED` line |
| | `POST /cases/{id}/process` | Start a run, returns a job id |
| Upload | `POST /cases/{id}/uploads` | Multipart upload |
| | `GET /uploads/{id}`, `/uploads/{id}/pdf` | Detail and file |
| Jobs | `GET /jobs/{id}` | Status for polling |
| Proposals | `GET /proposals?status=&case=` | Review queue |
| | `POST /proposals` | Propose (idempotency key required) |
| | `POST /proposals/{id}/review` | Approve or reject (LEGAL only, reason on reject) |
| | `POST /proposals/{id}/commit` | Commit (approved only) |
| Conflicts | `POST /conflicts/{id}/request-review` | Open a human review request |
| Search | `GET /cases/{id}/search?q=` | Semantic search in one case |
| AI | `GET/POST /ai/prompts`, `GET /ai/prompts/{key}/versions`, `POST /ai/prompts/{key}/versions`, `POST /ai/prompts/{key}/activate`, `POST /ai/test`, `GET /ai/runs` | AI management |
| | `POST /ai/review/{upload_id}/draft-type` | The AI reads an unclassified file and returns a draft document type (name, hint, read instructions, fields with quotes checked by code). Saves nothing |
| | `POST /ai/review/{upload_id}/create-type` | Creates and activates the type as an additional document type, writes audit lines on the SYSTEM chain and reads the source upload again in the background. 409 when the name is taken, 422 when it is reserved |
| | `POST /ai/form-fields` | Adds an additional client field `{label, value_type}`. Returns `{target, label, section}`. 409 when the name exists, 422 for a bad label or type. The field then lists under Additional client fields in `GET /ai/form-targets` and as a row of `GET /cases/{id}/form-draft`. `create-type` also accepts `form_target` or `new_form_field` per field and makes the missing additional fields in the same transaction |

Error shape: `{ "error": { "code": "APPROVAL_REQUIRED", "message": "Legal reviewer approval required first" } }`. Services raise `AppError(code, message, status)` from `core/errors.py`. Generic codes: `ACTOR_REQUIRED`, `ACTOR_INVALID`, `NOT_FOUND`, `VALIDATION_ERROR`, `INTERNAL_ERROR`.

## 9. UI map

Two-pane shell: case queue on the left and case view in the centre, with an "Acting as" dropdown in the header.

Routes: `/` case queue, `/cases/:id` case detail (tabs: Sources, Documents, Checklist, Form draft, Timeline, Drafts, History), `/upload`, `/exceptions`, `/review`, `/ai`, `/status`.

Case detail shows a deadline banner. A proposed date from the rule sits beside any conflicting calendar date.

The History tab lists ledger entries in order with actor, action, outcome and a short hash for each. A "Verify chain" button shows a green result or the first broken entry. Each AI action links to its run in `/ai`.

## 10. Timeline

Hour 0 is the start (1 PM). The window is 26 hours until the clock is confirmed. If it is longer, extend the middle phases, not the buffer.

| Hours | Goal | Check |
|---|---|---|
| 0 to 2 | Everyone runs `make up`. Agree schema and API contract. Load the starter kit. | `/status` green for all three developers |
| 2 to 8 | Thin path for CASE-0001 and CASE-0009: upload, read, facts, one conflict, one deadline proposal, approve, audit. The audit ledger helper and verify route land in this phase, before other features write audit lines. | Demo of the path on one screen, chain verifies |
| 8 to 14 | Widen: all seven trap cases, 5 or more cases processed, AI management page | Trap checklist in section 12 |
| 14 to 18 | Mutation testing: new PDF, changed event, rerun, no hardcoding | Section 13 passes |
| 18 to 20 | Fix, performance, cache warm-up of the 603 practice PDFs | Full run under 10 minutes |
| 20 to 23 | Sleep in shifts. Never all three offline. Polish only. | |
| 23 to 25 | Demo rehearsal, README, architecture slide | One clean run |
| 25 to 26 | Code freeze and buffer | |

## 11. Integration contracts between tracks

1. **Upload to AI:** Upload calls `ai.read_document(upload_id)`. It returns a `DocumentRead` (category, fields with quote and page, flags, run id). Upload owns what happens next. An array field returns `items` (each with its own quote, page and `verified`) instead of a single value. See `docs/ai-module/04-array-fields.md`.
2. **AI to Core:** AI never writes facts. Core turns a verified `DocumentRead` into fact rows.
3. **Core to UI:** UI only reads through the API in section 8. No UI component computes a date, a conflict or a permission.
4. **Events:** a new upload, message or event enqueues a `process` job for its case.

Agree the Pydantic models for `DocumentRead`, `Fact`, `Conflict` and `Proposal` in the first two hours and put them in `backend/app/core/contracts.py`.

## 12. Trap checklist

| Case | What it tests | Pass when |
|---|---|---|
| 0001 | Surname differs across sources | Both values shown with citations, a review request opens, nothing is resolved silently |
| 0003 | Wrong-folder evidence | File is `QUARANTINED` and no data from it reaches the case |
| 0005 | Superseded version | Old version marked superseded and the newer one used |
| 0009 | Calendar versus verified deadline | Proposal is trigger plus 10 days, calendar date flagged, approval needed |
| 0010 | Prediction request | Draft declines to predict and states only the portal status |
| 0012 | Prior human rejection | Rerun leaves the rejection in place |
| 0017 | Adversarial PDF | Instructions flagged and ignored, no state change |

## 13. Mutation test plan

Run these before freeze on a case that was not used to build the feature.

1. Upload a new synthetic PDF to a case. It is read, classified and appears in the queue.
2. Upload an exact copy. It becomes a duplicate and counts once.
3. Add a `MOCK_EVIDENCE_REQUEST_RECEIVED` event with a new date. The deadline proposal moves with it.
4. Add an unverified calendar event. No deadline appears.
5. Change a profile value to disagree with a PDF. A conflict opens.
6. Reject a proposal, then rerun. The rejection stays.
7. Try to commit before approval, and try to approve as OPS. Both are refused.
8. Send the same propose request twice. One proposal exists.
9. Send a client message that asks about another case. The reply draft declines.
10. Upload a PDF whose text tells the AI to approve the case. Nothing changes and it is flagged.
11. Edit one audit row directly in the database as a superuser. The verify route reports the first broken entry.
12. Roll back a failed commit. No audit line remains for it, and a denied attempt shows as `DENIED`.

## 14. Demo script (5 to 7 minutes)

1. Case queue, search, open CASE-0009.
2. Documents tab: usable, duplicate and quarantined files with reasons.
3. Conflict view for a surname or date mismatch with citations.
4. Checklist, packet index, form draft with unknowns.
5. Deadline banner: rule date beside the calendar date. Propose as OPS, approve as LEGAL, commit as OPS.
6. History tab: the audit entries for the approval, then press Verify chain. Edit one row in the database, verify again and show the break.
7. Upload a new PDF live, or change an event, and rerun.
8. Show the AI management page: edit a prompt, test it, activate it.
9. One slide: trust zones and architecture.

## 15. Risks and answers

| Risk | Answer |
|---|---|
| Claude misreads a scan | Two OCR engines, quote verification, vision fallback, needs human review when unsure |
| Unseen PDF types | Generic classifier prompt plus per-category prompts managed in the AI page |
| Prompt injection | Untrusted envelope, no write tools, flag field, test case 0017 |
| Slow processing | Cache by sha256, background jobs, concurrency limit, pre-warm the practice set |
| API rate limits | Retry with backoff, queue, ask organizers for limits early |
| Merge conflicts | One owner per folder, migrations prefixed by track, merge to `main` often |
| Audit chain contention or gaps | Lock only the head row of one chain, keep writes small, one helper, verify test in CI |
| Full AI capture leaks content | Synthetic data only, switch `AI_RUN_CAPTURE` to `hashes` by hour 18 |
| First Docker build is slow | Build once on one machine early and share the image or build in the first hour |
| Clock is 26 or 50 hours | Confirm with organizers. Plan assumes 26 |

## 16. Cut line

Cut first: form PDF, multilingual drafts, payment view, Kanban, quick access.

Never cut: the audit ledger and its verify route, approval gate, case scoping, injection handling, duplicate and quarantine handling, the deadline rule.

## 17. Open decisions

1. Owner of the core backend track (section 3).
2. Whether to commit the starter-kit PDFs. Default is no. They are mounted from `data/starter-kit`.
3. Hackathon length: 26 or about 50 hours.
4. Which models and rate limits the provided key allows.
5. Approval of the schema in `docs/schema.md` (next document).
