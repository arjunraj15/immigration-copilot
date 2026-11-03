# Frontend screens

Folder `frontend/src/features/ai-management/`. Route `/ai`, linked from the header AI menu. All calls go through `src/api/client.ts` with TanStack Query hooks in `hooks.ts`. Types in `types.ts` mirror `schemas.py`.

| Component | Screen |
|---|---|
| `AiManagementPage` | Layout, selection, enable or disable and delete controls |
| `PromptList` | Prompts grouped as Classify, Read and Other with category and active version |
| `PromptCreateForm` | Add a document type. Field definitions and schema are entered as JSON |
| `PromptEditor` | System text, template, model, effort, max tokens, field definitions, output schema, change note. Save makes a new version. Existing keys are read-only. "Use this draft in the test panel" sends an unsaved override |
| `ArrayItems` | Item sub-field rows for a field of type `array`, with locked item keys and a button that writes the schema entry |
| `VersionHistory` | All versions with Activate, also used for rollback |
| `TestPanel` | Paste text or pick a sample, optional override, then classification, fields with quote checks, raw JSON, source text, tokens and latency |

## Array editing

Choosing type `array` on a field row shows its item rows. At least one item with a key and a label is required before save. The button "Write schema entry for this array" inserts the correct `{value: [...]}` schema into the output schema JSON for that field. Existing item keys show as locked. Nesting is not offered.

## Test panel and quotes

Each scalar field shows a quote pill. An array field shows its rows. Each row has the server verdict ("Verified on page" or "Not verified, kept for review") and a browser check pill. The browser check works only on pasted text. For a sample upload the source text is read on the server, so the pill says to paste text.

Status is shown with a pill and a reason, never color alone, as `rules.md` section 5 requires.
