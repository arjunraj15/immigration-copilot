# Running the tests

Use the running backend container. Code is bind mounted, so no rebuild is needed.

## Offline tests

No network and no Claude calls. Database tests use a throwaway schema in the container Postgres.

```bash
docker exec teamecho-backend-1 sh -c 'cd /app && python -m pytest tests/ai -q'
```

Files in `backend/tests/ai/`: registry rules (`test_registry.py`, `test_array_registry.py`), reader and quote checks (`test_reader.py`), envelope, client with fake API objects, API routes, seed and YAML checks (`test_prompts_seed.py`), `fakes.py` with a fake model. The 18 live tests skip when `RUN_LIVE_AI` is not set.

## Live tests

They call the real API with the real seed prompts, in a throwaway schema, on text from the sample PDFs (pdfplumber text layer).

1. `RUN_LIVE_AI=1` enables them.
2. `SAMPLE_DOCS_DIR` is the folder that holds the `CASE-xxxx` folders. The compose file mounts the starter kit read-only at `/data/starter-kit` only when `STARTER_KIT_DIR` points at it. If that mount is empty, copy the folder in: `docker cp <path>/06_synthetic_documents/. teamecho-backend-1:/tmp/samples/` and use `SAMPLE_DOCS_DIR=/tmp/samples`.
3. The key comes from `ANTHROPIC_API_KEY`. The container already has it from `.env`. Pass it with `-e` at exec time if it is missing. Never print it.

```bash
docker exec -e RUN_LIVE_AI=1 -e SAMPLE_DOCS_DIR=/tmp/samples teamecho-backend-1 \
  sh -c 'cd /app && python -m pytest tests/ai/test_live_prompts.py -q'
```

A full live run takes about 90 seconds and spends a few tens of thousands of tokens.

## Other checks

1. Complexity: keep each function at 15 or less. `ruff` is not in the image, so use a local ruff with `--select C901` or count branches by hand.
2. Frontend types: `docker exec teamecho-frontend-1 sh -c 'cd /app && npx tsc --noEmit -p .'`. One old error about `process` in `vite.config.ts` is unrelated.
3. The whole backend suite is `python -m pytest -q` inside `/app`.
