# Document types and fields

Keys are fixed by the field definitions. They look like `CATEGORY.Field Name` and match `source_candidates` in the starter kit file `08_form_field_map.json`, so form drafting reads them directly. A label in another language still maps to the same key.

| Prompt key | Category | Recognition hint | Fields (required marked with *) |
|---|---|---|---|
| `doc.read.passport` | `PASSPORT` | Identity or travel document with a document identifier and expiry | Applicant*, Date of Birth*, Document Identifier*, Nationality, Expires*, Page Applicants (array) |
| `doc.read.arrival_record` | `ARRIVAL_RECORD` | Travel entry record | Applicant*, Last Recorded Entry*, Travel ID* |
| `doc.read.employer_letter` | `EMPLOYER_LETTER` | Employer verification letter | Applicant*, Employer*, Employment start*, Document Language, Signed On |
| `doc.read.pay_statement` | `PAY_STATEMENT` | Pay statement with a pay period | Applicant*, Employer*, Pay Period*, Net Pay*, Pay Record |
| `doc.read.prior_notice` | `PRIOR_NOTICE` | Prior case reference notice | Applicant*, Reference Number*, Previous Case Event* |
| `doc.read.certified_translation` | `CERTIFIED_TRANSLATION` | Certified translation of another document | Applicant*, Translation Of*, Language*, Certified* |
| `doc.read.generic` | `UNKNOWN` | Fallback when nothing matches | Any visible label and value pair |

Check the YAML files in `backend/app/ai/prompts/` for the exact optional and required flags. The YAML is the seed. The live definitions are in the database and may have newer versions.

## Notes

1. One pay prompt serves August and September. It returns `Pay Period` and code decides `PAY_AUG` or `PAY_SEP`.
2. A multi-case bundle is handled by the page-level categories and `owner_names` from classify. Core decides ownership.
3. The generic read returns a `fields` array of `{label, value, quote, page}` because the API rejects objects with free keys. Code turns it into keys named `UNKNOWN.<label>`. A repeated label gets a number, for example `UNKNOWN.Applicant 2`.
4. Dates are ISO `YYYY-MM-DD`. Names and identifiers are copied as written and never corrected or transliterated.
5. Required fields are in the schema `required` list so the model always returns them. Optional fields are omitted when missing.

## Categories

A category is a read prompt with an uppercase name. The key must be `doc.read.<category lowercase>`. `UNKNOWN` is reserved for the generic prompt. `REVIEW_REQUIRED` is a classify result and has no prompt. To add a type, create a read prompt in the UI or with `POST /api/ai/prompts`.
