# 100 case end to end run

Run on Oct 24, 2026 against a freshly wiped and re-seeded dev database. AI reading was on (reading model claude-sonnet-5-5). Drivers were small scripts that call the public API as the assigned OPS and LEGAL users.

## What was run

1. **Ingest.** `POST /api/cases/{id}/analyse` for all 100 cases, then poll `GET /api/jobs/{id}`. All 603 documents were read by the AI.
2. **OPS and legal simulation.** For every case: OPS submits the client reply draft, proposes the packet, the form, the deadline (when the portal rule gives one) and a stage change. The assigned LEGAL user approves, OPS commits. Every 10th stage change was rejected on purpose to check that a rejection is kept.
3. **Stage check.** Final stage compared with the stage the evidence calls for.

## Ingest result

| Item | Result |
| --- | --- |
| Cases with stored field states | 100 of 100 (900 rows) |
| Documents read | 603 of 603 |
| Usable | 592 |
| Invalid (translation needed 2, expired passport 1) | 3 |
| Needs human review (invalid date, orphan translation, rotated page, unreadable) | 4 |
| Quarantined (wrong client 1, mixed clients 1) | 2 |
| Duplicate / superseded | 1 / 1 |

Cases with at least one exception: 19. Types seen: missing document 5, fact conflict 4, unreadable 2, needs translation 2, suspicious text 2, human review 2, and one each of duplicate, wrong client, superseded, expired, deadline conflict, overdue, mixed clients, proposal rejected.

## Problem found and fixed: the app did not scale

The first pass ran three cases at once. Each case job reads up to 8 documents in parallel, so demand passed the database pool of 15 connections. 29 jobs ended FAILED with `TimeoutError` on single documents. It was a capacity problem, not a model or token problem.

Fixes:
- `backend/app/ingest/service.py`: one process wide limit of 8 reads at once across all jobs. Extra cases queue and wait.
- `backend/app/db/session.py`: pool raised to 20 plus 40 overflow (Postgres allows 100).
- The driver submits every case and polls the job. The re-run read the remaining 312 documents with no new pool errors.

The 31 FAILED job rows left in the table are from the first pass. Their documents were re-read by later jobs.

## OPS and legal simulation result

| Step | Count |
| --- | --- |
| Client reply sent to legal, approved, committed | 100 |
| Packet proposed, approved, committed | 100 |
| Form proposed, approved, committed | 82 |
| Form refused with `OPEN_EXCEPTIONS` | 18 |
| Deadline proposed, approved, committed | 2 |
| Stage change proposed and committed | 39 (38 committed, 1 rejected on purpose) |
| Stage change refused as `STAGE_UNCHANGED` | 61 |

The form is correctly blocked on every case with an open blocking exception. The 61 `STAGE_UNCHANGED` answers are expected, because sending the packet to legal already moves the case to Ready for legal review by itself.

## Stage check

Final stages: Ready for legal review 83, On hold 16, Intake review 1.

- All 82 cases with no blocking exception ended in Ready for legal review.
- 16 of the 18 cases with a blocking exception ended On hold.
- CASE-0070 stayed in Ready for legal review because its On hold change was the one rejected on purpose. The rejection was kept.
- CASE-0015 ended in Intake review. This was a real bug, see below.

## Bug found and fixed: a stale approved stage change was applied

CASE-0015 held an old approved stage change (Waiting for portal event to Intake review) that was never committed. The simulation committed it after a newer On hold change and moved the case back. A commit never checked that the case was still in the stage the change started from.

Fix in `backend/app/cases/proposals.py`: committing a stage change is refused with `STAGE_STALE` (409) when the case is in neither the from stage nor the to stage. Test added in `backend/tests/test_proposals.py`, and the stage tests pass. CASE-0015 itself still shows Intake review in the dev database.

## Open points

- **Packets were approved for cases with open exceptions in this run.** 18 cases with open conflicts or missing documents still got a packet approved and committed. The packet send is now blocked too (`OPEN_EXCEPTIONS`), so a rerun would refuse those cases.
- **The demo data is used up.** All 100 cases now have a committed packet and reply, and the audit trail has 2743 rows. A live demo from intake to an approved or rejected action needs untouched cases or a reset of proposals, drafts and audit rows.
- **Manifest has no expected outcomes,** so document outcomes could not be scored against an answer key. 592 of 603 usable is plausible only if the trap cases sit in the first cases. Check the trap suite (WS6) against the rule file for CASE-0001 to 0026.
- **Confidence on the form draft** is now filled from the evidence (committed earlier today, `b18baa7`).
- **Still uncommitted:** the pool change, the read limit, the stale stage guard, its test and this report.
