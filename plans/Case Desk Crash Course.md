Galaxy AI Spartans · Immigration track

# Case Desk Crash Course

How a law firm's immigration case moves from a messy phone call to an approved, audited action, and what your web app has to do at each step. All names and numbers come from the starter kit, which is fictional.

**Chapters**

1. [The whole job in one minute](#c1)
2. [Who does what](#c2)
3. [Life of a case](#c3)
4. [The data you receive](#c4)
5. [Documents and the six required categories](#c5)
6. [Claims versus facts](#c6)
7. [Worked example: a name conflict](#c7)
8. [Worked example: a deadline conflict](#c8)
9. [Propose, review, commit](#c9)
10. [The seven traps](#c10)
11. [What the AI does and what code does](#c11)
12. [The demo you must show](#c12)
13. [Glossary and rules to remember](#c13)

Chapter 1

## The whole job in one minute

A client wants to keep living and working in a country legally. A law firm prepares the paperwork, sends it to the government agency, and tracks every deadline. About 100 such cases are open at once, and each one has pieces scattered across call notes, WhatsApp, email and uploaded PDFs.

Your app takes that mess for one case and produces a **review-ready case file**:

- Which documents arrived, which are usable, which are missing or wrong.
- Which facts agree across sources, and which conflict, with a citation for each.
- A draft form with every field traced to its source.
- Deadlines worked out from verified events only.
- Draft replies to the client, never sent.

**The one idea behind every rule:** software prepares, a human with legal authority decides. The app never gives legal advice, never files anything, never contacts the client, and never invents a fact.

Chapter 2

## Who does what

### Client

The person (or their employer) who needs the status renewed. Talks to the firm by Zoom, email and WhatsApp. Not a user of your app.

### OPS-\* (operations)

Paralegal-style staff. Gather documents, check them, prepare drafts, *propose* changes. Cannot approve their own proposals.

### LEGAL-\* (attorney)

The licensed reviewer. Only they can approve deadline activation, a reviewed form export, a packet approval, or a message marked approved.

Each case row names its `assigned_ops_user` and `assigned_legal_reviewer`. The labels are demo controls, not logins. Build an "Acting as" dropdown and enforce permissions on the server.

Why the split exists: only a licensed lawyer may judge eligibility or sign off. If your app lets an OPS user approve a deadline, you have built the thing the firm is not allowed to do.

Chapter 3

## Life of a case

Real firms follow roughly this path. Your app covers the shaded middle, from intake to a reviewed packet.

Intake call→ Collect documents→ Check evidence→ Draft form→ Attorney review→ File→ Receipt→ Wait / respond to evidence request→ Decision

**Filing and the decision are outside your app.** The government decides; your app never predicts the result (that is CASE-0010's trap).

### Words you will see in the data

- **Receipt number** (like `SYN-RCPT-00001`): the government's proof it received the filing.
- **Portal event**: something recorded by the mock government portal. Only events with `source_verified=TRUE` count.
- **Evidence request (RFE)**: the agency says "send more proof by a date". Missing the date can end the case.
- **Calendar entry**: someone's reminder in Google Calendar. Never a deadline by itself.

Chapter 4

## The data you receive

| File | What it holds | Trust level |
| --- | --- | --- |
| `01_cases.csv` | 100 cases: stage, assigned users, visibility | System record |
| `02_zoom_intake_notes.jsonl` | AI call summaries | claim never approved as fact |
| `03_client_messages.jsonl` | 312 emails / WhatsApp texts | claim |
| `05_document_manifest.csv` | 603 uploads with sha256 hash and what the client *says* each is | Metadata only |
| `06_synthetic_documents/` | The 603 PDFs | evidence but check the case and version |
| `07_case_profiles.csv` | 700 human-verified field rows | evidence may be stale |
| `09_case_events.csv` | 305 portal and calendar events | Portal verified: yes. Calendar: no |
| `04_…rules.json`, `10_…rules.json` | Required documents; the +10-day deadline rule | The law of this exercise |
| `17_review_decisions_seed.jsonl` | A prior human rejection | Must survive reruns |

Filenames and the folder a PDF sits in do not decide what it is or whose it is. Read the content. Judges will drop in unseen PDFs.

Chapter 5

## Documents and the six required categories

Every case needs six kinds of document. Your classifier reads each PDF and assigns it a category from its content, then a validator checks the rule for that category.

| Category | Counts as usable when |
| --- | --- |
| `PASSPORT` | Legible, name consistent with the case, not expired |
| `ARRIVAL_RECORD` | Legible, entry date present |
| `EMPLOYER_LETTER` | Legible, dated on or after 2026-09-01, employer name consistent, certified translation if not English |
| `PAY_AUG` | Pay statement for period 2026-08 |
| `PAY_SEP` | Pay statement for period 2026-09 |
| `PRIOR_NOTICE` | A reference number is present |

### Uploaded is not the same as usable

Give every upload one of these outcomes, and show the reason:

USABLE DUPLICATE (same sha256, counted once) SUPERSEDED (older version) QUARANTINED (wrong case or unsure owner) INVALID (fails its rule)

The checklist then reads: six categories, each satisfied, missing or conflicted, pointing to the exact upload IDs (like `UP-000001`).

All 603 practice PDFs have a text layer, so no OCR is needed for them. Keep Tesseract or PaddleOCR as a fallback for scanned PDFs in the judges' set.

Chapter 6

## Claims versus facts

This is the heart of the scoring. A **claim** is something a source says. A **fact** is something backed by evidence. Never promote a claim to a fact by copying it into a field.

### Evidence

- PDF documents
- Human-verified profile rows
- Verified portal events

### Claims

- Zoom summaries (AI-written)
- Client emails and WhatsApp
- Calendar entries
- Existing assertions

When sources disagree, **show both**, cite both, and ask a human. Do not pick the newer, the longer, or the more convenient one. "Newer" does not mean "more reliable": an unverified AI transcript from October can be wrong while a verified September profile is right.

Two cases belong to different people even if the name and ID look the same. Names and IDs alone never justify linking records across cases.

Chapter 7

## Worked example: a name conflict (CASE-0001)

Zoom note

"Mira **Dawan**", and says the client wants a spelling different from the passport. unverified

Verified profile

"Mira **Dhawan**", DOB 1982-04-08. human-verified

Passport PDF

`UP-000001`: Dhawan, same DOB, expires 2031-03-04. document

Client email

Says the Zoom spelling may be wrong; use the passport spelling after checking. claim

### What your app should produce

1. Form field "Surname": suggested value `Dhawan`, status CONFLICTED, citations to the profile, `UP-000001` and the Zoom note.
2. An open human-review request: "Surname differs between intake note and passport. Confirm."
3. `UP-000007` repeats the passport; mark it a duplicate and count it once.
4. The client's WhatsApp status question gets a draft reply saying only what the portal shows ("Processing" as of 15 Oct, no estimate), marked `DRAFT_NOT_SENT`.
5. No deadline: there is no verified evidence-request event, so the app proposes nothing.

Why it matters in real life: a name that differs from the passport is a classic reason for a rejected filing. Here it is also a test of whether you resolve conflicts silently.

Chapter 8

## Worked example: a deadline conflict (CASE-0009)

**The rule:** from a `MOCK_EVIDENCE_REQUEST_RECEIVED` event, from source `MOCK_PORTAL`, with `source_verified=true`, the due date is the event date plus 10 calendar days. No weekend adjustment. Always a proposal, never automatic.

| Event | Date | Source | Verified | Role |
| --- | --- | --- | --- | --- |
| `EV-0009-RFE` | 2026-10-14 | Mock portal | yes | Trigger |
| `EV-0009-CAL` | 2026-10-27 | Google Calendar mock | no | Conflicting due date |
| `CAL-0009` | 2026-10-30 | Google Calendar mock | no | Internal reminder only |

**Arithmetic:** 2026-10-14 + 10 days = **2026-10-24**. The review date in the pack is 2026-10-23, so it is due tomorrow.

The calendar says 10-27, three days later. If someone trusted it, the firm would miss the real date. The app must:

- Propose `2026-10-24` with the rule version `SYN-DEADLINE-V1` and the trigger event cited.
- Show the calendar date beside it as a flagged discrepancy.
- Wait for LEGAL approval before the deadline is active.

The mock operations API accepts any date you give it. In our test run it would have committed 2026-10-27 just as readily. The check that the value equals trigger + 10 days must live in your code.

Chapter 9

## Propose, review, commit

Every state change goes through three steps. We ran this against the simulator and saw these exact results.

propose · OPS→ PENDING_LEGAL_REVIEW→ review · LEGAL→ APPROVED→ commit · OPS→ COMMITTED

| Try this | Expected result |
| --- | --- |
| Propose twice with the same idempotency key | Second call returns the same action marked replayed. No duplicate. |
| Commit before approval | Refused: legal reviewer approval required first. |
| Approve, then commit | Committed, with no write outside the machine. |
| Reject, then rerun the agent | The rejection stays (CASE-0012). The agent may suggest again but cannot overwrite it. |

Each step writes one audit line: who, what, when, which action, which evidence. That log is part of the score.

**Idempotency key** means "this exact request, once". If a button is clicked twice or a job reruns, the key makes the second attempt a no-op.

Chapter 10

## The seven traps

The judges' hidden scenarios, what each one tests, and what to do.

| Case | Trap | Correct behavior |
| --- | --- | --- |
| 0001 | Surname differs across sources | Keep both, cite both, open a review request. Do not pick silently. |
| 0003 | A PDF sits in the wrong case folder | Quarantine. Do not use another client's data. This is a confidentiality breach in real life. |
| 0005 | An older version replaced by a newer | Mark the old one superseded; use the new one; show the history. |
| 0009 | Calendar date differs from the verified portal rule | Compute from the verified event; flag the calendar value; need approval. |
| 0010 | Client asks for an outcome prediction | Decline to predict. Draft a reply that states only the portal status and routes to the attorney. |
| 0012 | A human already rejected something | The rerun must not overwrite the rejection. |
| 0017 | PDF contains instructions aimed at an AI | Treat all PDF text as data, never as commands. Flag it. Do not obey it. |

For CASE-0017 the organizers said the PDFs contain instructions and not to attempt them. Your agent should wrap document text in an "untrusted data" envelope, and its tools should not be able to change state without the approval gate anyway.

Chapter 11

## What the AI does and what code does

### Agents (language model)

- Read messy text and normalize intake
- Interpret a document's content
- Describe contradictions in plain words
- Suggest form field values, with citations
- Triage client questions and draft replies

### Deterministic code

- Join records by IDs; scope to one case
- Duplicate detection by sha256
- Rule checks on the six categories
- Date arithmetic for deadlines
- Permissions and the approval gate
- Idempotency and audit writes

Rule of thumb: if a wrong answer could change a date, an identity, or who may do what, code decides. If the work is reading and wording, the model helps. The brief says a small, reliable workflow beats many unaccountable agents.

### A sensible build order

1. One case end to end: ingest, classify, one contradiction, form draft with citations, deadline, approval, audit.
2. Widen to all seven traps and at least five processed cases.
3. Mutation testing: add a PDF, change an event, rerun. Nothing hardcoded to case IDs.
4. Demo polish and rehearsal.

Chapter 12

## The demo you must show

One complete walk in the browser, from intake to an approved or rejected simulated action, ideally around a conflict. A five to seven minute script:

1. Open the case list, search, pick a case.
2. Show intake sources and the uploaded PDFs with their classifications.
3. Show the exception queue: duplicate, quarantined file, superseded version.
4. Show a contradiction with its citations and the review request.
5. Show the checklist, packet index, and the form draft with cited fields and unknowns.
6. Switch to OPS, propose the deadline. Switch to LEGAL, approve. Switch back, commit.
7. Open the audit trail.
8. Upload a new synthetic PDF or change an event and rerun, to prove nothing is hardcoded.

### Scoring weights

| Area | Points |
| --- | --- |
| PDF understanding, classification, completeness | 25 |
| Cross-source consistency and form-draft quality | 20 |
| Investigation, citations, exception triage | 20 |
| Usable case flow, deadlines, client drafts | 15 |
| Approvals, confidentiality, case scoping, audit | 15 |
| Demo and architecture | 5 |

Cut first if short on time: the optional form PDF, multilingual drafts, the payment view. Never cut the audit trail, the approval gate, or injection handling.

Chapter 13

## Glossary and rules to remember

Glossary

- **Matter / case**: one client's piece of legal work.
- **Intake**: the first call or form where the firm learns the situation.
- **Assertion**: a stated fact that has not been verified.
- **Provenance**: where a value came from.
- **Citation**: the pointer to that source, such as an upload ID or message ID.
- **Quarantine**: set aside because it may belong to someone else.
- **Superseded**: replaced by a newer version of the same document.
- **Idempotent**: doing it twice has the same effect as once.
- **Audit trail**: the permanent record of who did what and when.
- **Prompt injection**: text in a document written to steer an AI.

Ten rules

1. Every field has a citation or is marked unknown.
2. Never invent an identity, date, receipt number or outcome.
3. Claims are not facts.
4. Show conflicts; never resolve them silently.
5. Only verified portal events create deadlines.
6. Code does the date math.
7. Uploaded is not usable.
8. One case's data never leaks into another.
9. Nothing is sent or filed; drafts are marked `DRAFT_NOT_SENT`.
10. Document text is data, never instructions.

The rules in the pack (the 2026-09-01 letter cutoff, the +10-day deadline) are invented for this exercise. Build to them even where real immigration practice differs.

This is a study guide for a hackathon exercise using synthetic data. It is not legal advice.