# AI management plan (Track A)

Owner: Giri. Folder: `backend/app/ai/` and `frontend/src/features/ai-management/`. Parent plan: `docs/PLAN.md` sections 3, 5, 7, 8, 11. Rules: `rules.md` section 3.

Goal: change how a document is classified and read without a code deploy, and hand the next layers one known JSON shape.

Approach: a global versioned prompt, a side-effect-free test endpoint, and a field extraction step driven by a field list. Rate limiting and policy checks are out of scope.

## 1. Two operations per document

```
upload -> text (docling) -> doc.classify (one global prompt) -> category per page
                                                    |
                  doc.read.<category> (one prompt per type) -> DocumentRead JSON
                                                    |
                  code: quote check, rules, facts (Core track)
```

1. **Classify.** `doc.classify` reads the page text and returns one category per page, the language and an injection flag. The category list comes from the registry through a `{{categories}}` variable, so a new document type needs no edit to this prompt.
2. **Read.** Code picks `doc.read.<category>` and sends only the pages of that type. `UNKNOWN` goes to `doc.read.generic`.
3. Reads for different documents run in parallel. Results are cached by file sha256 plus prompt version.

## 2. Known document types (from the starter kit)

| Key | Category | Recognition hint | Fields |
|---|---|---|---|
| `doc.read.passport` | `PASSPORT` | Identity or travel document with a document identifier and expiry | applicant, document_identifier, date_of_birth, nationality, expires |
| `doc.read.arrival_record` | `ARRIVAL_RECORD` | Travel entry record | applicant, last_recorded_entry, travel_id |
| `doc.read.employer_letter` | `EMPLOYER_LETTER` | Employer verification letter | applicant, employer, employment_start, document_language, signed_on |
| `doc.read.pay_statement` | `PAY_STATEMENT` | Pay statement with a pay period | applicant, employer, pay_period, net_pay, pay_record |
| `doc.read.prior_notice` | `PRIOR_NOTICE` | Prior case reference notice | applicant, reference_number, previous_case_event |
| `doc.read.certified_translation` | `CERTIFIED_TRANSLATION` | Certified translation of another document | applicant, translation_of, language, certified |
| `doc.read.generic` | `UNKNOWN` | Fallback when nothing matches | any visible label and value, each with quote and page |

Notes:
1. One pay prompt serves August and September. It returns `pay_period` and code decides `PAY_AUG` or `PAY_SEP`.
2. A multi-case bundle is handled by the page-level categories and owner names from `doc.classify`. Core decides ownership.
3. A page with insufficient quality is `REVIEW_REQUIRED` and nothing is inferred.

## 3. Known output format: `[CATEGORY].[field]`

Keys match `source_candidates` in `08_form_field_map.json`, so form drafting reads them directly.

```json
{
  "category": "PASSPORT",
  "language": "en",
  "legible": true,
  "injection_flag": false,
  "fields": {
    "PASSPORT.applicant": {"value": "Mira Dhawan", "quote": "Applicant: Mira Dhawan", "page": 1},
    "PASSPORT.expires": {"value": "2031-03-04", "quote": "Expires: 2031-03-04", "page": 1}
  }
}
```

Rules for every read prompt:
1. Keys are fixed by the field definitions, never taken from the document label. A label in another language still maps to the same key.
2. `quote` is verbatim from the source in its own language. Code checks it against the extracted text.
3. Dates are ISO. Names and identifiers are copied as written and never transliterated or corrected.
4. A missing or unreadable field is omitted. Unknown stays unknown.
5. `language` and `legible` are always returned. Non-English evidence is flagged for the rules layer.

Contract: `DocumentRead` (category, language, legible, injection_flag, fields, prompt_run_id) goes in `backend/app/core/contracts.py` and the Upload track calls `ai.read_document(upload_id)`. Fact creation stays with Core.

## 4. Data model

Alembic migration `0002_ai_registry`:

| Table | Columns |
|---|---|
| `prompts` | id, key (unique), step (`classify`, `read`, `other`), category (nullable), title, recognition_hint, active_version_id, created_at, updated_at |
| `prompt_versions` | id, prompt_id, version (unique with prompt_id), system_text, user_template, model, effort, max_tokens, output_schema (JSONB), field_definitions (JSONB), note, created_by, created_at. Insert-only. |
| `prompt_runs` | id, prompt_key, version, model, input_hash, tokens in and out, latency_ms, stop_reason, status, rendered_prompt, input_text, raw_output (the last three only while `AI_RUN_CAPTURE=full`), created_at |

