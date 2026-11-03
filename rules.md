# rules.md

Hard rules for everyone working on Immigration Case Co-Pilot, human or AI. If a rule blocks you, raise it in the team chat before bending it.

## 1. Product safety rules (never break)

1. No legal advice, no eligibility determination, no outcome or timeline prediction.
2. Nothing is filed, sent to a client or sent to any government system. Drafts are marked `DRAFT_NOT_SENT`. Form PDFs, if any, are marked `NOT FOR FILING`.
3. No live integrations (Notion, Cerenade, Drive, Gmail, WhatsApp, QuickBooks). Everything is local and synthetic.
4. Every state change goes through propose, review, commit. OPS proposes. LEGAL approves or rejects. OPS commits. Commit is refused unless the state is `APPROVED`.
5. A human rejection is permanent until a human changes it. A rerun may add a new suggestion but never edits or deletes a decision.
6. Every proposal carries an idempotency key. The same key returns the same proposal.
7. Every transition writes one audit line to the hash-chained audit ledger (section 12), in the same database transaction as the change. Denied attempts are logged too.
8. Case scoping: every query for case data takes a `case_id`. Retrieval, search and chat never cross cases. If ownership is uncertain the document is quarantined.
9. Actor labels are demo controls and not authentication. Permissions are still enforced on the server.

## 2. Evidence and data rules

1. Documents, human-verified profiles and verified portal events are evidence. Zoom notes, messages, calendar entries and existing assertions are claims.
2. Never turn a claim into a fact by copying it into a field. Show the conflict, cite both sides, and open a review request.
3. A value is only `verified` when its quote is found in the source text by code. Otherwise it is `unverified`.
4. Filenames and folder names do not decide document type or ownership. Read the content.
5. Exact sha256 duplicates count once. Uploaded does not mean usable.
6. Deadlines come only from a `MOCK_EVIDENCE_REQUEST_RECEIVED` event from `MOCK_PORTAL` with `source_verified` true, plus 10 calendar days (rule `SYN-DEADLINE-V1`). Never from a calendar entry or a message. Code does the date math. The value in a proposal must be recomputed and compared before it is accepted.
7. The rules in the starter kit are fictional. Build to them and do not correct them from real-world law.
8. Never invent an identity, evidence, receipt number, date or outcome. Unknown stays unknown.

## 3. AI and prompt rules

1. **No hardcoded prompts.** Every prompt, system text, model choice, effort level and output schema lives in the prompt registry (database, seeded from `backend/app/ai/prompts/*.yaml`). Code calls a prompt by key, for example `doc.read.passport`.
2. Prompts are versioned. A run records the prompt key, version, model, token counts, input hash and result status. While debugging, `AI_RUN_CAPTURE=full` also stores the rendered prompt, the text sent and the raw output in `prompt_runs`. Switching it to `hashes` stops storing content and keeps only hashes and metadata. It is an environment setting and needs no code change. Decide the final value by hour 18.
3. Document text is untrusted data. Wrap it in the untrusted-data envelope. Instructions found inside a document are flagged and never followed.
4. Claude calls get no tools that change state. They return JSON and the backend decides what to store.
5. Use structured outputs with a schema. Every extracted value carries a verbatim `quote` and a `page`. Code verifies the quote against the extracted text.
6. Do not use forced tool choice, assistant prefill, `temperature`, `top_p` or `top_k`. Set `effort` explicitly.
7. Check `stop_reason` before reading content. On `refusal` or failure, mark the item "needs human review" and continue.
8. Cache Claude results by file sha256 plus prompt version. A prompt change invalidates the cache.
9. Default models: `claude-sonnet-5-5` for document reading, `claude-opus-5-5` for analysis. Both are set in the registry and not in code.
10. Semantic search uses the local embedding model and pgvector. Always filter by `case_id` before ranking.

## 4. Backend rules

1. Layers: route, service, repository. Routes are thin. Rules and date math live in services as pure functions with tests.
2. Python 3.12, type hints everywhere, Pydantic models at the API boundary, SQLAlchemy 2 style.
3. Cyclomatic complexity of 15 or less. Early returns. Enums instead of boolean flags with more than two states.
4. All database changes go through Alembic migrations. Never edit the schema by hand or with `create_all`.
5. Errors return a clear JSON body with a code and a message. Do not swallow exceptions.
6. Long work (reading a PDF, processing a case) runs as a background task. The API returns a job status that the UI polls.
7. Read config from environment through `core/config.py`. No secrets in code.

## 5. Frontend rules

1. React 19 with TypeScript. Function components and hooks only.
2. Server state with TanStack Query. Local UI state with `useState` or context.
3. All API calls go through `src/api/client.ts`, which adds the `X-Actor` header. No direct `fetch` in components.
4. Every status is shown with a pill and a reason, never color alone. Show source chips (claim or evidence) next to every value.
5. Forms use controlled inputs and clear inline errors. Buttons say what they do.
6. Support light and dark themes through CSS variables. Keep layouts usable at phone width.
7. No new UI library without agreement. Tailwind plus small hand-made components.

## 6. Database rules

1. PostgreSQL with the pgvector extension, enabled by migration.
2. Table and column names use snake_case. Tables are plural nouns. Every table has `id`, `created_at`, and `updated_at` where rows change.
3. Every case-owned table has an indexed `case_id`.
4. Audit rows are insert-only and hash-chained. No update or delete (see section 12).
5. Enumerated values (upload outcome, proposal status, source kind) are enums or check constraints, documented in `docs/schema.md`.

