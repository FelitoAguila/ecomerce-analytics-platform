# dlt Pipeline

ELT pipeline: extract from Postgres OLTP → load into BigQuery (bronze layer).

---

## 1. What it does

Loads all 9 Olist tables from the Postgres OLTP database (Neon) into the
`bronze_data` dataset in BigQuery. First run loads everything; subsequent runs
only fetch rows that changed since the last load (incremental).

```
Postgres (Neon OLTP)
   │
   │  SELECT * FROM <table> WHERE updated_at > <last watermark>
   v
dlt extract → normalize → load
   │
   v
BigQuery
   └── bronze_data dataset (customers, orders, order_items, ...)
```

## 2. How incremental loading works

Every table in Postgres has an `updated_at` column maintained by a trigger:
- `DEFAULT NOW()` stamps the insert time.
- `BEFORE UPDATE` triggers stamp every subsequent change.

dlt uses this column as a **cursor** (watermark). On each run:

1. dlt reads the last watermark from its pipeline state (stored in BigQuery in
   the `_dlt_pipeline_state` table of the dataset).
2. Extracts only rows where `updated_at > <previous max>`.
3. Loads the new rows into BigQuery (append-only).
4. Updates the watermark for the next run.

This means:
- **First run:** loads all rows (no previous watermark).
- **Second run onward:** only new/changed rows. Fast.
- **Status transitions** (e.g., shipped → delivered) appear as separate rows in bronze: the simulator fires an `UPDATE`, the `updated_at` trigger stamps a fresh timestamp, and dlt appends a new version of the row under the new watermark. This is correct for a bronze layer — it preserves historical truth. The silver layer (dbt) deduplicates (keeps the latest `updated_at` per natural key).

### Why append-only?

A bronze layer should be a faithful copy of the source. If an order goes from `shipped` to `delivered`, both states should exist in bronze. Silver (dbt) applies business logic to pick the latest state.

## 3. Files

| File | Purpose |
|---|---|
| `packages/pipeline/src/pipeline/ingestion.py` | The dlt pipeline (entry point: `ingest`) |
| `packages/pipeline/src/pipeline/config.py` | Settings via pydantic-settings (Postgres DSN, BigQuery project/location/keyfile, dataset name) — reads the root `.env` |
| `packages/pipeline/pyproject.toml` | Registers the `ingest` script + `dlt[bigquery,sql-database]` deps |

## 4. Credentials

No secrets are committed. Configuration lives in the root `.env` (gitignored)
and is read by pydantic-settings:

```
.env (gitignored)
   │  pydantic-settings (env_file=<workspace>/.env, nested `__` keys)
   v
Settings (packages/pipeline/src/pipeline/config.py)
   │
   ├── postgres_db.dsn          ← POSTGRES_DB__DSN
   ├── bigquery.project         ← BIGQUERY__PROJECT
   ├── bigquery.location        ← BIGQUERY__LOCATION (default US)
   ├── bigquery.keyfile         ← BIGQUERY__KEYFILE (path to SA JSON)
   └── pipeline.name / dataset  ← PIPELINE__NAME / PIPELINE__DATASET_NAME (optional)
```

BigQuery auth is a **service-account key file**: dlt loads it via
`google.oauth2.service_account.Credentials.from_service_account_file(...)` and
passes the credentials to `dlt.destinations.bigquery(...)`. The key JSON is
gitignored (`*-sa.json`).

There is **no `.dlt/` directory**: dlt keeps its state inside BigQuery (the
`_dlt_pipeline_state` table), so container runs stay incremental automatically
with no local volume.

## 5. Usage

```bash
make ingest                                            # from the repo root
uv run --package olist-pipeline ingest                 # same thing, explicit
```

First run takes several minutes (~1.3M rows, especially geolocation). Subsequent runs are fast (only new/changed rows).

## 6. Key design decisions

| Decision | Why |
|---|---|
| SQLAlchemy engine (psycopg) | dlt's `sql_database` source accepts a SQLAlchemy engine; we build one from the Postgres DSN with `postgresql+psycopg`. |
| `updated_at` cursor | Change tracking without modifying the source. The Postgres triggers guarantee this column is always current. |
| Append-only bronze | Historical truth. Status transitions preserved as separate rows. Deduplication is silver's job. |
| `ALL_TABLES` list | Single source of truth. Adding a table means editing one list, not two. |
| Service-account keyfile | Explicit, portable auth for local + Docker; the key path lives in `.env`, the key file itself is gitignored. |
| BigQuery state, no volume | dlt's watermark lives in BigQuery, so the ELT container needs no persistent disk. |

## 7. dlt warnings

You'll see warnings like:

```
Large number of records (50000) sharing the same value of cursor field 'updated_at'
```

This is expected. The Olist dataset has many rows with the same timestamp (e.g., all historical orders seeded at once). dlt handles this correctly — it uses internal deduplication. The warning is informational, not an error.

## 8. Status & what's next

- **Incremental verified** (Phase 3): the watermark works for inserts and updates.
- **dbt (Phase 4) done:** dbt reads `bronze_data.*` from BigQuery, builds silver + gold models with tests.
- **Orchestration (Phase 5) done:** Prefect schedules `ingest → dbt build` (see `docs/orchestration.md`).
- **Airbyte comparison (deferred):** build the same load with the Airbyte Python API, compare ergonomics, speed, features.

---

*Last updated: BigQuery migration — dlt loads straight into `bronze_data` in BigQuery (2026-10)*
