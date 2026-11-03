.PHONY: up down build logs test lint seed seed-intake demo-reset migrate psql shell-backend reset-db

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

test:
	docker compose exec backend pytest -q

lint:
	docker compose exec backend ruff check app tests

seed:
	docker compose exec backend python -m app.cases.seed

demo-reset:
	bash scripts/demo-reset.sh

seed-intake:
	docker compose exec backend python -m app.cases.seed --intake-only

migrate:
	docker compose exec backend alembic upgrade head

psql:
	docker compose exec db psql -U casedesk -d casedesk

shell-backend:
	docker compose exec backend bash

reset-db:
	docker compose down -v
	docker compose up -d --build
