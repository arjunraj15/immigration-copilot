# Prompt lifecycle

## Versions

1. A prompt has many versions. A version holds system text, user template, model, effort, max tokens, output schema, field definitions, note and creator.
2. Versions are insert-only. A change is always a new row with the next number. Nothing is edited or deleted.
3. Saving a version does not activate it. The prompt keeps pointing at `active_version_id`.

## Activate and rollback

`POST /api/ai/prompts/{key}/activate` with a version number. It works forward and backward, so a rollback is just activating an older version. An unknown number returns `VERSION_NOT_FOUND`. A changed active version changes the cache key, so old cached results are not reused.

## Key lock

A new version must keep every field key of the active version, and every array item key. Removing or renaming one returns `KEY_LOCKED` (409). Adding keys is allowed. The editor shows existing keys as read-only. The reason is that downstream code and the form field map depend on the keys.

## Registry checks on every save

Valid field definitions, an output schema that requires `quote` and `page` on every value, schema keys equal to definition keys, and render variables that exist. Failures return `INVALID_PROMPT_VERSION` (422).

## Disable, delete, restore

1. Disable (`POST .../disable`) keeps the prompt but removes it from the category list and from routing. Reads of that category fall back to the generic prompt. Enable reverses it.
2. Delete is soft. It sets `deleted_at`. Versions and runs stay. The key cannot be reused and creation returns `PROMPT_DELETED`. Restore brings it back.
3. Protected prompts, `doc.classify` and `doc.read.generic`, cannot be disabled or deleted (`PROMPT_PROTECTED`). The reader needs both.

## Adding a document type

Only read prompts can be added. Rules:

1. `step` must be `read` (`DOCUMENT_TYPE_ONLY`).
2. `category` is required, uppercase, and not `UNKNOWN`.
3. The key must be `doc.read.<category lowercase>` (`KEY_CATEGORY_MISMATCH`).
4. There is one classify prompt. It is edited, never duplicated.

## Seeds

At startup `seed_prompts` inserts a YAML prompt only when its key is missing from the database. It never overwrites an edit. Changing a YAML file for an existing key does nothing by itself. To apply a changed seed, add a new version only when the active version was created by `seed`, and never when a person edited it. A small script doing this is `sync_seeds.py` in the session scratchpad, and it follows the same rule: compare the active row with the YAML, skip if `created_by` is not `seed`, otherwise call `registry.create_version` and point the prompt at it.
