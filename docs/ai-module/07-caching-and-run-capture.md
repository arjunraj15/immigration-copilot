# Caching and run capture

## Cache

1. The cache key is the file sha256, the prompt key, the version number and the page numbers sent.
2. Only results with status `ok` are cached. Failures and refusals are retried next time.
3. A new active version has a new number, so a prompt change invalidates earlier results without any extra step.
4. The default cache is a module-level dict inside the process. It is lost on restart. It is not shared between workers.
5. The test dry run uses a throwaway cache, so a test never fills the real one. The test panel also never changes saved state. It only writes `prompt_runs` rows.
6. The test panel text input uses the sha `test`. An override uses version 0.

## Run history

Each Claude call writes one `prompt_runs` row: prompt key, version, model, optional case id, input hash, tokens in and out, latency, stop reason and status. `GET /api/ai/runs` can filter by `prompt_key` and `case_id`. Status is `ok`, `needs_review` or `error`.

## Capture modes

Setting `AI_RUN_CAPTURE`, read through `core/config.py`.

| Value | Stored |
|---|---|
| `full` (default) | Also the rendered prompt, the document text sent and the raw output |
| `hashes` | Only metadata and the input hash, no content |

Changing it needs an environment change and a backend restart, not a code change. The plan says to decide the final value by hour 18. Use `hashes` for real client data.

## Call rules

Structured outputs with `output_config.format` json_schema and an explicit `effort`. No tools, no forced tool choice, no prefill, no `temperature`, `top_p` or `top_k`. `stop_reason` is checked before content is parsed. `refusal` and `max_tokens` become `needs_review`. Transient errors (connection, rate limit, server) retry three times with backoff. Models and effort come from the version row. Classify uses `claude-haiku-5-5` and the reads use `claude-sonnet-5-5`.
