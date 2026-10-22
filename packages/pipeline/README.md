# pipeline (`olist-pipeline`)

The analytics pipeline: dlt extracts from the Postgres OLTP (Neon) into BigQuery
bronze, and dbt builds silver + gold models with tests. It also ships the `elt`
runner that chains both stages.

```
Postgres (Neon)
   │ dlt incremental            dlt reconcile (bounded window, merge/upsert)
   v                                   v
BigQuery bronze_data  ◄────────  bronze_reconcile
   │
   └── dbt: stg (views) → int (views) → mart (tables) + snapshots
```

Deep dives: [`docs/dlt-pipeline.md`](../../docs/dlt-pipeline.md) and
[`docs/dbt-guide.md`](../../docs/dbt-guide.md).

## 1. Layout

| Path | Purpose |
|---|---|
| `src/pipeline/config.py` | pydantic settings: Postgres DSN, BigQuery, pipeline/dataset names |
| `src/pipeline/ingestion.py` | dlt pipeline (`ingest` entry point), `ALL_TABLES`, `PRIMARY_KEYS`, `--backfill`/`--since`/`--until` |
| `src/pipeline/run_elt.py` | `elt` entry point: dlt ingest → `dbt build` |
| `dbt/` | dbt project (models, macros, snapshots, generic tests) |
| `Dockerfile` | baked ELT job image (dlt + dbt, Cloud Run-shaped) |
| `docker-compose.yaml` | one-shot `elt` job with the SA key mounted |

## 2. Prerequisites

- `.env` at the repo root with `POSTGRES_DB__DSN` and the `BIGQUERY__*` keys
  (`PROJECT`, `LOCATION` = `us-central1`, `KEYFILE`). See `.env.example`.
- A seeded OLTP database (see [`packages/ecommerce_db`](../ecommerce_db/README.md)).
- dbt deps are installed through the `dbt-bigquery` dependency group.

## 3. Ingest (bronze)

```bash
make ingest                 # incremental: rows with updated_at > watermark → bronze_data
```

- Uses `updated_at` as the cursor and `range_start="open"`, so re-runs never
  re-read what was already loaded and the dlt state stays small.
- The watermark lives in dlt state (synced to BigQuery `_dlt_pipeline_state`).

### Reconciliation (recover skipped rows)

```bash
make ingest-backfill SINCE=2026-10-01T00:00:00
make ingest-backfill SINCE=2026-10-01T00:00:00 UNTIL=2026-10-21T12:00:00
```

- Separate pipeline + dataset (`ecommerce_pipeline_reconcile` → `bronze_reconcile`).
- Bounded window: `updated_at >= since AND updated_at <= until` (until defaults
  to now). The window is stateless; it never moves the incremental watermark.
- Loaded with BigQuery `merge`/`upsert` on the primary key, so re-running the
  same window is idempotent.
- Keep `SINCE` moving forward: upsert overwrites with the version just read.

## 4. ELT runner

```bash
make elt                     # dlt ingest → dbt build
uv run elt                   # same, explicit
uv run elt --ingest-only     # bronze only
uv run elt --dbt-only        # silver/gold/tests only
```

Exit code is propagated: a failed dlt job or dbt test stops the run. The Prefect
flow and the Dockerized job both shell out to this entry point. See
[`docs/elt-runner.md`](../../docs/elt-runner.md).

## 5. dbt

```bash
make dbt-parse    # validate YAML/syntax
make dbt-run      # build models
make dbt-test     # data tests (runs the snapshot first)
make dbt-build    # models + snapshot + tests
```

The project **must** run from `packages/pipeline/dbt/` (dbt 1.9+ has no
`--project-dir`); the Makefile handles the `cd`, the `dbt-bigquery` group, and
`--env-file`. Datasets are `stg` / `int` / `mart` / `snapshots`, mapped by the
`generate_schema_name` macro override. Staging unions `bronze_data` with
`bronze_reconcile` through `macros/olist_sources.sql` and keeps the newest row
per natural key (`updated_at` desc, `_dlt_load_id` desc).

## 6. Docker

```bash
make elt-build     # build the baked image
make elt-docker    # run the full ELT once
```

The compose file passes `POSTGRES_DB__DSN` + `BIGQUERY__*` from the root `.env`,
mounts the service-account key read-only at `/app/secrets/gcp-sa.json`, and
mounts `.env` so the dbt subprocess can read it. No warehouse volume: data and
dlt state live in BigQuery.
