# Targets for dockerized OLTP + local ELT/transforms.
# Usage: make <target>  (e.g. make db-shell, make dlt-pipeline, make dbt-build)

.PHONY: up down db-init db-shell simulator dlt-pipeline dbt dbt-debug dbt-parse dbt-run dbt-test dbt-build dbt-snapshot dbt-docs

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