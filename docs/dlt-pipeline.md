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
   │  normal run:   SELECT * FROM <table> WHERE updated_at > <watermark>
   │  reconcile:    SELECT * FROM <table> WHERE updated_at >= <since> AND updated_at <= <until>
   v
dlt extract → normalize → load
   │
   v
BigQuery
   ├── bronze_data       (append-only history, incremental)
   └── bronze_reconcile  (latest version per key, merged)
```

Two datasets, two jobs. The normal run appends to `bronze_data` and owns the
watermark. The reconciliation run re-reads a bounded window into
`bronze_reconcile` and never touches the watermark. The dbt staging layer
unions both and keeps the latest version of each row (see `docs/dbt-guide.md`).

## 2. How incremental loading works

Every table in Postgres has an `updated_at` column maintained by a trigger:
- `DEFAULT NOW()` stamps the insert time.
- `BEFORE UPDATE` triggers stamp every subsequent change.

dlt uses this column as a **cursor** (watermark). On each run:

1. dlt reads the last watermark from its pipeline state (stored in BigQuery in
   the `_dlt_pipeline_state` table of the dataset).
2. Extracts only rows past the watermark.
3. Loads the new rows into BigQuery (append-only).
4. Updates the watermark for the next run.

This means:
- **First run:** loads all rows (no previous watermark).
- **Second run onward:** only new/changed rows. Fast.
- **Status transitions** (e.g., shipped → delivered) appear as separate rows in bronze: the simulator fires an `UPDATE`, the `updated_at` trigger stamps a fresh timestamp, and dlt appends a new version of the row under the new watermark. This is correct for a bronze layer — it preserves historical truth. The silver layer (dbt) deduplicates (keeps the latest `updated_at` per natural key).

### The guarantees

| Guarantee | Mechanism |
|---|---|
| Incremental | `updated_at` cursor + `last_value` watermark |
| History-preserving (append-only) | dlt's dedup is only a *boundary-overlap* guard: rows with a newer cursor always pass through, so every status transition is appended. |
| No duplicates on re-runs | The normal run requests `updated_at > watermark` (strictly greater), so it never re-reads a row it already loaded. Nothing to dedup. |
| Small state (no oversized blob) | `range_start="open"` disables boundary dedup, so dlt stores no per-row hashes — only the watermark. |
| Idempotent reconciliation | The reconciliation run merges by primary key (`merge` + `upsert` on BigQuery) into a separate dataset, so re-running it updates rows instead of appending copies. |

> **What `primary_key` does and does not do.** dlt's `primary_key` only feeds
> the *boundary dedup* guard: when a run re-reads rows whose cursor equals the
> start value, dlt compares a hash of the key columns against the hashes the
> **previous** run stored, and drops the ones it has seen. It is not a global
> unique constraint:
>
> - Rows with a cursor **newer** than the start value are always appended, even
>   if their key was loaded before.
> - The guard only works if the previous run also stored boundary hashes. A run
>   with `range_start="open"` stores none, so a following `closed` run has
>   nothing to compare against and re-appends the whole boundary group.
>
> That combination is exactly how the dimension tables were duplicated once:
> an `open` run followed by a `closed` run re-read the seed timestamp group and
> appended a second copy of every row. The reconciliation design below avoids
> the situation instead of relying on the guard.

### Primary keys

Each resource gets a `primary_key` in its incremental hint (see
`PRIMARY_KEYS` in `ingestion.py`), mirroring the Postgres PKs in `schema.sql`:

| Table | Primary key |
|---|---|
| customers | `customer_id` |
| sellers | `seller_id` |
| products | `product_id` |
| geolocation | `geolocation_id` |
| product_category_name_translation | `product_category_name` |
| orders | `order_id` |
| order_items | `order_id, order_item_id` |
| order_payments | `order_id, payment_sequential` |
| reviews | `review_id, order_id` |

The reconciliation run also sets the same key as a **resource-level**
`primary_key` hint, because that is the hint dlt's `merge` strategy uses to
build the `MERGE` statement.

### The tie problem

`updated_at` is a coarse cursor. The seed loads every table in a single
transaction, and `NOW()` returns the *transaction* start time — so all
~1.3M seeded rows share one timestamp. The simulator's batches share another.

That has two consequences:

1. A watermark on `updated_at` can never separate "the row I already loaded"
   from "a row that arrived with the same timestamp".
2. Any dedup scheme that hashes boundary rows stores one hash per tied row —
   1,000,163 hashes for `geolocation` alone, which is what produced the
   `RESPONSE_TOO_LARGE` failure on the pipeline state.

The design below removes the problem instead of fighting it: the normal run
never re-reads what it loaded, and the reconciliation run merges by key in the
destination rather than relying on a cursor.

### `range_start="open"` for the normal run

`range_start` controls whether rows **equal** to the watermark are re-requested.
The normal run uses `"open"`: request `updated_at > watermark`. Rows exactly at
the watermark are excluded, so dlt can skip storing per-row dedup hashes
entirely → the pipeline state stays tiny.

The trade-off of `"open"`: a **new** row whose timestamp lands *exactly* on the
previous watermark is not re-requested and is silently skipped. That is what the
periodic reconciliation run exists to cover.

## 3. Reconciliation (periodic backfill)

To recover rows the `open` range skipped, run a **reconciliation**:

```bash
make ingest-backfill SINCE=2026-10-01T00:00:00                  # from the repo root
uv run --package olist-pipeline ingest --backfill --since 2026-10-01T00:00:00
```

- `--backfill` selects the reconciliation job: a different pipeline
  (`ecommerce_pipeline_reconcile`) writing to a different dataset
  (`bronze_reconcile`).
- `--since` is the ISO-8601 lower bound (required with `--backfill`).
- `--until` is the optional upper bound; it defaults to *now*. The window is
  therefore always bounded: `updated_at >= since AND updated_at <= until`.
- The window is **stateless**. Setting both `initial_value` and `end_value`
  makes dlt use a throwaway in-memory state, so the incremental watermark of
  `bronze_data` is never moved and no per-row hashes are stored.
- The load is a BigQuery `MERGE` on the primary key
  (`write_disposition={"disposition": "merge", "strategy": "upsert"}`), so a key
  appears at most once in `bronze_reconcile` with its most recent version.
  Re-running the same window updates rows instead of appending copies.
- `bronze_data` is not written at all by this job, so the incremental history
  and its watermark stay exactly as they were.

Typical usage: schedule a daily reconciliation with `SINCE` = *now minus a
safety window* (e.g. 24–48h). This recovers any boundary rows the `open` range
skipped, while the normal incremental runs stay fast and small.

> Keep `SINCE` moving forward. The `upsert` merge overwrites the reconciled row
> with the version it just read, so a reconciliation over an *older* window can
> move a reconciled row back to an older version.

The dbt staging models union `bronze_data` with `bronze_reconcile` and keep the
latest `updated_at` per natural key, so reconciled rows reach silver exactly
once. See `docs/dbt-guide.md`.

## 4. Files

| File | Purpose |
|---|---|
| `packages/pipeline/src/pipeline/ingestion.py` | The dlt pipeline (entry point: `ingest`) + `PRIMARY_KEYS` + `--backfill`/`--since`/`--until` CLI |
| `packages/pipeline/src/pipeline/config.py` | Settings via pydantic-settings (Postgres DSN, BigQuery project/location/keyfile, dataset names) — reads the root `.env` |
| `packages/pipeline/pyproject.toml` | Registers the `ingest` script + `dlt[bigquery,sql-database]` deps |

## 5. Credentials

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
   └── pipeline.reconcile_*     ← PIPELINE__RECONCILE_NAME / PIPELINE__RECONCILE_DATASET_NAME (optional)
```

