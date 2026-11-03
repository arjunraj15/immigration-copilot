# API routes and error codes

All under `/api/ai`. The frontend client prefixes `/api`. Errors have the body `{"error": {"code": "...", "message": "..."}}`. Request body shape errors from validation use the framework default 422 body.

| Route | Purpose |
|---|---|
| `GET /prompts` | Grouped by step (`classify`, `read`, `other`). `include_deleted=true` shows deleted |
| `POST /prompts` | Create a read prompt (a new document type) with its first version, already active |
| `GET /prompts/{key}` | Summary, active version, field definitions, last run |
| `GET /prompts/{key}/versions` | History, newest first |
| `POST /prompts/{key}/versions` | Save a new version, not active yet |
| `POST /prompts/{key}/activate` | Body `{"version": n}`. Activate or roll back |
| `POST /prompts/{key}/disable` and `/enable` | Toggle routing |
| `DELETE /prompts/{key}` | Soft delete, returns 204 |
| `POST /prompts/{key}/restore` | Undo a delete |
| `POST /test` | Dry run on pasted `text` or an `upload_id`, with optional `prompt_key` and `override` version |
| `GET /runs` | Run history, filter `prompt_key`, `limit` 1 to 200 |

The `X-Actor` header is stored as `created_by` on new versions. It is a demo control, not authentication.

## Error codes

| Code | Status | When |
|---|---|---|
| `PROMPT_NOT_FOUND` | 404 | Unknown or deleted key |
| `PROMPT_EXISTS` | 409 | Create with a key that exists |
| `PROMPT_DELETED` | 409 | Create with a deleted key. Restore instead |
| `DOCUMENT_TYPE_ONLY` | 422 | Create with a step other than read |
| `CATEGORY_REQUIRED` | 422 | Read prompt without a category |
| `CATEGORY_RESERVED` | 422 | Category `UNKNOWN` |
| `KEY_CATEGORY_MISMATCH` | 422 | Key is not `doc.read.<category lowercase>` |
| `INVALID_PROMPT_VERSION` | 422 | Registry check failed (definitions, schema, arrays) |
| `KEY_LOCKED` | 409 | New version drops or renames a locked key |
| `PROMPT_PROTECTED` | 409 | Disable or delete of classify or generic |
| `VERSION_NOT_FOUND` | 404 | Activate with an unknown number |
| `TEST_INPUT_REQUIRED` | 422 | Test without text or upload_id |
| `UPLOADS_UNAVAILABLE` | 501 | Test with `upload_id` while no uploads loader exists |

The test result is `category`, `language`, `legible`, `injection_flag`, `fields` and `prompt_run_ids`. `fields` is a flat list of `{key, value, quote, page, verified, items}`. Array fields carry `items`.
