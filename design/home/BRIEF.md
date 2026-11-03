# Home page brief (shared by all three variants)

Design the landing page of Case Desk for the **operations user** (OPS). It is the first screen after opening the app. An operations user should know in under 10 seconds what needs them, what is due, and what just changed, and reach any case in one click or one keystroke.

## Source of truth
- Hackathon guide: `Immigration Law Firm/Galaxy_AI_Spartans_Immigration_WebApp_Developer_Guide.pdf` (text copy at `/tmp/claude-679401117/guide.txt`).
- Data: `/home/giri@ad-galaxyweblinks.com/Documents/giri_docs/hackathon/hackathon-participants/Immigration Law Firm/Galaxy_Immigration_starter-kit/` (read `01_cases.csv`, `02_zoom_intake_notes.jsonl`, `05_document_manifest.csv`, `07_case_profiles.csv`, `09_case_events.csv`, `10_deadline_rules.json`, `11_web_app_schema.json`, `DATA_DICTIONARY.md`).
- Existing look and tokens: `/var/www/php73-app/TeamEcho/design/variant-a-FROZEN.html` (colors, fonts, radius, header). Reuse its tokens so the page feels like the same app. Do not edit that file.
- Plans: `/var/www/php73-app/TeamEcho/plans/Case Desk Flow.md` (figure 5 case list wireframe) and `/var/www/php73-app/TeamEcho/plans/HANDOFF.md`.

## What the page must contain
1. **Case list with search.** All cases reachable. Each row: case id, client name, stage, assigned OPS and legal reviewer, priority, restricted indicator, review indicators, one line reason. The required list view is "case_id, stage, owner, restricted case count, review indicators". Search by name, case id or receipt number. Filters for stage and for needs attention.
2. **Needs attention, complete.** Every case that is blocked or waiting on a person, grouped or tagged by reason. Cover ALL of these known situations, each with its own label, a short reason and the one next action:
   - Document defects: DUPLICATE, WRONG CLIENT (quarantined, details hidden), mixed clients by page, UNREADABLE or rotated scan, EXPIRED passport, STALE employer letter (dated before Sep 1 2026), OLDER VERSION (superseded), NEEDS TRANSLATION, missing required document (passport, arrival record, employer letter, August pay, September pay, prior notice), wrong pay period, prior notice without reference number.
   - Facts: IDENTITY MISMATCH (spelling differs between passport, verified profile and intake call), other cross-source conflicts (employer, dates, address).
   - Security: SUSPICIOUS TEXT inside a PDF (flagged, never followed).
   - Deadlines: verified portal request date differs from the calendar entry (DEADLINE CONFLICT), deadline proposal waiting for legal approval, deadline due soon or overdue.
   - Approvals: waiting for LEGAL (deadline activation, form draft, evidence packet, client message), proposal REJECTED with a reason (a rerun must not overwrite it), info requested by the attorney, sent back to OPS.
   - Client: unsent client message draft (DRAFT, NOT SENT), unsupported client question (never predict outcomes).
   - Stages from the data: INTAKE_REVIEW, DOCUMENT_COLLECTION, EVIDENCE_REVIEW, READY_FOR_LEGAL_REVIEW, WAITING_FOR_PORTAL_EVENT, ON_HOLD.
3. **Recent activity.** A feed from the audit trail: who, what, when, which case, with a link. Use the real audit actions: UPLOAD_RECEIVED, DUPLICATE_DETECTED, DOCUMENT_READ, QUARANTINED, INJECTION_FLAGGED, CONFLICT_OPENED, REVIEW_REQUESTED, PROPOSE, REVIEW_APPROVE, REVIEW_REJECT, COMMIT, AI_DRAFT, INFO_REQUESTED.
4. **Deadlines.** A view of upcoming and overdue deadlines. Rule: a candidate deadline is a verified `MOCK_PORTAL` event of type `MOCK_EVIDENCE_REQUEST_RECEIVED` plus 10 calendar days, proposal only, legal approval required. Calendar entries never activate a deadline, show a contradiction flag when one differs. Show state: proposed, approved, conflict, overdue. All dates are evaluated as of **Oct 23, 2026**, never the clock.
5. **A way to start work:** an "Upload a new case" entry that opens the upload wizard (a button is enough).

## Rules
- US formats: dates like `Oct 24, 2026` or `10/24/2026`, 12-hour times, US spelling.
- Never use em-dashes or semicolons in any visible text.
- No legal advice, no outcome prediction, no eligibility opinion. Client messages are always labeled DRAFT, NOT SENT.
- Every status is a pill with words, never color alone. Use straight rounded pills.
- Every claim of fact shows its source id chip (for example `UP-000001`, `EV-0009-2`, `PROFILE-CASE-0001-full_name`).
- Restricted matters: quarantined files from another client are not viewable and their details are hidden.
- Do not hardcode a single demo case. Show variety across at least 14 cases covering every situation above. Use real case ids and names from `01_cases.csv` and real event ids from `09_case_events.csv`. Where the data has no example of a situation, invent clearly plausible sample rows but keep ids in the same format and mark nothing as real.
- No new libraries. Plain HTML, CSS and a little vanilla JS, one self-contained file, no external requests, no fonts to download.
- Light theme matching variant A. Works from 1280px wide down to 390px (mobile stacks). Keyboard friendly, visible focus, real buttons and links, `aria-label` on icon buttons.
- Desktop first. Operations works all day on this page, so keep it dense but calm. Fewer clicks beats more decoration.

## Operations time savers to include
- A search box focused with `/` that filters instantly.
- Counts on every filter chip.
- One primary action per row (for example "Review conflict", "Open documents", "Send to attorney").
- Sort by what is due soonest first within each group.
- A "just me" toggle for cases assigned to the acting OPS user, default on.
- Collapsed low-priority groups with counts so nothing hides.

## Output
Write ONE file at the path given in your task. It must open by double-click in a browser. Include a visible switcher or small label that says which variant it is. After writing, open it with the chrome-devtools tools at `file://<path>`, take a screenshot at 1440x900 and at 390x844, fix any overlap or cut-off text, and report what you built, which situations are covered, and anything you could not satisfy.
