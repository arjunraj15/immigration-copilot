# Document loader plan

The loader turns an upload into page text for `read_document` (`backend/app/ai/reader.py`). The reader already classifies, reads by category in parallel and verifies every quote against the page text. What is missing is the code that supplies `LoadedUpload(sha256, pages)`. This plan covers that loader and the fallback ladder for pages that do not extract well.

## Rules this plan follows

- Documents are untrusted data. Text goes to the model only inside the envelope from `app/ai/envelope.py`. Instructions found inside a document are flagged and never followed.
- A quote counts as verified only when it is found in text we extracted ourselves.
- An unreadable or rotated page is `REVIEW_REQUIRED`. Contents are never inferred.
- Case scoping. Only pages that belong to the case being processed reach the model. Pages owned by another case are quarantined and their details stay hidden.
- Same file, same result. Reads are cached by sha256 plus prompt version.

## Loader steps for one upload

1. **Receive.** Compute the sha256 from the stored bytes. A hash already seen in this case is `DUPLICATE` and is not read again.
2. **Check the file.** Allowed types only (PDF, JPG, PNG, TIFF, DOCX), size limit, and the signature bytes must match the type. Anything else is `INVALID` with a reason.
3. **Split into pages.** One entry per page, with its page number. Images and DOCX are converted to pages first.
4. **Extract each page with the ladder below.** Record which step produced each page.
5. **Check ownership.** Read the `Synthetic Matter:` line on each page. Pages owned by another case are quarantined and left out of the model input. A mixed bundle keeps the foreign page numbers on the record.
6. **Hand the case pages to `read_document`.** It returns one `DocumentRead` per category.
7. **Apply the document rules** from `04_case_document_rules.json` (expired passport, stale letter, pay period, translation, prior notice reference). Write the outcome and reason on the upload row.
8. **Audit.** One entry per upload for received, read, quarantined, duplicate and injection flagged.

## The fallback ladder, per page

| Step | Used when | Result | Verified quotes |
|---|---|---|---|
| 1. Text layer (pdfplumber, pypdf) | The page has enough text | `TEXT_LAYER` | Yes |
| 2. OCR (docling in the container) | Deferred. Not built yet. A page that fails step 1 goes straight to step 3 | none | not applicable |
| 3. Page image sent to the model | The text layer is poor and an image covers most of the page | `IMAGE` | No, so values are `UNVERIFIED` |

OCR is deferred by decision. The loader has a short comment where an OCR step can be added later. Until then the stored text source is `TEXT_LAYER` or `IMAGE`.

- **Enough text** is a measured threshold, for example fewer than a set number of characters or too few `Label: value` lines. Tune it on the starter files.
- **Page images, not the full PDF.** Only the failing pages of the right case are sent. This keeps other clients' pages out of the prompt and keeps the cost down. The page is rotated upright first when rotation is detected.
- **Vision is a suggestion, not evidence.** A value read from an image never makes the document `ACCEPTED` and never becomes a `PROPOSED` form field by itself. It goes to the reviewer with the page image beside it, marked "read from image, not verified".
- **Hard stop.** Blank, corrupted or too poor pages are `REVIEW_REQUIRED` with no model call.
- **Cap on cost.** Vision runs once per page and the result is cached by the page hash.

## What gets stored per page

`document_reads` already has `text_source`, `page_count`, `text_sha256`, `extracted`, `injection_flags`, and the verified and unverified field counts. Add to the extracted JSON, per page: the step used, the character count and the rotation applied. The audit line records the step so a reviewer can see how each value was obtained.

## Build order

1. Upload row lookup, hash, type and size checks (the viewer route already resolves the stored file safely).
2. Text-layer extraction and the `LoadedUpload` loader. Run the 603 starter files and compare with `reference/expected_results.json` where available.
3. Ownership check and quarantine.
4. OCR step with the threshold.
5. Vision step behind a setting, off by default, with the unverified handling.
6. Document rules and outcomes on the upload row, then the audit lines.
7. Re-run the same set and confirm cached reads cost nothing.

## Tests

- Text PDF gives verified quotes. A page with no text layer falls to OCR. An unreadable page is `REVIEW_REQUIRED` with no model call.
- A vision value is `UNVERIFIED` and the document is not `ACCEPTED`.
- A bundle with a foreign page never sends that page to the model and records the foreign page numbers.
- An exact duplicate is not read twice.
- An instruction inside a PDF is flagged and ignored.
- The model call is faked in every test, no network.

## Rotated scans

Without OCR the loader cannot detect the rotation of a scanned page itself. Text pages that are rotated are caught by the reversed label check. A rotated scan is caught only when the model reports the page as not legible, which makes the upload `NEEDS_HUMAN_REVIEW`. No prompt was changed for this.

## Open questions

- The text-length threshold and the OCR quality cutoff, to be set from the starter files.
- Whether vision stays off for the live demo or is shown as a labelled fallback.
- Whether native PDF input is worth a trial on the scanned and rotated starter files. If it is, it replaces step 3 only and keeps the unverified rule.
