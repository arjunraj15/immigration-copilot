# Review queue brief (shared by all three variants)

Redesign the legal **Review** page (`/review`, today `frontend/src/features/review/ReviewPage.tsx`) of Case Desk. It lists proposals that need a legal decision. Nothing is filed or sent from this app. Static mockups only, no backend.

## Source of truth
- Hackathon guide: `Immigration Law Firm/Galaxy_Immigration_starter-kit/Developer_Challenge_Guide.pdf`. Relevant parts: simulated approval (offline proposal, review, commit, audit), reviewer actions, idempotent approval-gated changes, preserved rejections, injected PDF text is untrusted, never fabricate identity, evidence, dates or outcomes, every update needs provenance, uncertainty stays visible.
- Starter data: `Immigration Law Firm/Galaxy_Immigration_starter-kit/` (`01_cases.csv`, `09_case_events.csv`, `10_deadline_rules.json`, `17_review_decisions_seed.jsonl`, `DATA_DICTIONARY.md`).
- Current page and types: `frontend/src/features/review/ReviewPage.tsx`, `useProposals.ts`, `DecisionPanel.tsx`.
- Look and tokens: `design/review/base.css` (frozen palette, copied from `design/ai/base.css`). Do not edit other design files.

## Data model to show
Proposal: `proposal_id` (like `PR-0007`), `case_id`, client name, `kind`, `status`, `proposed_by`, `proposed_at`, `reviewed_by`, `review_reason`, `committed_by`, value summary, `evidence_ids`.
- Kinds: Deadline activation, Form export, Packet approval, Message approval, Case stage change.
- Statuses: Pending legal review, Approved, Rejected, Sent back, Committed.
- Actors: OPS-01 (operations, proposes and commits), LEGAL-01 (attorney, approves, rejects, sends back). Attorney decides. Operations sees the list read only and can apply approved changes.

## What the page must contain
1. Queue of proposals with status filter chips and counts: Waiting for your decision, Approved, Sent back, Rejected, Committed, All. Default is Waiting.
2. Per proposal: id, case link, client, kind, proposer and time, status pill, and one primary action (Review).
3. A one-line summary of what is proposed and a flag chip when something needs care:
   - deadline candidate (verified portal request date plus 10 days) differs from a calendar reminder
   - identity mismatch holds a form field (passport, verified profile and intake call disagree)
   - packet has a missing or unusable document
   - message draft is DRAFT, NOT SENT and answers a question we cannot predict
   - suspicious text found in a PDF (flagged, never followed)
   - earlier rejection preserved with its reason
4. Evidence chips with source ids (`UP-000001`, `EV-0009-2`, `PROFILE-CASE-0001-full_name`).
5. Decision controls: Approve, Reject with a required reason, Send back with a note. Attorney only. A visible role toggle in the mockup (Attorney, Operations). Operations sees the read-only note and an Apply approved changes link.
6. Decided rows show reviewer, time and reason. A rejected row keeps its reason visible.
7. Empty state when nothing is waiting.

## Rules
- US formats: dates like `Oct 24, 2026`, 12-hour times, US spelling. All dates evaluated as of Oct 23, 2026.
- Never use em-dashes or semicolons in visible text.
- No legal advice, no outcome prediction, no eligibility opinion. Client messages labeled DRAFT, NOT SENT.
- Every status is a pill with words, never color alone.
- Restricted matters: details of wrong-client files are hidden.
- Sample data: at least 12 proposals across the demo cases CASE-0001 to CASE-0008 covering every kind, every status and every flag above. Use real case ids and names from `01_cases.csv` and real event ids from `09_case_events.csv`. Invent plausible rows only where the data has none, keeping id formats.
- Plain HTML, CSS and a little vanilla JS. One self-contained file per variant that links only `base.css` (same folder). No external requests, no downloads.
- Light theme. Works from 1280px down to 390px (mobile stacks). Keyboard friendly, visible focus, real buttons and links, `aria-label` on icon buttons.
- Dense but calm. Fewer clicks beats decoration.
- Each page shows a small "Variant N" label in the header, like `design/ai` variants.

## Variants
1. `variant-1-queue-table.html` closest to today. Table with filter chips, a "needs my decision" count, kind and flag columns, sort by oldest first, inline expandable row for the decision.
2. `variant-2-split-inbox.html` list on the left, decision preview on the right (value, evidence chips, flags, history, Approve, Reject, Send back). Clear items without leaving the page. Stacks on mobile.
3. `variant-3-grouped-by-case.html` grouped by case, risk first (conflicts, identity holds, restricted), with a collapsed "already decided" section.

## Output
Write ONE file at the path given in your task. After writing, open it in a browser only if cheap. Report what you built, the situations covered, and anything unmet. Do not commit.
