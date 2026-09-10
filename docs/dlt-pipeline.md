# dlt Pipeline

ELT pipeline: extract from Postgres OLTP → load into DuckDB (bronze layer).

---

## 1. What it does

Loads all 9 Olist tables from the Postgres OLTP database into a local DuckDB warehouse. First run loads everything; subsequent runs only fetch rows that changed since the last load (incremental).

```
Postgres (OLTP)
   │
   │  SELECT * FROM <table> WHERE updated_at > <last watermark>
   v
dlt extract → normalize → load
   │
   v
DuckDB (data/warehouse/ecommerce.duckdb)
   └── ecommerce_data schema (customers, orders, order_items, ...)
```

## 2. How incremental loading works

Every table in Postgres has an `updated_at` column maintained by a trigger:
- `DEFAULT NOW()` stamps the insert time.
- `BEFORE UPDATE` triggers stamp every subsequent change.

dlt uses this column as a **cursor** (watermark). On each run:

1. dlt reads the last watermark from its pipeline state (stored in the `_dlt_pipeline_state` table of the DuckDB file).
2. Extracts only rows where `updated_at > <previous max>`.
3. Loads the new rows into DuckDB (append-only).
4. Updates the watermark for the next run.

This means:
- **First run:** loads all rows (no previous watermark).
- **Second run onward:** only new/changed rows. Fast.
- **Status transitions** (e.g., shipped → delivered) appear as separate rows in bronze: the simulator fires an `UPDATE`, the `updated_at` trigger stamps a fresh timestamp, and dlt appends a new version of the row under the new watermark. This is correct for a bronze layer — it preserves historical truth. The silver layer (dbt, Phase 4) deduplicates (keeps the latest `updated_at` per natural key).

### Why append-only?

A bronze layer should be a faithful copy of the source. If an order goes from `shipped` to `delivered`, both states should exist in bronze. Silver (dbt) applies business logic to pick the latest state.

## 3. Files

| File | Purpose |
|---|---|
| `pipeline/src/pipeline/ingestion.py` | The dlt pipeline (entry point: `ingest`) |
| `pipeline/src/pipeline/config.py` | Settings via pydantic-settings (Postgres DSN, warehouse path, dataset name) — reads the root `.env` |
| `pyproject.toml` | Registers the `ingest` script + dlt/deps |
| `data/warehouse/ecommerce.duckdb` | DuckDB warehouse file (gitignored, ~100MB; parent dir auto-created on first run) |

## 4. Credentials

No secrets are committed. Configuration lives in the root `.env` (gitignored) and is read by pydantic-settings:

```
.env (gitignored)
   │  pydantic-settings (env_file=".env", nested `__` keys)
   v
Settings (pipeline/config.py)
   │
   ├── postgres_db.dsn         ← POSTGRES_DB__DSN
   ├── warehouse_local.path    ← WAREHOUSE_LOCAL__PATH
   └── pipeline.name / dataset ← PIPELINE__NAME / PIPELINE__DATASET_NAME (optional)
```

There is **no `.dlt/` directory**: the DuckDB destination path is not a secret, and dlt keeps its state inside the warehouse file itself. Run `uv run ingest` from the repo root so `env_file=".env"` resolves (`*.env` paths are relative to the current directory).

## 5. Usage

```bash
make ingest      # from the project root (runs `uv run ingest`)
uv run ingest    # same thing, explicit
```

First run takes several minutes (~1.3M rows, especially geolocation). Subsequent runs are fast (only new/changed rows). The warehouse parent directory (`data/warehouse/`) is created automatically on the first run.

## 6. Key design decisions

| Decision | Why |
|---|---|
| SQLAlchemy engine (psycopg) | dlt's `sql_database` source accepts a SQLAlchemy engine; we build one from the Postgres DSN with `postgresql+psycopg`. |
| `updated_at` cursor | Change tracking without modifying the source. The Postgres triggers guarantee this column is always current. |
| Append-only bronze | Historical truth. Status transitions preserved as separate rows. Deduplication is silver's job. |
| `ALL_TABLES` list | Single source of truth. Adding a table means editing one list, not two. |
| Settings via pydantic-settings | The config model reads the root `.env` (`env_file=".env"`); nested `__` keys map to sub-models (`POSTGRES_DB__DSN`, `WAREHOUSE_LOCAL__PATH`). Run from the repo root so the relative `env_file` resolves. |
| DSN string → SQLAlchemy URL | Keep credentials as a connection string; `.set(drivername="postgresql+psycopg")` produces a standard SQLAlchemy URL for the source. |

## 7. dlt warnings

You'll see warnings like:

```
Large number of records (50000) sharing the same value of cursor field 'updated_at'
```

This is expected. The Olist dataset has many rows with the same timestamp (e.g., all historical orders seeded at once). dlt handles this correctly — it uses internal deduplication. The warning is informational, not an error.

## 8. Status & what's next

- **Incremental verified** (Phase 3): the watermark works for inserts and updates. To re-check: run `uv run ingest` twice and confirm bronze counts stabilize.
- **dbt (Phase 4) done:** dbt reads `ecommerce_data.*` from DuckDB, builds silver + gold models with tests.
- **Orchestration (Phase 5) done:** Prefect schedules `ingest → dbt build` (see `docs/orchestration.md`).
- **Airbyte comparison (deferred):** build the same load with the Airbyte Python API, compare ergonomics, speed, features.
- **BigQuery (Phase 7):** swap the DuckDB destination for BigQuery; creds move into Secret Manager.

---

*Last updated: Phase 3 (dlt) — refreshed for the `pipeline/` layout (2026-09)*
