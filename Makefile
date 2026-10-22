# Targets for the Neon-backed OLTP, BigQuery ELT, orchestration, and dashboard.
# Usage: make <target>   (e.g. make seed, make elt, make dashboard)
#
# Run all targets from the repo root.

.PHONY: help docker-build seed simulate simulate-logs simulate-once seed-local ingest ingest-backfill elt elt-build elt-docker dbt-debug dbt-parse dbt-run dbt-test dbt-build dbt-snapshot dbt-docs prefect-server prefect-flow prefect-serve prefect-pool prefect-deploy prefect-worker orc-up orc-down orc-logs orc-deploy orc-run dashboard lint format

# --- Dockerized OLTP (Neon-backed; see packages/ecommerce_db/README.md) ---
# --env-file .env lets Compose interpolate ${...} from the repo-root .env.
OLTP := -f packages/ecommerce_db/docker-compose.yaml --env-file .env

help:
	@grep -E '^[a-zA-Z_-]+:' $(MAKEFILE_LIST) | sort | awk -F: '{printf "  %-18s\n", $$1}'

# Build the seeder/simulator image (shared by both services).
docker-build:
	docker compose $(OLTP) build

# Seed Neon: one-shot job, with row-count verification.
seed:
	docker compose $(OLTP) run --rm seed

# Continuous simulator (compose default: 100 orders every 20s), detached.
simulate:
	docker compose $(OLTP) up -d simulate

# Follow the simulator logs.
simulate-logs:
	docker compose $(OLTP) logs -f simulate

# Run a single simulator batch locally (via uv), 50 orders.
simulate-once:
	uv run --package olist-ecommerce-database simulate --orders 50

# Seed locally (via uv) instead of Docker.
seed-local:
	uv run --package olist-ecommerce-database seed --verify

# --- ELT: dlt ingest -> dbt build (Neon -> BigQuery) ---
# Extract from Postgres -> load into BigQuery bronze.
ingest:
	uv run --package olist-pipeline ingest

# Periodic reconciler: re-read rows in [SINCE, UNTIL] into the separate
# bronze_reconcile dataset. Idempotent: merged by primary key, watermark untouched.
ingest-backfill:
	@test -n "$(SINCE)" || (echo "SINCE is required, e.g. make ingest-backfill SINCE=2026-10-01T00:00:00"; exit 1)
	uv run --package olist-pipeline ingest --backfill --since "$(SINCE)" $(if $(UNTIL),--until "$(UNTIL)",)

# Full ELT: dlt ingest -> dbt build (bronze/silver/gold + tests).
elt:
	uv run --package olist-pipeline elt

# --- Dockerized ELT runner (baked image; runs dlt -> dbt against Neon/BigQuery) ---
ELTFILE := -f packages/pipeline/docker-compose.yaml --env-file .env

elt-build:
	docker compose $(ELTFILE) build

elt-docker:
	docker compose $(ELTFILE) run --rm elt

# --- dbt (must run from the dbt project dir; dbt 1.9+ dropped --project-dir) ---
DBT := cd packages/pipeline/dbt && uv run --package olist-pipeline --group dbt-bigquery --env-file $(CURDIR)/.env dbt

dbt-debug:
	$(DBT) debug

dbt-parse:
	$(DBT) parse

dbt-run:
	$(DBT) run

dbt-test: dbt-snapshot
	$(DBT) test

dbt-build:
	$(DBT) build

dbt-snapshot:
	$(DBT) snapshot

dbt-docs:
	$(DBT) docs generate
	$(DBT) docs serve --port 8080

# --- Prefect orchestration (local server + work pool) ---
PREFECT := uv run --no-sync prefect
FLOWS := uv run --package olist-orchestration python -m orchestration.flows

prefect-server:
	$(PREFECT) server start --host 0.0.0.0

prefect-flow:
	$(FLOWS)

prefect-serve:
	$(FLOWS) --serve

prefect-pool:
	$(PREFECT) work-pool create --type process elt-pool

prefect-deploy:
	uv run --package olist-orchestration prefect deploy packages/orchestration/src/orchestration/flows.py:elt_flow --name elt-daily --pool elt-pool --cron "0 7 * * *" --concurrency-limit 1

prefect-worker:
	$(PREFECT) worker start --pool elt-pool

# --- Containerized orchestration (docker compose; server + worker) ---
ORC := -f packages/orchestration/docker-compose.yaml --env-file .env

orc-up:
	docker compose $(ORC) up -d --build

orc-down:
	docker compose $(ORC) down

orc-logs:
	docker compose $(ORC) logs -f prefect-worker

orc-deploy:
	docker compose $(ORC) run --rm --no-deps prefect-worker \
		uv run --no-sync prefect deploy /app/packages/orchestration/src/orchestration/flows.py:elt_flow \
		--name elt-daily --pool elt-pool --cron "0 7 * * *" --concurrency-limit 1

orc-run:
	docker compose $(ORC) run --rm --no-deps prefect-worker \
		uv run --no-sync prefect deployment run 'elt-daily'

# --- Dashboard (Streamlit; reads BigQuery gold) ---
dashboard:
	uv run --package olist-dashboard streamlit run packages/dashboard/src/dashboard/app.py

# --- Code quality ---
lint:
	uv run ruff check .

format:
	uv run ruff format .
