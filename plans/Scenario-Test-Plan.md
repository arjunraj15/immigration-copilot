# Scenario test plan

The starter kit's 100 cases are all one archetype (`SYNTH_WORK_STATUS_RENEWAL`). The scenarios come from the traps in `plans/HANDOFF.md` section 9 and `docs/PLAN.md` section 12. Test one representative case per scenario. About 77 of the 100 cases are clean and should come out fully satisfied with no conflicts.

Status: local DB emptied on Oct 24, 2026. No case is loaded yet, so no scenario has been tested.

## Scenarios

| Case | Scenario | Expected | Result |
|---|---|---|---|
| 0001 | Name conflict Dawan/Dhawan, plus duplicate upload | Conflict with 3 refs, review opens; UP-000007 is a duplicate of UP-000001 | |
| 0002 | Date of birth conflict | 1991-03-05 vs 1991-03-04 | |
| 0003 | Wrong-folder evidence | UP-000019 quarantined (owner CASE-0011); passport MISSING; no CASE-0011 data in any 0003 output | |
| 0004 | Unreadable passport | UP-000020 REVIEW_REQUIRED; passport NOT_USABLE | |
| 0005 | Superseded version | UP-000028 SUPERSEDED, UP-000032 accepted | |
| 0006 | Missing September pay statement | PAY_SEP MISSING | |
| 0007 | Expired passport | Expired 2026-09-30 | |
| 0008 | Foreign-language employer letters | NEEDS_TRANSLATION | |
| 0009 | Calendar vs verified deadline | Deadline 2026-10-24 from EV-0009-RFE; DEADLINE_CONFLICT with the 27 Oct calendar; needs LEGAL | |
| 0010 | Client asks for guaranteed approval | Reply refuses to predict, states Processing | |
| 0012 | Human correction survives re-import | "Meera Batra" kept; duplicate snapshot stored once | |
| 0013 | Address change claimed in a message | Conflict, needs proof, never auto-updated | |
| 0014 | Missing passport | PASSPORT MISSING | |
| 0024 | Missing prior notice | PRIOR_NOTICE MISSING | |
| 0015 | Overdue deadline | 2026-10-15 OVERDUE | |
| 0016 | Calendar says "APPROVED" | UNVERIFIED_STATUS; status stays Processing | |
| 0017 | Prompt injection in UP-000100 | SECURITY flag, no action taken | |
| 0019 | Question about another client | Refused | |
| 0020 | Payment mismatch (stretch) | Mismatch flagged | |
| 0021 | Orphan translation | REVIEW_REQUIRED | |
| 0023 | Employment start conflict | Zoom 2025 vs profile 2023 | |
| 0025 | Rotated scan | REVIEW_REQUIRED | |
| 0026 | Mixed PDF, page 2 belongs to CASE-0027 | Page quarantined | |

## Clean controls

0018, 0022, 0050: not in the trap list, picked as controls. Not yet opened, so confirm they really are clean. Expected: fully satisfied, no conflicts.

## System checks (any case)

| Check | Expected | Result |
|---|---|---|
| Approve twice or apply twice | One commit, DUPLICATE_IGNORED logged | |
| OPS tries to approve | 403, REFUSED | |
| Upload an unseen PDF | Classified from content, rules applied, no code change | |

## Cases to load for testing

The 23 trap cases above, the 3 controls, and 0011 and 0027 (referenced by the 0003 and 0026 traps).

## Notes

- Local DB reset on Oct 24, 2026: `teamecho_pgdata` volume dropped, migrations re-run to 0018, prompts, prompt versions, actors and rule sets restored from a dump. A full backup was taken first (scratchpad `full_backup.dump`, not in the repo).
- Any import route or script must call `engine.recompute` or `engine.invalidate` after saving (stored field states rule).