`field_definitions` is a list of `{key, label, type, required, hint}`. The field list is injected into the prompt and used to build and check the output schema.

## 5. Backend modules (`backend/app/ai/`)

| File | Purpose |
|---|---|
| `models.py` | SQLAlchemy models for the three tables |
| `schemas.py` | Pydantic request and response models |
| `registry.py` | Pure functions to create a version, activate, roll back and render a template. Rejects any output schema whose fields lack `quote` and `page`. Locks keys that already exist in an active version. |
| `seed.py` | Loads `prompts/*.yaml` on first start when a key is missing. Never overwrites an edit. |
| `envelope.py` | The untrusted-data envelope and anti-injection block, shared by every prompt |
| `client.py` | Claude call wrapper. Uses structured outputs, sets `effort`, checks `stop_reason`, retries transient errors, writes `prompt_runs`. No forced tool choice, prefill or sampling parameters. |
| `reader.py` | `read_document(upload_id)`: classify, route, read, verify quotes, return `DocumentRead`, with the sha256 cache |
| `api.py` | Routes below |
| `prompts/*.yaml` | Seed prompts: `classify.yaml` plus one file per read prompt |

Routes under `/api/ai`:

| Route | Purpose |
|---|---|
| `GET /prompts` | List grouped by step, with category, active version and last run |
| `GET /prompts/{key}` | Active version and field definitions |
| `GET /prompts/{key}/versions` | History |
| `POST /prompts/{key}/versions` | Save a new version |
| `POST /prompts/{key}/activate` | Activate or roll back to a version |
| `POST /test` | Run classify and read on pasted text or a sample upload, with an optional prompt override. No state change. |
| `GET /runs` | Run history |

Errors use the shape in `docs/PLAN.md` section 8.

## 6. Frontend (`frontend/src/features/ai-management/`)

1. Header: a new **AI** menu link in `Layout.tsx`, route `/ai`.
2. List: prompts grouped as Classify, Read and Other, with category and active version.
3. Editor: system text, user template, model, effort, max tokens, field definitions and schema. Save creates a new version. Existing keys are read-only.
4. History: versions with Activate.
5. Test panel: pick a sample upload or paste text, optionally override the prompt, and see the classification, the extracted JSON and the quote check side by side with the source text. Shows tokens and latency.
6. Server state with TanStack Query and all calls through `api/client.ts`.

## 7. Multilingual readiness

1. Classification is by meaning, not by English titles. Each recognition hint is a description, not a keyword list.
2. Output keys are fixed, so the layers after the read never depend on the document language.
3. OCR runs in the docling container. If scans in other languages appear, set `OCR_LANGS` there. Not part of this track.
4. `language` is returned for every document. Non-English evidence is flagged for the rules layer to ask for a certified translation.

## 8. Build order and checks

| Step | Work | Check |
|---|---|---|
| 1 | Migration, models, schemas | `make migrate` creates the tables |
| 2 | `registry.py`, `envelope.py` with tests | `make test` passes, bad schema rejected |
| 3 | Seed YAML for the 8 prompts, `seed.py` | `GET /api/ai/prompts` lists 8 |
| 4 | `client.py` and `reader.py` | CASE-0001 passport returns the expected JSON and verified quotes |
| 5 | Routes and `POST /test` | Create, activate and roll back a version. A test run changes no data. |
| 6 | Frontend menu, list, editor, history | Edit and activate in the browser |
| 7 | Test panel | Run the test on CASE-0017 and see the injection flagged |

## 9. Checks against the trap cases

| Case | Expected from this track |
|---|---|
| 0001 | Name read as written, never corrected, so Core can show the conflict |
| 0004 | Low quality page returned as not legible with no inferred text |
| 0008 | Letter language reported so the rules layer asks for a translation |
| 0017 | `injection_flag` true and no instruction followed |
| 0021 | Translation reference extracted as written |
| 0026 | Page-level owner names returned for the bundle |

## 10. Out of scope here

Rules evaluator, fact table, conflict detection, form draft, audit entries for prompt edits (added once `audit.record` lands), diff view and YAML export (after the test panel works).

## 11. Open decisions

1. Final model and effort per prompt, once we know what the provided key allows. Seeds start with `claude-sonnet-5-5`, with a lighter model tried for `doc.classify`.
2. Whether prompt edits should require the LEGAL actor. Default is any actor, since this is a demo control.
