# Immigration Case Co-Pilot Schema

Database contract for Case Desk, derived from `docs/PLAN.md` section 6, `plans/Case Desk Flow.md` figures 2 and 4, and the starter kit `DATA_DICTIONARY.md`. Status: draft v1, waiting for team approval.

Tables are added by the phase that needs them (see `docs/WORK_PLAN.md`). A column change lands in the same commit as its Alembic migration and an update to this file.

## Conventions

1. PostgreSQL 18 with pgvector. All changes go through Alembic.
2. snake_case names. Tables are plural nouns.
3. Every table has `id` and `created_at`. Tables whose rows change also have `updated_at`.
4. `id` is a `bigint` identity. Starter kit ids (`CASE-0001`, `UP-000001`, `EV-0009-RFE`) are kept in their own unique text column, because they are the citation ids shown to users.
5. Every case-owned table has an indexed `case_id` (text, foreign key to `cases.case_id`).
6. Enumerated values are `text` columns with a `CHECK` constraint, not native Postgres enums, so adding a value is one migration line. The Python side uses the `StrEnum` classes in `backend/app/core/contracts.py`.
7. Timestamps are `timestamptz` in UTC. Calendar dates are `date`.
8. Values that come from the starter kit rules (document categories, form field targets, deadline offsets) are data in `rule_sets`, never check constraints or code.

## Enumerations

| Name | Values | Used by |
|---|---|---|
| `actor_role` | `OPS`, `LEGAL`, `SYSTEM` | audit, proposals |
| `source_kind` | `EVIDENCE`, `CLAIM` | facts |
| `source_type` | `DOCUMENT`, `PROFILE`, `PORTAL_EVENT`, `CALENDAR_EVENT`, `INTAKE_NOTE`, `MESSAGE`, `ASSERTION` | facts, citations |
| `upload_outcome` | `PENDING`, `READING`, `DUPLICATE`, `QUARANTINED`, `SUPERSEDED`, `INVALID`, `USABLE`, `CLAIM_SOURCE`, `NEEDS_HUMAN_REVIEW` | uploads |
| `text_source` | `TEXT_LAYER`, `IMAGE` (OCR deferred) | document_pages |
| `verification` | `VERIFIED`, `UNVERIFIED` | facts, extracted fields |
| `conflict_status` | `OPEN`, `IN_REVIEW`, `RESOLVED` | conflicts |
| `review_request_status` | `OPEN`, `CLOSED` | review_requests |
| `proposal_kind` | `DEADLINE_ACTIVATE`, `FORM_EXPORT`, `PACKET_APPROVE`, `MESSAGE_APPROVE` | proposals |
| `proposal_status` | `PENDING_LEGAL_REVIEW`, `APPROVED`, `REJECTED`, `COMMITTED` | proposals |
| `decision` | `APPROVED`, `REJECTED`, `REJECTED_EXTRACTION` | review_decisions |
| `draft_kind` | `FORM`, `CLIENT_MESSAGE` | drafts |
| `send_status` | `DRAFT_NOT_SENT` | drafts |
| `job_status` | `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED` | jobs |
| `prompt_run_status` | `OK`, `CACHED`, `REFUSED`, `MAX_TOKENS`, `SCHEMA_INVALID`, `TIMEOUT`, `ERROR` | prompt_runs |
| `audit_outcome` | `ALLOWED`, `DENIED`, `SYSTEM` | audit_log |

`upload_outcome` follows figure 2 of the flow doc. `PENDING` covers Received and Read before a final outcome. `NEEDS_HUMAN_REVIEW` is the result when Claude refuses or fails (rules.md 3.7).

