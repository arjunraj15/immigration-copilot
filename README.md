# TeamEcho: Immigration Case Co-Pilot

An agentic case operations co-pilot for a fictional immigration law firm, built for the Galaxy AI Spartans hackathon. It turns messy intake and uploaded PDFs into a traceable, review-ready case. Legal staff keep every legal judgment. All data is synthetic.

## Read first

1. `docs/PLAN.md` for scope, tracks, API contract, timeline and demo.
2. `rules.md` for the rules everyone follows.
3. `CLAUDE.md` for AI assistant guidance.
4. `docs/ai-module/README.md` for the AI module (prompt registry, document types, output contract).
5. `docs/schema.md` for the data model and `docs/E2E-100-Case-Run.md` for the 100 case run.
6. `docs/ARCHITECTURE.md` for the architecture diagram and trust zones, `docs/DEMO-SCRIPT.md` for the 5 to 7 minute demo.

## Quick start (Docker only)

You need Docker with Compose. Nothing else.

```bash
cp .env.example .env          # then set ANTHROPIC_API_KEY
mkdir -p project_requirmnt && cp -r <path to Galaxy_Immigration_starter-kit> project_requirmnt/
make up                       # first build is slow, later ones are fast
```

Open the frontend, then the `/status` page. Every check should be green. Ports are in `.env.example`. Services that start: `db` (Postgres with pgvector), `migrate` (runs Alembic once), `backend` and `frontend`.

After the first `make up`, run `make seed` once to load the starter kit into the database. It is safe to run again. The Acting as picker in the header lists the users found in the data.

To start with only the Zoom notes, client messages, profiles and events (no documents, the user uploads those), run `make seed-intake` instead. It derives one case per case id, starts each in document collection, and never resets a stage the app has moved.

To return to a clean demo state before a take or a judging session, run `make demo-reset`. It backs up the database, rebuilds the schema, keeps the AI prompts, resets the audit checkpoint and loads the intake files again. No document is loaded, so uploads are done live. It never rebuilds or recreates a container.

Useful commands: `make logs`, `make test`, `make lint`, `make seed`, `make seed-intake`, `make demo-reset`, `make migrate`, `make psql`, `make shell-backend`, `make build`, `make reset-db`, `make down`.

The database has two roles. Migrations run as the owner `casedesk` (`MIGRATION_DATABASE_URL`). The app runs as `casedesk_app` (`DATABASE_URL`), which can only insert into and read the audit ledger.

The starter kit is mounted read-only into the backend at `/data/starter-kit` and is never committed. Set `STARTER_KIT_DIR` in `.env` if you keep it somewhere else.

## Stack

React 19, Vite, TypeScript, Tailwind 4, TanStack Query, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL with pgvector, Anthropic SDK.

## Layout

```
backend/app/
  ai/          prompt registry, Claude calls, document reader, run history
  api/         thin FastAPI routes
  cases/       case queue, documents, form draft, packet, proposals, stage, audit use
  facts/       fact table, normalising, sources, value matching
  ingest/      uploads, hashing, duplicate checks, intake, background jobs
  investigate/ case questions and consistency checks
  replies/     client reply drafts and triage
  validation/  document rules, cross checks, deadline rules
  core/        config, audit ledger, security helpers
  services/    shared helpers
backend/migrations/  Alembic revisions
backend/tests/       pytest suite
frontend/src/features/  home, cases, documents, upload, facts, review, status, ai-management
docs/        plan, schema, AI module notes, E2E run, pipeline diagram
project_requirmnt/  local starter kit and brief (ignored by git)
```

## What it does

1. **Ingest.** Uploads and starter kit files are hashed, deduplicated, scoped to a case and read.
2. **Read.** Claude reads each document through a prompt from the registry and returns JSON with a quote and page per value. Code checks every quote against the source text.
3. **Facts and conflicts.** Values become a fact table. Claims never overwrite evidence, so a mismatch opens an exception for review.
4. **Exceptions.** Missing documents, translations, expired or unreadable files, wrong client and suspicious text are listed per case.
5. **Proposals.** OPS proposes the client reply draft, form draft, packet, deadline and stage change. LEGAL approves or rejects. OPS commits. Sending the packet to legal is blocked while exceptions or required documents are open.
6. **Audit.** Every transition is written to the hash-chained ledger, and the History tab verifies the chain.

The AI Management page edits prompts, document types and form field mappings, and lists run history. The Review page is the LEGAL queue.

## Tracks

| Track | Folders |
|---|---|
| AI management | `backend/app/ai/`, `frontend/src/features/ai-management/` |
| Upload and ingestion | `backend/app/ingest/`, `frontend/src/features/upload/` |
| Cases and review UI | `backend/app/cases/`, `frontend/src/features/{cases,review,chat}/` |

## Verify the audit chain

Every state change is a line in a hash chained ledger, one chain per case. Open a case, go to the History tab and press Verify chain, or call `GET /api/cases/{case_id}/audit/verify` (one case) or `GET /api/audit/verify` (all). Verifying needs a LEGAL user. A changed or removed row breaks the chain from that line on, and the head of each chain is also kept in a checkpoint file outside the database, so a rewritten chain is caught.

## Safety

Nothing is filed, sent or predicted. Drafts are marked `DRAFT_NOT_SENT`. Documents are untrusted data. Every state change needs LEGAL approval and is audited. See `rules.md`.

### Automatic case stage (a recorded exception)

The case stage is a status that follows events, so code moves it without a legal approval. A document received or read moves the case to evidence review when a file has a problem or is still being read, and to document collection when a required document is missing. A form export or packet sent to legal moves it to ready for legal review, and a legal rejection of either moves it to on hold. Each move is written to the audit trail as `STAGE_CHANGED` with `automatic: true` and the reason. A person who wants a different stage proposes a stage change, which legal approves and OPS commits like any other sensitive action. The rules are in `backend/app/cases/stage.py`.
