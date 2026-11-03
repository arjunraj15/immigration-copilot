# Docker notes

1. Services: `db` (Postgres with pgvector), `docling` (OCR and text), `migrate`, `backend`, `frontend`. Container names are `teamecho-backend-1` and so on.
2. `migrate` is a one-shot service built from the backend image. It runs `alembic upgrade head` and the backend waits for it to finish successfully. The backend image command also runs the migration before starting uvicorn with `--reload`. Migrations connect as the database owner through `MIGRATION_DATABASE_URL`. The app and the `migrate` service both get `DATABASE_URL` for the limited `casedesk_app` role.
3. The backend image is based on `python:3.12`, the full image and not slim, with only `curl` added. Dependencies come from `backend/requirements.txt`. `fastembed` is not installed.
4. `./backend` is bind mounted at `/app`, and `uvicorn --reload` picks up Python edits. Tests can be run with `docker exec` without a rebuild. A rebuild is only needed for dependency changes.
5. The frontend mounts `./frontend` and keeps `node_modules` in a volume.
6. The starter kit mount `${STARTER_KIT_DIR:-./data/starter-kit}` is read-only at `/data/starter-kit`. It is empty unless `STARTER_KIT_DIR` is set.
7. The `.env` file supplies `ANTHROPIC_API_KEY` and `AI_RUN_CAPTURE` through `env_file`. Do not commit it.
8. Check the VPN state before a rebuild, and do not rebuild images unless a dependency changed.
9. Migration order is `0001` pgvector, `0002` audit ledger and app role, `0003` starter kit tables, `0004` AI registry (`prompts`, `prompt_versions`, `prompt_runs`) and `0005` prompt enabled flag and soft delete. `0002` and `0003` belong to the core track. The AI migrations come after them.