`audit_action` is validated by the `AuditAction` enum in `backend/app/core/contracts.py`, not by a database check, so a new phase adds an enum value and no migration. Only `audit.record(...)` writes the column. Values (rules.md 12.10 plus the ones the Activity tab needs): `UPLOAD_RECEIVED`, `DUPLICATE_DETECTED`, `DUPLICATE_IGNORED`, `DOCUMENT_READ`, `QUARANTINED`, `INJECTION_FLAGGED`, `FACT_WRITTEN`, `CONFLICT_OPENED`, `CONFLICT_RESOLVED`, `REVIEW_REQUESTED`, `CASE_CREATED`, `ANALYSIS_RUN`, `AI_DRAFT`, `PROPOSE`, `REVIEW_APPROVE`, `REVIEW_REJECT`, `COMMIT`, `SUBMITTED_FOR_REVIEW`, `INFO_REQUESTED`, `RERUN_SKIPPED_PRIOR_REJECTION`, `PROMPT_VERSION_CREATED`, `PROMPT_VERSION_ACTIVATED`, `CHAT_QUESTION`, `CHAIN_VERIFIED`, `SEED_LOADED`. A denied attempt uses the action it tried, with outcome `DENIED`.

## Starter kit tables (phase 2)

Loaded by `make seed` (`app/cases/loader.py`) in one transaction. Each table has a unique source key, so a second load changes nothing. A changed source row is updated in place. Every table has `id`, `created_at` and `updated_at` unless noted. Case tables have an indexed `case_id` that references `cases.case_id`.

### cases
| Column | Type | Notes |
|---|---|---|
| case_id | text unique | `CASE-0001` |
| web_record_id | text | |
| client_ref | text | |
| case_archetype | text | |
| operational_stage | text | `INTAKE_REVIEW`, `DOCUMENT_COLLECTION`, `EVIDENCE_REVIEW`, `WAITING_FOR_PORTAL_EVENT` in the kit, not constrained |
| assigned_ops_user | text | |
| assigned_legal_reviewer | text | |
| opened_at | date | |
| matter_visibility | text | |
| priority | text | |

### intake_notes (claims)
`intake_id` unique (`Z-0001`), `case_id`, `recorded_at`, `platform`, `speaker`, `summary`, `raw_note_excerpt`, `ai_generated` bool, `approved_as_fact` bool.

### messages (claims)
`message_id` unique (`MSG-0001-1`), `case_id`, `thread_id`, `created_at_source` timestamptz, `channel`, `direction`, `sender_role`, `subject`, `body`, `attachment_refs` text[], `delivery_state`.

### profile_fields (evidence, may be stale)
`source_id` unique (`PROFILE-CASE-0001-full_name`), `case_id`, `field_name`, `verified_value`, `verification_state`, `verified_at`, `verified_by`.

### case_events
`event_id` unique, `case_id`, `event_date` date, `event_type`, `event_source`, `source_reference`, `details`, `source_verified` bool, `import_batch`. Evidence only when `event_source = 'MOCK_PORTAL'` and `source_verified`. Everything else is a claim.

### rule_sets
`key` (`document_rules`, `deadline_rules`, `form_field_map`, `form_template`), `version`, `source_file`, `body` jsonb, `sha256`. Unique on (`key`, `version`). A changed rules file becomes a new version and older versions stay. Code reads the newest version only. The review date used everywhere comes from `deadline_rules.as_of`, never the system clock. No `updated_at`, rows are never changed.

### review_decisions (insert-only)
`decision_id` unique, `case_id`, `proposal_id` nullable, `field_name` nullable, `rejected_value`, `corrected_value`, `decision`, `reviewer_role`, `reviewer_id`, `reason`, `source_ref`, `recorded_at`. Seeded from `17_review_decisions_seed.jsonl` and appended by LEGAL reviews. The app role has no UPDATE or DELETE, and a trigger blocks UPDATE, DELETE and TRUNCATE for every role. No `updated_at`. The newest corrected value for `full_name` is the case's display name.

### case_workflows
`case_id` unique, `status` (`NEW`, `ANALYSING`, `IN_PROGRESS`, `WITH_ATTORNEY`, `INFO_REQUESTED`, `APPROVED`, `REJECTED`, `APPLIED`), `wizard_step` int (0 based), `submitted_by`, `submitted_to`, `submitted_at`, `note`, `decided_at`. One row per case, created by the loader as `NEW`. The status decides which queue group a case appears in. Later phases change it through services that write an audit line.