## 7. Docker rules

1. Everything runs through `docker compose`. Do not ask teammates to install Python, Node, Tesseract or PaddleOCR locally.
2. Versions are pinned in `backend/requirements.txt` and `frontend/package.json`. Change a version only in a dedicated commit that explains why.
3. Licenses must allow commercial use. No AGPL or GPL dependencies. PyMuPDF is banned for this reason. Use `pdfplumber`, `pypdf` or `pdftoppm` (poppler, in the image) for PDF text and page images.
4. Models (PaddleOCR, embeddings) are downloaded at image build time so the demo works offline.
5. The starter kit is mounted read-only at `/data/starter-kit`. Never write into it.
6. Do not commit `.env`, `data/`, uploads or model caches.

## 8. Git rules

1. `main` is always runnable. Work on short-lived branches named `track/short-topic`, for example `ai/prompt-registry`, `upload/dropzone`, `ui/case-queue`.
2. Small commits with a clear subject line in the imperative mood. No em-dashes or semicolons.
3. Pull and rebase from `main` before pushing. Merge to `main` at least every few hours.
4. Never force-push `main`. Never commit secrets, keys, `.env` files or the PDFs.
5. Resolve API contract changes in `docs/PLAN.md` section 8 in the same commit as the code.

## 9. Text and copy style

Never use em-dashes or semicolons in any generated text. This covers UI copy, tooltips, button labels, code comments, docstrings, commit messages, docs and PR descriptions. Use a period, a comma or a short connecting word. Write plainly and prefer specific words over clever ones.

## 10. Ownership and boundaries

| Track | Owns | Avoid editing without asking |
|---|---|---|
| AI management | `backend/app/ai/`, `frontend/src/features/ai-management/`, prompt seeds, run history | other tracks' folders |
| Upload | `backend/app/ingest/`, `frontend/src/features/upload/`, OCR service | `ai/` internals (use the registry API) |
| Cases and review UI | `backend/app/cases/`, `frontend/src/features/{cases,review,chat}/`, shell layout | `ingest/` internals |
| Shared | `docker-compose.yml`, `requirements.txt`, `package.json`, `core/`, `db/`, migrations, `docs/` | change by agreement, one owner per commit |

Migrations are the main collision risk. Pull before creating one and rename the revision message with your track prefix.

## 11. Definition of done

A task is done when:
1. It runs in Docker from a clean `make up`.
2. It has a test for the rule it implements (pure functions) or a manual check noted in the PR.
3. It works on a case it was not built against, not only the demo cases.
4. It writes an audit line through the ledger helper if it changes state, and the chain still verifies.
5. No hardcoded case ids, prompts or rule values.
6. The `/status` page is still green.

## 12. Audit ledger (black box)

The audit log is a blockchain-style ledger. Each entry is linked to the one before it by a hash, so any edit, deletion or reordering is detectable.

1. **One writer.** All audit writes go through one helper, `audit.record(...)` in `backend/app/core/audit.py`. No other code inserts into `audit_log`.
2. **Same transaction.** The helper writes in the same transaction as the state change. If the change rolls back, its audit line rolls back too. A denied attempt is written in a separate transaction after the rollback, with outcome `DENIED` and the reason.
3. **Chains.** There is one chain per case, plus one `SYSTEM` chain for events without a case (prompt versions, admin actions). Each chain has a head row in `audit_heads` (`stream_id`, `last_seq`, `last_hash`). The helper locks the head row, reads it, inserts the entry with `seq = last_seq + 1`, and updates the head.
4. **Hash.** `row_hash = SHA-256(canonical JSON of the entry fields + prev_hash)`. Canonical JSON means sorted keys, UTF-8, no extra whitespace, timestamps in UTC ISO 8601. The first entry in a chain uses 64 zeros as `prev_hash`.
5. **What an entry holds.** `stream_id`, `seq`, `occurred_at` (database clock), `actor`, `actor_role`, `action`, `outcome` (`ALLOWED`, `DENIED`, `SYSTEM`), `case_id`, `target_type`, `target_id`, `before_state`, `after_state`, `evidence_ids`, `idempotency_key`, `request_id`, `prompt_run_id`, `details`, `prev_hash`, `row_hash`.
6. **No content.** Entries store ids, hashes and states. They never store document text, message bodies or personal details beyond the ids already in the case.
7. **Immutable.** The application database role has only INSERT and SELECT on `audit_log`. `audit_heads` is changed only by the helper. A trigger rejects UPDATE, DELETE and TRUNCATE on `audit_log`.
8. **Verify.** `GET /api/cases/{id}/audit/verify` and `GET /api/audit/verify` recompute every chain and return `valid` or the first broken `seq` with the expected and found hashes. The History tab shows the result.
9. **Head anchors.** Chain head hashes are also written to a checkpoint file outside the database. Rewriting a whole chain then shows as a head mismatch.
10. **Required events.** Upload received, duplicate detected, document read, quarantined, fact written, conflict opened, review requested, propose, approve, reject, commit, denied attempt, rerun skipped because of a prior rejection, injection flagged, prompt version created or activated, chat question, chain verified.
11. **Tests.** Every new audited action has a test that the line exists and that `verify` passes. One test edits a row directly as a superuser and checks that `verify` reports the break.
12. **Postgres only.** The ledger lives in Postgres and nowhere else. No Delta Lake, no second audit store.
