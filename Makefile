# Targets for dockerized OLTP + local ELT/transforms.
# Usage: make <target>  (e.g. make db-shell, make dlt-pipeline, make dbt-build)

.PHONY: up down db-init db-shell simulator ingest dbt dbt-debug dbt-parse dbt-run dbt-test dbt-build dbt-snapshot dbt-docs prefect-server prefect-flow prefect-serve prefect-pool prefect-deploy prefect-worker orc-up orc-down orc-logs orc-deploy orc-run dashboard

up:
	cd ecommerce_db && docker compose up -d

down:
	cd ecommerce_db && docker compose down

db-init:
	cd ecommerce_db && docker compose run --rm seed

db-shell:
	docker exec -it ecommerce_db psql -U postgres -d ecommerce

# Run simulator live: 10 orders, 10 seconds interval
simulator:
	cd ecommerce_db && docker compose run -d --no-deps --rm simulator uv run --no-sync simulate --orders 10 --continuous --interval 10

# Run the dlt ELT pipeline: extract from Postgres -> load into DuckDB (bronze).
# Runs from the repo root so pipeline.config reads the root .env.
ingest:
	uv run ingest

# --- dbt (must run from the dbt project dir; dbt 1.9+ no longer accepts --project-dir) ---
DBT := cd pipeline/dbt && uv run --group dbt-duckdb --env-file ../../.env dbt

# Verify the DuckDB connection and project config.
dbt-debug:
	$(DBT) debug

# Re-render project (catch YAML/syntax errors) without running models.
dbt-parse:
	$(DBT) parse

# Build all models: staging (view) -> intermediate (view) -> marts (table).
dbt-run:
	$(DBT) run

# Run all data tests (unique/not_null/relationships/custom) against built models.
dbt-test:
	$(DBT) test

# Full gate: run models + snapshot + tests in dependency order.
dbt-build:
	$(DBT) build

# Run SCD Type 2 snapshots only.
dbt-snapshot:
	$(DBT) snapshot

# Generate docs + lineage (writes to dbt/target/) and serve them locally.
dbt-docs:
	$(DBT) docs generate
	$(DBT) docs serve --port 8080

# --- Prefect orchestration (local server + work pool) ---
PREFECT := uv run --no-sync prefect

# Start the local Prefect server (its own terminal; accessible at localhost:4200).
prefect-server:
	$(PREFECT) server start --host 0.0.0.0

# Run the ELT flow once (manual trigger; appears in UI if server is up).
prefect-flow:
	uv run --group orchestration python orchestration/prefect/flows.py

# Serve the flow as the 'elt-daily' deployment (daily 07:00; its own terminal).
prefect-serve:
	uv run --group orchestration python orchestration/prefect/flows.py --serve

# Create the process work pool (one-time setup).
prefect-pool:
	$(PREFECT) work-pool create --type process elt-pool

# Deploy the flow to the work pool (registers deployment with server).
prefect-deploy:
	uv run --group orchestration prefect deploy orchestration/prefect/flows.py:elt_flow --name elt-daily --pool elt-pool --cron "0 7 * * *" --concurrency-limit 1

# Start a worker that pulls from the work pool (its own terminal).
prefect-worker:
	uv run --no-sync prefect worker start --pool elt-pool

# --- Containerized orchestration (docker compose; server + worker in containers) ---
# Requires the OLTP stack up (ecommerce_db service) for the shared network.
ORC := -f orchestration/docker-compose.yaml

# Build + start the containerized Prefect server and worker.
orc-up:
	docker compose $(ORC) up -d --build

# Stop the containerized Prefect stack (data volume is kept).
orc-down:
	docker compose $(ORC) down

# Tail the worker logs (elt_flow runs: dlt -> dbt).
orc-logs:
	docker compose $(ORC) logs -f prefect-worker

# Register the 'elt-daily' deployment (one-time; requires server up).
orc-deploy:
	docker compose $(ORC) run --rm --no-deps prefect-worker \
		uv run --no-sync prefect deploy /app/orchestration/prefect/flows.py:elt_flow \
		--name elt-daily --pool elt-pool --cron "0 7 * * *" --concurrency-limit 1

# Trigger one run of the 'elt-daily' deployment now (manual verification).
orc-run:
	docker compose $(ORC) run --rm --no-deps prefect-worker \
		uv run --no-sync prefect deployment run 'elt-daily'

# --- Dashboard (Streamlit) ---
# Reads the gold layer from the warehouse; backend chosen via DASHBOARD__SOURCE.
dashboard:
	uv run --group dashboard streamlit run dashboard/app.py