## Documents (phase 4)

### uploads
Loaded from the manifest in phase 2 with outcome `PENDING`. `storage_root` is `STARTER_KIT` (path relative to the kit) or `APP_STORAGE`. The outcome columns are filled in phase 4. `case_id` is the folder the file was uploaded to, not proof of ownership.

| Column | Type | Notes |
|---|---|---|
| upload_id | text unique | `UP-000001`, or a new id for app uploads |
| case_id | text | the case it was uploaded to (`folder_case_id`), not proof of ownership |
| storage_path | text | |
| original_filename | text | never used for classification |
| mime_type, file_size_bytes | text, bigint | |
| sha256 | text indexed | |
| uploaded_at | timestamptz | |
| uploader_role, ingestion_source | text | |
| client_supplied_type | text | shown as a claim, never decides category |
| version_label | text | |
| category | text nullable | from content, validated against `rule_sets` |
| outcome | upload_outcome | |
| outcome_reason | text | shown in the exception queue |
| duplicate_of_upload_id | text nullable | |
| superseded_by_upload_id | text nullable | |

### document_reads
`upload_id`, `case_id`, `prompt_run_id`, `text_source`, `page_count`, `text_sha256`, `extracted` jsonb (a `DocumentRead`), `injection_flags` jsonb, `verified_field_count`, `unverified_field_count`. The full extracted text lives in `text_chunks` and storage, not here.

### document_pages
`upload_id`, `page_number`, `text_source`, `char_count`, `rotation`, `owner_case_id`, `image_sha256`, `reason`. Added by migration 0008, which also adds `document_reads.extracted` and the `READING` outcome. A value read from a page image carries `from_image` true and `verified` false in `extracted`.

### jobs (phase 4)
Not created yet. Added by the migration of the phase that starts background work, with the columns `kind`, `case_id` nullable, `status` job_status, `progress`, `total`, `error` jsonb, `started_at`, `finished_at`.

## Facts and conflicts (phase 5)

### facts
| Column | Type | Notes |
|---|---|---|
| case_id | text | |
| field_name | text | form field target or profile field, from `rule_sets` |
| value | text | original value as found |
| normalized_value | text | for comparison only |
| source_kind | source_kind | |
| source_type | source_type | |
| source_id | text | citation id |
| quote | text nullable | verbatim, checked by code |
| page | int nullable | |
| verification | verification | `VERIFIED` only when code found the quote |
| observed_at | timestamptz nullable | |
| document_read_id | bigint nullable | |

Index on (`case_id`, `field_name`).

### conflicts
`case_id`, `field_name`, `status`, `fact_ids` bigint[], `explanation` text nullable, `explanation_prompt_run_id` nullable, `review_request_id` nullable.

### review_requests
`case_id`, `target_type`, `target_id`, `question`, `status`, `requested_by`, `closed_by` nullable, `closed_reason` nullable.

## Proposals and drafts (phase 6)

### proposals
| Column | Type | Notes |
|---|---|---|
| proposal_id | text unique | `ACT-000001` |
| case_id | text | |
| kind | proposal_kind | |
| status | proposal_status | |
| idempotency_key | text unique | same key returns the same row |
| target_type, target_id | text | |
| value | jsonb | for deadlines also the rule version and trigger event id |
| evidence_ids | text[] | |
| proposed_by | text | OPS actor |
| reviewed_by | text nullable | LEGAL actor |
| review_reason | text nullable | required on reject |
| committed_by | text nullable | |
| reviewed_at, committed_at | timestamptz nullable | |

### drafts
`case_id`, `kind` draft_kind, `version` int, `body` jsonb, `evidence_ids` text[], `send_status` (client messages only), `prompt_run_id`, `proposal_id` nullable. Form drafts carry status `DRAFT_NOT_FOR_FILING` inside `body`.

## AI (phase 3)

