# Demo script, 5 to 7 minutes

Case used: CASE-0009 (Riya Suri). After `make demo-reset` it has no files, so the first minutes upload its PDFs live. Its portal deadline disagrees with a calendar entry. Acting as: OPS-01 for operations, LEGAL-01 for the reviewer. Both are demo controls, not authentication.

## Before you start (2 minutes, off camera)

- Backend healthy, `/status` page green, API key loaded. Do not rebuild or recreate containers on the day.
- Run `make demo-reset` before every take. CASE-0009 starts with no documents and shows missing items.
- Have CASE-0009's PDFs ready to upload, and wait for the read to finish before moving on.
- One unseen PDF and one PDF with an injected instruction ready on the desktop.
- Pick a spare case that nobody has touched for the live data change.

## The run

| Time | Say and do | What the judge should see |
|---|---|---|
| 0:00 | The problem in one line: messy intake and uploads become a traceable, review-ready case. Software prepares, legal approves, nothing is filed or sent. | Home queue, 100 cases, a reason on each row. Most show "Missing document" because nothing is uploaded yet. |
| 0:30 | Open CASE-0009 (all six required items missing). Upload its PDFs and the call and message files. | The AI reads each file live. Usable files, call and message files marked as claims, each with an outcome and a reason. |
| 1:15 | Open the facts step. Point at a field with two sources. | Conflict kept, never silently picked, each side cited with quote and page. |
| 2:00 | Checklist, packet index and form draft. | Required items satisfied or missing. Form fields cited, unknown stays blank with the reason. Marked NOT FOR FILING. |
| 2:45 | Try to send the packet to legal while something is open. | Button disabled with the reason. The server refuses it too. |
| 3:15 | Deadline banner: rule date beside the calendar date. Propose as OPS, switch to LEGAL-01, approve, switch back, commit. | Candidate computed from the verified portal event only, the calendar entry flagged, activation gated on approval. |
| 4:15 | Client reply step: a client asks "will I be approved?" | Draft refuses to predict, states the status as processing, marked DRAFT, NOT SENT. |
| 4:45 | History tab, Verify chain. | The approval, the refusal and the rejection are on the ledger, chain valid. |
| 5:15 | Live change: Add data on the spare case. Import a changed event or a Zoom note with a different name. | "New data arrived" summary shows the field or deadline that changed. Importing it again changes nothing. OPS cannot tick Verified, only LEGAL can. |
| 6:00 | Upload the unseen PDF, then the injected one. | Classified from content, rules applied. The injection is flagged and not followed. |
| 6:30 | Delete a wrongly uploaded file with a reason. | It leaves the lists and the facts, and the ledger records who, when and why. |
| 6:45 | Architecture, `docs/ARCHITECTURE.md`. | Agents read and suggest, deterministic code decides, legal approves. |

## If something goes wrong

- **A file shows "not read yet" with the reason "The AI service was not available":** the AI service or key failed. The file is safe. Fix the key, then press Read with AI on the Documents page. Say it plainly, it is the designed behavior.
- **Approve twice:** show that one commit happens and the duplicate is logged.
- **A reviewer asks about a hidden case:** the guide traps map to cases in `plans/Scenario-Test-Plan.md` (name spelling 0001, wrong client 0003, rotated 0025, mixed bundle 0026, injection 0017).
