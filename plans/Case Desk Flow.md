Design before schema

# Case Desk Flow

The whole path from raw intake to an approved, audited action, drawn before any table or route exists. Read figures 1 to 5 in order. The decisions at the bottom are what the schema will be built from.

Deterministic code Claude (language model) Human decision

Figure 1 · System

## Everything flows down one pipeline, and nothing is applied until a human approves

```mermaid
flowchart TB
  subgraph IN["1. Sources: files and claims, all untrusted until checked"]
    direction LR
    Z["Zoom notes"]
    M["Client messages"]
    U["PDF uploads and manifest"]
    P["Verified profiles"]
    E["Portal and calendar events"]
  end
  ING["Ingest and scope: join by case id, sha256 duplicates, quarantine unsure owners"]:::code
  subgraph DOC["2. Document pipeline, one PDF at a time"]
    direction LR
    D1["Extract text layer, OCR if scanned"]:::code --> D2["Claude reads the PDF and returns fields with quotes"]:::llm --> D3["Check each quote exists in the text"]:::code --> D4["Classify and apply document rules"]:::code
  end
  FACTS["Fact table: every value with source, kind, date and citation"]:::code
  CONF["Conflict detector: same field, different values"]:::code
  EXP["Claude explains each conflict in plain words"]:::llm
  subgraph OUT["3. Proposals: drafted, never applied"]
    direction LR
    O1["Checklist and packet index"]:::code
    O2["Form draft, every field cited or unknown"]:::llm
    O3["Deadline: verified event plus 10 days"]:::code
    O4["Client reply marked DRAFT_NOT_SENT"]:::llm
  end
  Q["Review queue"]:::human
  L["LEGAL approves or rejects"]:::human
  C["OPS commits the approved action"]:::code
  A["Audit log: who, what, when, evidence"]:::code
  IN --> ING --> DOC --> FACTS --> CONF --> EXP --> OUT --> Q --> L --> C --> A
  L --> A
  classDef code fill:#dbe8ff,stroke:#1b5fd1,color:#14213a
  classDef llm fill:#efe5fb,stroke:#7a3fc4,color:#14213a
  classDef human fill:#dff3e8,stroke:#17754a,color:#14213a
```

Claude appears in three places: reading a PDF, explaining a conflict, and drafting words. Every other step that could change a date, an identity or a permission is plain code, and the only way out of the proposal stage is through a LEGAL decision.

Figure 2 · One upload

## Uploaded is not usable: each PDF ends in exactly one outcome

```mermaid
stateDiagram-v2
  [*] --> Received
  Received --> Duplicate: same sha256 as an earlier upload
  Received --> Read: new file
  Read --> Quarantined: owner unsure or wrong case
  Read --> Superseded: newer version of the same document
  Read --> Classified: category found from content
  Classified --> Invalid: fails its rule
  Classified --> Usable: passes its rule
  Usable --> Superseded: newer version arrives later
  Quarantined --> Classified: reviewer confirms the owner
  Duplicate --> [*]
  Invalid --> [*]
  Usable --> [*]
  note right of Read
    Instructions found inside the PDF are flagged and never obeyed
  end note
```

The outcome and its reason are stored per upload, so the exception queue can show "UP-000007, duplicate of UP-000001" without recomputing. A judge's new PDF takes the same path as the 603 practice files.

Figure 3 · One run

## Who talks to whom when a case is opened and a deadline is approved

```mermaid
sequenceDiagram
  autonumber
  actor OPS as OPS user
  participant UI as Web app
  participant API as Backend
  participant AI as Claude
  participant DB as Database
  actor LG as LEGAL user
  OPS->>UI: open a case or upload a new PDF
  UI->>API: process this case
  API->>DB: load records for this case only
  loop each new PDF
    API->>AI: PDF and rules inside an untrusted-data envelope
    AI-->>API: JSON fields with quotes and pages
    API->>API: verify quotes, classify, apply rules
  end
  API->>API: build fact table and find conflicts
  API->>AI: explain conflicts, draft form notes and reply
  AI-->>API: cited drafts as JSON
  API->>DB: save findings and proposals as pending
  UI-->>OPS: checklist, conflicts, drafts, deadline proposal
  OPS->>API: propose deadline with idempotency key
  LG->>API: approve or reject with a reason
  API->>DB: update status and write audit line
  OPS->>API: commit
  API->>DB: mark committed and write audit line
```

