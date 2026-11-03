# AI module guide

This folder holds the business knowledge of the AI module (`backend/app/ai/` and `frontend/src/features/ai-management/`). It is written so a coding agent can pick the work up without reading every file first.

Read in this order.

1. [Purpose and the two operations](01-purpose-and-operations.md). Classify then read.
2. [Document types and fields](02-document-types.md). The seeded prompts and their keys.
3. [Output contract and quote rule](03-output-contract.md). What `DocumentRead` holds and how a quote is verified.
4. [Array fields](04-array-fields.md). Repeated rows with a quote on every row.
5. [Prompt lifecycle](05-prompt-lifecycle.md). Versions, activate, rollback, key lock, disable, delete.
6. [Untrusted data and injection](06-untrusted-data-and-injection.md). The envelope and `injection_flag`.
7. [Caching and run capture](07-caching-and-run-capture.md). Cache key and capture modes.
8. [API routes and error codes](08-api.md).
9. [Frontend screens](09-frontend.md).
10. [Trap cases](10-trap-cases.md). What the module must return for 0001, 0004, 0008, 0017, 0021, 0026.
11. [Running the tests](11-testing.md). Offline and live.
12. [Known limits and open decisions](12-known-limits.md).
13. [Docker notes](13-docker-notes.md).

Related files outside this folder: `rules.md` section 3 (AI rules), `plans/AI-Prompts-Plan.md` (the original plan), `docs/PLAN.md` section 8 (API contracts).

Writing style for anything added here: no em-dashes, no semicolons, plain words. Do not name other products or earlier projects.
