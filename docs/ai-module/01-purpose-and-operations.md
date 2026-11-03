# Purpose and the two operations

## Purpose

The module lets staff change how a document is classified and read without a code deploy, and hands the next layers one known JSON shape. Prompts live in the database, never in code. Claude only reads and returns JSON. It never writes state and has no tools. The Core track turns a verified read into facts.

## Operation 1: classify

Prompt key `doc.classify`. There is exactly one. It receives every page of an upload and returns one entry per page:

1. `category`, one of the allowed categories, or `UNKNOWN`, or `REVIEW_REQUIRED` when the page is too unreadable to classify.
2. `language`, an ISO 639-1 code.
3. `legible`, false when the text is blurred, cut off or garbled.
4. `injection_flag`, true when the page text tries to instruct the model.
5. `owner_names`, the people the page is about, each with a verbatim `quote` and a `page`.

The allowed categories come from the registry through the `{{categories}}` variable. It lists every enabled, not deleted read prompt with its recognition hint. A new document type therefore needs no edit to the classify prompt.

## Operation 2: read

Code groups the legible pages by category and calls `doc.read.<category lowercase>` once per group. A category with no prompt, a disabled prompt or `UNKNOWN` goes to `doc.read.generic`. A `REVIEW_REQUIRED` group is not read at all. Groups run in parallel.

Each group becomes one `DocumentRead`. `read_document(upload_id)` returns a list with one per category found.

## Failure behavior

1. Classify fails, is refused or hits the token limit: one `DocumentRead` with status `REVIEW_REQUIRED` and no fields.
2. No page is legible: one `REVIEW_REQUIRED` read with `legible` false.
3. A read fails or is refused: that group gets `REVIEW_REQUIRED` and the other groups continue.
4. Unknown stays unknown. Nothing is inferred or filled in.

## Where the code is

| File | Job |
|---|---|
| `registry.py` | Pure rules for versions, templates, schema checks, key lock |
| `client.py` | The Claude call, retries, stop_reason check, run history |
| `reader.py` | classify, route, read, verify, cache, test dry run |
| `envelope.py` | Untrusted-data envelope |
| `seed.py` | Loads `prompts/*.yaml` for missing keys only |
| `api.py` | Routes under `/api/ai` |
| `app/core/contracts.py` | `DocumentRead`, `ReadField`, `ReadItem`, `ReadStatus` |