The model never touches the database. It returns JSON to the backend, which checks it and decides what to store. Step 4 is where case scoping is enforced, so no other case's data can reach the model.

Figure 4 · One proposal

## The approval gate: states a proposal can be in

```mermaid
stateDiagram-v2
  [*] --> PendingLegalReview: OPS proposes with an idempotency key
  PendingLegalReview --> Approved: LEGAL approves
  PendingLegalReview --> Rejected: LEGAL rejects with a reason
  Approved --> Committed: OPS commits
  Committed --> [*]
  Rejected --> [*]
  note right of Rejected
    A rerun may suggest again as a new proposal but never edits this decision
  end note
  note left of PendingLegalReview
    Same key sent twice returns the same proposal
  end note
```

The same machine serves deadline activation, reviewed form export, packet approval and approved message status. Commit is refused unless the state is Approved, and the audit log gets one line per transition.

Figure 5 · Screens

## What the user sees, in the order of the demo

Six screens, one actor switcher in the header. Wireframes show content, not styling.

**1 Case list**/cases

Search case, client, receipt

StagePriorityNeeds attention 12

CASE-0009 · INTAKE_REVIEW · OPS-05 · deadline in 1 day

CASE-0001 · INTAKE_REVIEW · 1 conflict

**2 Case detail**/cases/:id

RESTRICTEDOPS-02LEGAL-02

Proposed deadline 2026-10-24 · calendar says 10-27

SourcesDocumentsConflictsChecklistFormTimelineDrafts

**3 Documents**exception queue

UP-000001 · PASSPORT · USABLE

UP-000007 · PASSPORT · DUPLICATE of 01

UP-0000xx · letter · QUARANTINED

Client said "UNSPECIFIED" → read as EMPLOYER_LETTER

**4 Conflicts**side by side

**Surname** CONFLICTED

Dawan · Zoom Z-0001 · claim

Dhawan · profile + UP-000001 · evidence

Open review request

**5 Review queue**LEGAL view

ACT-000001 · DEADLINE_ACTIVATE · 2026-10-24

Trigger EV-0009-RFE (verified) + 10 days · rule SYN-DEADLINE-V1

ApproveReject (reason required)

**6 Audit trail**per case

PROPOSE · OPS-01 · 07:38

REVIEW_APPROVE · LEGAL-01 · 07:38

MOCK_COMMIT · OPS-01 · 07:38

Every line links to its evidence

Trust zones

## Who decides each thing

| Decision | Claude | Code | Human |
| --- | --- | --- | --- |
| What a PDF says | reads, quotes | verifies the quote |  |
| Which category it is, and is it usable | suggests | applies the rules |  |
| Whose document it is |  | decides, quarantines if unsure | confirms |
| Do two sources conflict |  | compares values |  |
| Why they conflict, in words | explains |  | resolves |
| Form field values | suggests with citations | checks citations | LEGAL approves export |
| Deadline date |  | trigger + 10 days | LEGAL activates |
| Client reply | drafts | marks not sent | LEGAL approves status |
| Who may do what |  | enforces |  |

Before the schema

## Decisions to settle together

Each answer fixes a table or a route. My recommendation is first.

1. **Database.** SQLite for speed of setup; Postgres in Docker only if you expect parallel writers. One file is easier to reset between demo runs.
2. **One fact table or many.** A single `facts` table (case, field, value, source kind, source id, quote, date) makes conflict detection one query and keeps every citation uniform.
3. **Sync or background processing.** Run a case in a background task and let the UI poll for status. A judge's upload then shows progress instead of freezing.
4. **Where case scoping lives.** Every query takes a case id in one data-access layer, so no route can read across cases by mistake.
5. **Seeded review decisions.** Load `17_review_decisions_seed.jsonl` as real rejected proposals, so the CASE-0012 rerun test is just another case.
6. **Cache key.** Claude results keyed by file sha256 plus prompt version, so reruns are free and a prompt change invalidates cleanly.

Next step once these are agreed: derive the tables from figures 2 and 4 (upload outcome, proposal state) and the fact table, then the routes from figure 3.