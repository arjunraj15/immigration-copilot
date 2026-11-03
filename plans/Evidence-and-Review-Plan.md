# Evidence and review plan

How the app treats each source, what it requires, and when a case goes to Legal. It follows the hackathon rule files first.
Anything added beyond them only adds care and never changes a result the rule files define.

Sources: `04_case_document_rules.json`, `08_form_field_map.json`, `13_synthetic_form_template.json` and the Developer Challenge Guide.

## 1. What counts as evidence

| Source | Counts as | Why |
|---|---|---|
| Uploaded PDF the rules accept (usable, right case, not a duplicate) | Evidence | Rule file: "Documents and human-verified profiles are evidence" |
| Case profile (`07_case_profiles.csv`, rows `HUMAN_VERIFIED`) | Evidence, shown as "checked earlier (may be stale)" | Same rule. The guide calls the profile "previously verified (possibly stale)" |
| Zoom intake summary | Claim | Rule file: "Zoom summaries are unverified claims". Each note carries `approved_as_fact: false` |
| Client messages (email, WhatsApp) | Claim | Unverified |
| Calendar reminders | Claim, never a deadline | `source_verified` is FALSE |
| AI output | Never evidence | Guide: "AI output is not evidence" |

A claim is kept and shown. It never becomes a fact on its own, and it never settles a disagreement.

## 2. The mismatch rule: profile against Zoom intake

When the case profile and the Zoom intake give different values for the same field, the field is a **conflict** and goes to **Legal review**.

- The field is held. The form draft row is `HELD_FOR_REVIEW`, has no value, and cites every disagreeing source.
- A human review request is opened (`review_requests`, state `review_open`). Nothing is picked for anyone.
- Legal (the assigned reviewer) decides; Operations may only suggest a value or leave it to Legal, and may decide a medium severity field with a written reason.
- The decision is stored as an insert-only review decision, so a re-import never undoes it.
- The same rule covers every field Zoom can state: full name, employer, employment start, last entry date and mailing address. It also covers a document against the profile and a document against a document. A test checks all five Zoom fields.
- Values that only differ in writing (order, an initial, accents, "LLC", abbreviations, date style) are the same value. A different spelling, number or word is not. Dawan and Dhawan stay a conflict.

When they match, the field agrees and needs no review.

## 3. Required documents

Only the kit's six: passport, arrival record, employer letter, August pay statement, September pay statement and prior notice. Each needs one usable file.

- The mailing address is not a required document. The kit names only the profile and client messages as its sources.
- The last entry date comes from the arrival record or the profile. The arrival record is required as a document by the kit's rules. A last entry date that rests on the profile is accepted evidence and is not asked for again.

## 4. Address

- The profile is the accepted evidence. A message that states another address is a claim and conflicts with it (the CASE-0013 trap). It is shown for Legal and never applied on its own.
- An address proof (utility bill, lease, change of address confirmation) is optional supporting evidence. It is not required for any case.

## 5. Showcase: a new document type through AI customisation

The kit has no address document. The app reads one anyway, which shows the AI setup can be extended without code:

1. Open **AI** and find the read prompt `doc.read.address_proof`. It defines the fields to read (applicant, address, document date, date of birth) and the same untrusted-text rules as every other document type.
2. Upload `data/extra-documents/CASE-0001/ADDR-0001_utility_bill.pdf` to CASE-0001. The classifier names it ADDRESS_PROOF from its content. The filename plays no part.
3. The address on the Form draft now cites the bill next to the profile and the Zoom note.
4. Upload `CASE-0013/ADDR-0013_change_of_address.pdf` to CASE-0013 to see the claimed new address backed by a document while the profile still disagrees, which Legal must decide.

A prompt version can be edited and activated from the AI page and the next read uses it. The PDFs come from `backend/scripts/make_address_pdfs.py`.

## 6. Added beyond the rule files, and why each is safe

| Extra | What it does | Why it cannot change a rule file result |
|---|---|---|
| Value gate | Treats writing variants of a name, employer or address as one value | Decided in code first. A different spelling or number is always a conflict |
| Case-level name check | A document must match any name on file, so it is the right case | Only flags. Which spelling is right stays a Legal decision |
| Reference serial check | Flags a case whose reference numbers come from two sets | Flag only, nothing is quarantined |
| US date display and parsing | MM/DD/YYYY everywhere, written dates read properly | Display and reading only. An ambiguous date is left as written |
| Claim-only values on the draft | Fill the row from the claim and mark it for review | Never counts as evidence |
| Delete case | Hides a test case, keeps the audit trail | No effect on rules |