BigQuery auth is a **service-account key file**: `ingestion.py` builds
`GcpServiceAccountCredentials`, parses the JSON via `parse_native_representation`,
and passes the credentials to `dlt.destinations.bigquery(...)`. The key JSON is
gitignored (`*-sa.json`).

There is **no `.dlt/` directory**: dlt keeps its state inside BigQuery (the
`_dlt_pipeline_state` table), so container runs stay incremental automatically
with no local volume.

## 6. Usage

```bash
make ingest                                            # from the repo root
uv run --package olist-pipeline ingest                 # same thing, explicit

# periodic reconciliation (see section 3)
make ingest-backfill SINCE=2026-10-01T00:00:00
make ingest-backfill SINCE=2026-10-01T00:00:00 UNTIL=2026-10-21T12:00:00
```

First run takes several minutes (~1.3M rows, especially geolocation). Subsequent runs are fast (only new/changed rows).

## 7. Key design decisions

| Decision | Why |
|---|---|
| SQLAlchemy engine (psycopg) | dlt's `sql_database` source accepts a SQLAlchemy engine; we build one from the Postgres DSN with `postgresql+psycopg`. |
| `updated_at` cursor | Change tracking without modifying the source. The Postgres triggers guarantee this column is always current. |
| Append-only bronze | Historical truth. Status transitions preserved as separate rows. Deduplication is silver's job. |
| `range_start="open"` for normal runs | The run never re-reads what it already loaded → no duplicates by construction, and no per-row boundary hashes → the state stays tiny and never hits `RESPONSE_TOO_LARGE`. |
| Separate pipeline + dataset for reconciliation | The reconciliation job needs a bounded, repeatable window and destination-side merging. Sharing the incremental pipeline would corrupt the watermark and re-append the boundary group. |
| `merge` + `upsert` for the reconciliation load | BigQuery merges on the primary key, so re-running a window is idempotent and the dataset holds one row per key. |
| `initial_value` + `end_value` for the window | dlt uses a mock state, so the incremental watermark is untouched and no hashes are stored. `initial_value` is honoured even when a state already exists — without `end_value` it would be ignored. |
| `ALL_TABLES` + `PRIMARY_KEYS` | Single source of truth for table list and keys. Adding a table means editing these maps, not the loop. |
| Service-account keyfile | Explicit, portable auth for local + Docker; the key path lives in `.env`, the key file itself is gitignored. |
| BigQuery state, no volume | dlt's watermark lives in BigQuery, so the ELT container needs no persistent disk. |

## 8. dlt warnings

You may see:

```
Large number of records (50000) sharing the same value of cursor field 'updated_at'
```

This is informational. The Olist dataset has many rows sharing one timestamp
(all historical orders seeded at once). With `range_start="open"`, dlt stores
no boundary hashes at all, so this warning no longer implies a state-size
problem. The earlier `RESPONSE_TOO_LARGE` failure came from a *closed* range
storing a hash per tied row; `open` for the normal run removed that.

## 9. Status & what's next

- **Incremental verified** (Phase 3): the watermark works for inserts and updates.
- **Reconciliation redesigned:** a separate pipeline + dataset, bounded window, merged by primary key. The incremental watermark is never touched by it.
- **dbt (Phase 4) done:** dbt reads `bronze_data.*` (and `bronze_reconcile.*` when present) from BigQuery, builds silver + gold models with tests.
- **Orchestration (Phase 5) done:** Prefect schedules `ingest → dbt build` (see `docs/orchestration.md`). A scheduled reconciliation flow is a documented follow-up, not yet wired.
- **Airbyte comparison (deferred):** build the same load with the Airbyte Python API, compare ergonomics, speed, features.

---

*Last updated: reconciliation moved to a separate pipeline + dataset with merge/upsert (2026-10)*