### prompts
`key` unique (`doc.read.passport`), `kind` (`EXTRACTION`, `ANALYSIS`, `DRAFT`, `CHAT`), `description`, `active_version` int nullable. Only the active pointer changes. `origin` (`BUILT_IN` or `ADDITIONAL`, check constraint, default `BUILT_IN`). A document type created from an uploaded file is `ADDITIONAL` and is listed under additional document types in the AI section.

### additional_form_fields
Global extra inputs of the Form draft, added from the AI tab. `target` text unique (code built `additional.<slug>`), `label`, `value_type` (`string`, `date`, `number`, check constraint), `enabled`, `created_by`, `created_at`, `updated_at`. Not case data, so no `case_id`. The fact field of a row is its `target`. A read prompt field fills it through `form_target`. Every add writes a `FORM_FIELD_ADDED` line on the SYSTEM audit chain.

### prompt_versions
`prompt_key`, `version` int, `system_text`, `user_template`, `model`, `effort`, `max_tokens`, `output_schema` jsonb, `content_sha256`, `created_by`. Unique on (`prompt_key`, `version`). The app role has no UPDATE or DELETE, so a change is always a new version. Text templates use `{name}` placeholders. `{documents}` and `{review_as_of}` are always available.

### prompt_runs
`prompt_key`, `version`, `model`, `case_id` nullable, `input_hash`, `cache_key` nullable, `cache_hit`, `status` (`OK` or `NEEDS_HUMAN_REVIEW`), `reason_code` (`REFUSAL`, `MAX_TOKENS`, `MALFORMED_JSON`, `SCHEMA_INVALID`, `TIMEOUT`, `API_ERROR`, `NOT_CONFIGURED`), `stop_reason`, `input_tokens`, `output_tokens`, `latency_ms`, `attempts`, `result` jsonb nullable, `rendered_prompt`, `input_text`, `raw_output`. The last three are filled only when `AI_RUN_CAPTURE=full`. Rows are insert-only for the app role and are written in their own transaction. `cache_key` is a hash of the file sha256, prompt key, version and content hash, and only `OK` runs are reused.

### text_chunks (phase 8)
`case_id`, `source_type`, `source_id`, `page` nullable, `chunk_index`, `text`, `embedding vector(384)`. Index on `case_id`. Every search filters by `case_id` before ranking.

## Audit ledger (phase 1)

Rules in `rules.md` section 12.

### audit_log (insert-only)
`id` identity, `stream_id` text (`CASE-0001` or `SYSTEM`), `seq` bigint, `occurred_at` timestamptz (database clock), `actor`, `actor_role`, `action`, `outcome`, `case_id` nullable, `target_type`, `target_id`, `before_state` jsonb, `after_state` jsonb, `evidence_ids` text[], `idempotency_key`, `request_id`, `prompt_run_id` bigint (no foreign key until `prompt_runs` exists), `details` jsonb, `prev_hash` char(64), `row_hash` char(64). Unique on (`stream_id`, `seq`), index on `case_id`. `case_id` has no foreign key so the ledger can outlive and precede the `cases` table. The table has `occurred_at` in place of `created_at`.

`row_hash` is the SHA-256 of the canonical JSON (sorted keys, no spaces, UTF-8) of every column above except `id`, `prev_hash` and `row_hash`, plus `prev_hash`. `occurred_at` is UTC ISO 8601 with microseconds. Entries must not contain floats because jsonb does not keep them byte for byte.

Two database roles. The owner (`casedesk`) runs migrations. The app runs as `casedesk_app`, which has only SELECT and INSERT on `audit_log` and no DELETE on `audit_heads`. A trigger rejects UPDATE, DELETE and TRUNCATE on `audit_log` for every role, including the owner.

### audit_heads
`stream_id` primary key, `last_seq`, `last_hash`, `updated_at`. Locked and updated only by `audit.record(...)`. Chain heads are also written to a checkpoint file (`AUDIT_CHECKPOINT_FILE`, default `/app/storage/audit_checkpoint.json`) after each commit, so a chain rewritten with valid hashes still fails verification.

## Not modelled

`14_billing_mock.csv` and `15_collections_sheet_mock.csv` feed the stretch payment view and get a table only if that view is built.
