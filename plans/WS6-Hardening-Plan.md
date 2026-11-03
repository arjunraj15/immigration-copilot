# WS6 plan: hardening and judging

Written Oct 24, 2026. The mandatory features are built. This stream makes the app survive unknown input and ships the deliverables. Order is by what judges can do live first, then by points at risk. Tick items in `plans/Pending-Tasks.md` as each lands.

## Decisions made (Oct 24, 2026)

1. Demo reset re-seeds the database. The audit ledger is append-only for the app role, so a re-seed keeps the chain honest.
2. The packet is blocked like the form. Sending it to legal is refused while the case has an open blocking exception or a missing or unusable required document (`OPEN_EXCEPTIONS`).
3. Add a `reference_patterns` entry (field key to regex) to the document rules so the reference number check stops being skipped.
4. Arjun's share of 6.3 and 6.4 is still open, ask the user.
5. The full 603 file run needs the user's OK after 6.1 to 6.6.

## 6.1 Re-import route and "New data arrived" banner

Status (Oct 24, 2026): built as `POST /api/cases/{id}/import` (`cases/importer.py`, tests in `tests/test_import.py`) and an Add data panel in the case header (`features/cases/ImportData.tsx`). It takes an event, a Zoom note or a client message. PDFs keep using `POST /api/cases/{id}/documents`. Only a portal event may be verified. Also added: delete an uploaded file (soft delete, migration 0025, `UPLOAD_DELETED` audit line, `tests/test_delete_upload.py`).

- `POST /api/import` (OPS or LEGAL), scoped to one case. Accepts an events row, a Zoom note, a message or a PDF.
- Idempotent by event id or content sha256. Never overwrites a human decided field. Calls `engine.recompute(db, case_id)` after saving. Writes an `IMPORTED` audit line.
- Case banner says new data arrived and what changed (new conflict, deadline, exception).
- Check: change a verified portal event date and the deadline and calendar contradiction update. Change a name in a Zoom note and a conflict appears. Import the same row twice and get one row.

## 6.2 Demo reset and a fresh demo set

- `make demo-reset` re-seeds the DB. Keep 5 or more cases never touched by any script.
- Prepare one unseen PDF and one with an injected instruction.

## 6.3 Trap suite for cases 0001 to 0026

- One pytest per case in `plans/Scenario-Test-Plan.md`, with recorded model replies. Assert outcome, reason code, conflict refs and no other client's data in the output.
- Add controls 0018, 0022 and 0050 (expected clean).
- Cover the guide section 6 scenarios: identity mismatch, wrong client, unreadable or rotated, stale, missing translation, duplicate, deadline contradiction, unsupported client question, rejection preserved, double approval gives one commit, injected PDF. OPS approving gets a 403.
- One live pass with the real API for the AI parts.

## 6.4 Twelve mutation tests

On a case not used in development, change one thing at a time: name, DOB, passport number, employer, start date or address in the intake note; an event date; a `source_verified` flag; a disagreeing calendar reminder; a wrong month pay statement; an unseen wrong client PDF; a rotated PDF; an exact duplicate; a client message asking for an approval prediction. Assert the right outcome for each.

## 6.5 Hardcode grep

Search `app/` and `frontend/src` for case ids, client names, rule dates (`2026-09-01`, `2026-10-23`), the offset `10` and category names. Every hit must come from rule data or fixtures.

## 6.6 Rule and field gaps

- Wire `09_case_events.source_reference` as a source for `case.prior_receipt_reference`.
- Confirm address claims from `03_client_messages.body` reach `applicant.mailing_address`.
- Add `reference_patterns` to the document rules.
- Show an unverified APPROVED calendar note as an Exceptions item and a home reason.
- Reword the profile chip to "Profile (earlier verified, may be stale)".
- Packet send blocked when exceptions are open or a required document is missing or unusable.
- Form step: Preview JSON, Download JSON and Download PDF buttons.

## 6.7 Full run over all 603 files

Redo `docs/E2E-100-Case-Run.md` after 6.1 to 6.6 with a concurrency limit. Ask the user first (token cost).

## 6.8 Delivery documents

- Architecture diagram with trust zones: untrusted PDF and message zone, agent zone (read, triage, investigate, tools listed), deterministic zone (joins, rules, dates, permissions, gates, audit), human gate. Mermaid in `docs/` plus a PNG.
- README: run, seed, demo reset, tests, how to verify the audit chain, safeguards.
- Demo script, 5 to 7 minutes: dashboard, CASE-0001 name conflict with citations, document and exception queue, cited form draft, deadline proposal with calendar contradiction, client reply that refuses to predict, OPS refused then LEGAL approves, double approve gives one commit, rejection preserved, audit trail, a live unseen PDF.
- Two timed rehearsals.

## 6.9 Cleanup

- Delete by hand (rm is blocked): `SampleNotice.tsx`, `UploadPage.tsx`, `FactsStep.tsx`, `PasteText.tsx`, unused `rowsFromProfile`.
- Fix the Passport type name saved as "Password".
- Rebuild the backend image so reportlab is permanent (check VPN first).
- Commit the E2E fixes (pool, read limit, stale stage guard, test, report) through the feature, `dev`, `main` flow. Leave `CommunicationTab.tsx`, the design drafts and the deck files out unless told.
- Haiku browser checks of client reply, communication and exceptions at desktop and mobile widths.
- Tick `plans/Pending-Tasks.md`, which is stale.

## Checks for every stream

Backend tests with fakes and the type check, a Haiku browser check at desktop and mobile, one commit per stream through the feature branch, `dev` and `main` flow. Do not run the full backend suite without asking.
