# Next work plan

Written Oct 23, 2026. Tick items in `plans/Pending-Tasks.md` as each stream lands. This file holds the order, the reasons and the checks.

## Where we stand

- Built: document pipeline with AI read and scanned page images, the new case wizard (documents, confirm, AI processing, client name, form draft), Zoom, WhatsApp and email as claim source document types, the attorney review flow for the form export, and the audit chain.
- In progress: the fact table and conflict detection agent.
- Built but not on `main` yet: the ingestion rework and the Communication tab.
- Still sample data: both Client reply steps.

## How a case starts

- The kit treats a case as already existing. Its row has the case id, type, stage and assigned people, and an opened date (CASE-0001 opened Jun 2, 2026).
- The Zoom intake note is attached later (Oct 4, 2026). It is the first claim source, never evidence. Every case's Zoom note comes before its first message.
- WhatsApp and email are the follow up. The office's one outbound email per case is the document checklist request. Inbound messages are status questions, upload notices and sometimes a new fact.
- Our wizard creates a case for a new client from the files you add. That is our own design. The server assigns the case number and the legal reviewer.

## Streams, in order

### WS0. Land what is built
- Finish the fact and conflict agent, apply migration `0013`, run the full backend suite and the type check, then commit through a feature branch, `dev` and `main`.
- Check: tests green, form draft route works on the dev database, audit chain still verifies.

### WS1. Case origin and communication model
- The Communication tab pins the Zoom call as "Intake call, starting point". Later messages are marked as updates.
- Claims carry a baseline or update label. A later message that changes a fact shows as a conflict against the call and the documents. Nothing is updated automatically.
- A short wizard line says a Zoom note can start a new client draft.
- Depends on WS0.

### WS2. Replace sample screens with real data
- Operations Documents step and the case Documents tab show the real checklist, outcomes and AI types.
- Operations Deadlines step shows the real timeline and the proposed deadline.
- The home page shows document problems (duplicate, wrong client, expired, unreadable, needs translation) as reasons.
- Journey steps 3, 4 and 7.

### WS5. Exceptions page (runs beside WS2, same backend reasons)
- One real list of defects, conflicts, quarantined files and flagged injections, each linked to its case.
- Scored triage, journey steps 3 to 5.

### WS2b. Deterministic validation layer
- The AI reads and quotes, code validates and decides. The validation layer is pure functions with no model call, using values from the rule data and the review date, never the clock. An expired passport is a plain date comparison.
- Cross check: when a page has a clean `Label: value` line, code compares it with the AI value. A disagreement sends the file to Human review. No AI call is skipped and none is added.
- Value checks on everything the AI returns: dates must parse (ambiguous ones go to review), a birth date is in the past, a passport expiry is after the birth date, an employment start is not after the review date, reference numbers match the pattern in the rule data, the applicant name is the same across a document's pages, and the applicant is compared with the case's known name.
- Deadlines belong to the same layer. The deadline candidate (verified portal evidence request plus the rule offset, rule set `SYN-DEADLINE-V1`), the calendar contradiction flag, the overdue check and the as of date all become validators in one place, pure functions using the rule data. Home, the timeline, the Deadlines steps and the attorney deadline step call it instead of keeping their own copies.
- Every failed check carries a plain reason code for the Exceptions page.
- Runs after WS2 and WS5 because it changes the same ingest files.

### WS3. Client communication
- Reply drafting for the Client reply steps. Always marked DRAFT, NOT SENT. No outcome prediction, no legal advice, no other client's data.
- Missing field email. For every field that is missing, unverified or in conflict, a deterministic template drafts an email to the client that lists the fields and why. AI is used only to triage the client's question.
- Outbound drafts appear in the Communication tab. A message approval can go to the attorney.
- Depends on WS1. Journey step 8.

### WS3b. Investigation agent with tools
- One read only agent with case scoped tools (documents, facts and conflicts, events, communications, checklist, audit) and deterministic comparison tools (compare dates, add days, is expired, compare names, compare values). The case id is fixed by the server and no tool can write.
- The comparison tools reuse the WS2b validation layer, one implementation for the pipeline and the agent. A name similarity label only informs a human and never resolves anything. Date and name verdicts in an answer must cite a tool result, and code checks the cited ids exist.
- Uses: "Why is this blocked?", client question triage (refuse unsupported questions, status is "processing", no predictions) and exception explanations. Document text goes through the untrusted envelope. Replies are drafts only.
- Depends on WS2b and WS3. Covers the agentic investigation criterion of the guide.

### WS4. Approvals
- Proposal creators for deadline, packet and message approval.
- Packet index: an evidence index that lists each usable document under its required category with its id, built by code from the checklist, with an approval through the same gate (the mock's evidence packet draft and approve kinds). Required by the guide.
- Case stage update as a proposal using the six stages in the data (intake review, document collection, evidence review, ready for legal review, waiting for portal event, on hold), through the same gate (the mock's stage update kind). Required by the guide ("update local case state").
- The attorney deadline choice: approve, a different date saved as a note, or ask a question.
- Cancel on Reject, the sent back and rejected views, and the apply screen.
- Journey step 9.

### WS6. Hardening and judging
- Restore the starter cases for testing.
- Trap suite for cases 0001 to 0026, mutation tests and a re-import route for judges' changes.
- Check for hardcoded case ids, a full run over all 603 files, the README, the architecture diagram and the demo script.

## Parallel work

1. WS0 alone first.
2. WS1, then WS2 and WS5 together. WS2 and WS5 share one backend reasons module, so one agent builds both.
3. WS2b after WS2 and WS5, since it changes the same ingest files.
4. WS3 after WS1, then WS3b.
5. WS4, then WS6.

## Checks for every stream

- Backend tests with fakes and the type check.
- A Haiku browser check at desktop and mobile widths.
- One live run with the real API on a scratch database for AI parts.
- One commit per stream through the feature branch, `dev` and `main` flow.

## Defaults chosen and open questions

- Order as above (decided).
- Reply drafts use a plain template, with AI only for triage (decided).
- The dev database holds the starter kit data again, loaded with `make seed` on Oct 23, 2026 after the test cases were removed (decided). The Communication samples come from that data. New cases from the wizard continue the numbering after CASE-0100.
- Open: which streams Arjun takes on the backend.
