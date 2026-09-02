# Targets for dockerized OLTP + local ELT/transforms.
# Usage: make <target>  (e.g. make db-shell, make dlt-pipeline, make dbt-build)

.PHONY: up down db-init db-shell simulator dlt-pipeline dbt dbt-debug dbt-parse dbt-run dbt-test dbt-build dbt-snapshot dbt-docs prefect-server prefect-flow prefect-serve prefect-pool prefect-deploy prefect-worker

up:
	docker compose up -d

down:
	docker compose down

db-init:
	docker compose run --rm seed

db-shell:
	docker exec -it ecommerce_oltp psql \
		-U $$(sed -n 's/^POSTGRES_USER=//p' .env | tr -d '\r' | xargs) \
		-d $$(sed -n 's/^POSTGRES_DB=//p' .env | tr -d '\r' | xargs)

simulator:
	docker compose run --rm simulator

# Run the dlt ELT pipeline: extract from Postgres -> load into DuckDB (bronze).
dlt-pipeline:
	cd src/dlt_pipeline && uv run python dlt_pipeline.py

# --- dbt (must run from the dbt/ project dir; dbt 1.9+ no longer accepts --project-dir) ---
DBT := cd dbt && uv run dbt

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