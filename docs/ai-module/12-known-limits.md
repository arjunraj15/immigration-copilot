# Known limits and open decisions

## Known limits

1. **Root list of records is not supported.** A prompt cannot return several records of the same type as its root. The root is one object with `fields`, and `read_document` returns one `DocumentRead` per category. Doing it cleanly needs a new schema root, a new contract field for the record index, and changes to routing, the test result and the editor. Use an array field for repeated rows inside one record. Use page level classification for different records on different pages.
2. **Array depth is one level.** An item cannot be an array or an object.
3. **`owner_names` is not consumed by Core yet.** Classify returns page level owner names, but `DocumentRead` does not carry them. Core has to read them from the classify result or the contract must grow a field.
4. **Uploads loader is missing.** `reader.default_deps()` uses `_no_loader`, which raises `NotImplementedError`. `POST /test` with `upload_id` returns `UPLOADS_UNAVAILABLE` (501). The Upload track must supply page text and sha256.
5. **Sample picker has no uploads endpoint.** The test panel calls `GET /api/uploads` and shows "No samples available" until that exists.
6. **Quote check in the browser works only for pasted text.** The server verdict (`verified`) always works.
7. **Embeddings are out of the image.** `fastembed` was removed from the slim image and is imported on first use, so the embeddings health test skips.
8. **Cache is per process memory.** It is lost on restart and not shared.
9. **Seed changes do not reach an existing database by themselves.** See the seed section in the lifecycle file.
10. **The array seed field is optional and the model often omits it** on documents that are not clearly a repeated list. It returns rows when the schema requires it.

## Open decisions

1. Final model and effort per prompt, once the allowed models for the key are known.
2. Whether prompt edits should require the LEGAL actor. Today any actor can edit.
3. The final `AI_RUN_CAPTURE` value.
4. Audit lines for prompt edits, once `audit.record` is available.
5. Whether to add a diff view and a YAML export.
