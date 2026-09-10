# dbt Project

Transformations: bronze (dlt-loaded) → silver (staging) → intermediate → gold (marts), plus SCD Type 2 snapshots. Owns silver + gold and the test suite.

---

## 1. What it does

dbt reads the raw `ecommerce_data` schema in DuckDB (loaded by dlt) and builds a layered analytics model:

```
DuckDB (data/warehouse/ecommerce.duckdb)
│
├── ecommerce_data   bronze — dlt raw tables (customers, orders, ...)
│
│   dbt sources (read-only)
│
├── main_stg         silver — staging views, cleaned + deduplicated (9 models)
├── main_int         intermediate — enriched/aggregated views (4 models)
├── main_mart        gold — star schema tables (dim_* + fct_*)  (5 models)
└── main_snapshots   SCD Type 2 history of orders (1 snapshot)
```

Running `uv run dbt run` (from `pipeline/dbt/`) builds all models in dependency order. Running `dbt build` runs models **and** their data tests, plus the snapshot.

## 2. Layers

### Staging (`models/staging/`, materialized as views)

One model per source table, `stg_olist__<table>`. Job: **clean and deduplicate only** — no business logic, no joins across tables.

- Standard 3-CTE pattern: `source → transform → select`.
- Deduplication via `row_number() over (partition by <natural key> order by updated_at desc)`; keep `rn = 1`.
- Composite keys used where a single column isn't unique:
  - `order_items` → `(order_id, order_item_id)`
  - `order_payments` → `(order_id, payment_sequential)`
  - `reviews` → `(order_id, review_id)`
- Renames kept in source, fixed here: `product_name_lenght` → `product_name_length`, `product_description_lenght` → `product_description_length`.
- A synthetic `geolocation_id` key is added because the source `geolocation` table has none.

**Why views:** staging is recomputed every run from upstream raw data. A view is just saved SQL, so it always reflects the latest raw state with zero storage cost. Recomputing a view is cheap.

### Intermediate (`models/intermediate/`, materialized as views)

Enrichment and aggregation — one job per model, narrowly scoped, no duplicate of staging logic:

| Model | Job |
|---|---|
| `int_orders_enriched` | orders joined to customers + derived timing metrics (`delivery_days`, `approval_hours`) |
| `int_order_items_enriched` | items joined to products, sellers, and the category translation (with `coalesce` fallback for unmatched categories) |
| `int_order_items_aggregated` | items rolled up per order → `item_count`, `order_total_value`, freight totals |
| `int_geolocation_aggregated` | the 1M+ raw geolocation rows rolled up to city/state with average coordinates |

**Why this layer exists:** keeps each intermediate doing one focused job. Gold composes them instead of re-joining raw tables. Narrow, composable models are easier to test, debug, and reuse.

### Marts (`models/marts/`, materialized as tables)

The star schema. `dim_*` are the things you slice by (who/what), `fct_*` are the events you measure.

| Model | Notes |
|---|---|
| `dim_customers` | one row per **real** customer (`customer_unique_id`) — `customer_id` is per-order, so this collapses to unique customers |
| `dim_products` | product with English category available via translation |
| `dim_sellers` | seller attributes |
| `fct_orders` | one row per order, composes `int_orders_enriched` + `int_order_items_aggregated`, `coalesce(..., 0)` so money/counts are never NULL |
| `fct_order_payments` | one row per payment line |

**Why tables:** marts are the final BI-facing outputs, queried repeatedly. A table stores the computed result so every dashboard query doesn't recompute the whole pipeline.

**Why `coalesce` in `fct_orders`:** a `LEFT JOIN` to the order-totals model means orders with no items get NULL totals. Coalescing to `0` makes the fact table clean.

## 3. Schema-per-layer (`main_*`)

Configured in `dbt_project.yml` via `+schema`:

```yaml
staging:      { +materialized: view,  +schema: stg }
intermediate: { +materialized: view,  +schema: int }
marts:        { +materialized: table, +schema: mart }
snapshots:    target_schema: main_snapshots
```

The resulting schemas are `main_stg`, `main_int`, `main_mart`, `main_snapshots`.

**The `main_` prefix is a DuckDB adapter quirk:** dbt *appends* `+schema` to the profile's default schema (`main`) rather than replacing it. So `+schema: stg` yields `main_stg`, not `stg`. This is DuckDB-specific behavior — on BigQuery (Phase 7), `+schema` maps to a dataset name directly. Knowing this now avoids confusion later.

Clean separation: raw (`ecommerce_data`) is kept untouched; `main` itself is left empty of dbt objects.

## 4. Materialization & rebuild semantics

dbt is **declarative**: the model SQL describes the desired end state, and `dbt run` makes reality match it on every run.

- **Views** are recreated each run (drop + recreate). Cheap.
- **Tables** are fully rebuilt each run (drop + recreate from current SQL). At ~100k orders this takes seconds.
- dbt does **not** incrementally merge by default. The `materialized='incremental'` strategy is available, but the DuckDB adapter implements it as a full table swap (no native `MERGE`), and full rebuilds are fast at this scale — so we skip incremental here. It becomes valuable on BigQuery (Phase 7).

**Orphan cleanup gotcha:** if you move/rename a model or change its schema, `dbt run` creates the new object but does **not** drop the old one. You clean up old objects yourself. (This happened in Step 8 when moving views from `main` to `main_stg` — the 13 orphan views in `main` were dropped manually.)

## 5. Snapshots (SCD Type 2)

`snapshots/orders_snapshot.sql` tracks the full history of order status changes:

```sql
{% snapshot orders_snapshot %}
{{
    config(
        target_schema='main_snapshots',
        unique_key='order_id',
        strategy='timestamp',
        updated_at='updated_at',
    )
}}
select * from {{ ref('stg_olist__orders') }}
{% endsnapshot %}
```

- `strategy='timestamp'`: a new version is created whenever `updated_at` changes.
- `unique_key='order_id'`: one logical order tracked over time.
- On each run, dbt **closes** the previous version (`dbt_valid_to = now()`) and **inserts** a new one (`dbt_valid_from = now()`, `dbt_valid_to = NULL`).

This works hand-in-hand with the append-only bronze: status transitions shipped → delivered arrive as new rows with a fresh watermark, so the snapshot reconstructs the full timeline. First run inserts all rows as "open"; the history accumulates on subsequent runs as the simulator changes order statuses.

Result columns the snapshot adds: `dbt_scd_id`, `dbt_updated_at`, `dbt_valid_from`, `dbt_valid_to`.

## 6. Tests

Data tests guard the layers (73 in total). Built-in tests used: `unique`, `not_null`, `accepted_values`, `relationships`. Plus one custom generic test: `assert_non_negative` (`tests/generic/`), which fails any row where a column is negative — used on money/count columns.

- `staging`: 29 tests — PK (`unique` + `not_null`), FK integrity (`relationships` to sources), value whitelists (`accepted_values`), and `not_null` on required columns. Review `accepted_values` uses a `where:` config to skip NULLs.
- `intermediate`: uniqueness on composite keys, `not_null` on keys, `accepted_values` on `order_status`, and `assert_non_negative` on money/counts.
- `marts`: PKs on `dim_*`, plus `fct_orders` FK → `dim_customers` and `fct_order_payments` FK → `fct_orders` (referential integrity in gold).
- `snapshots`: `not_null` on `order_id`, `order_status`, `dbt_valid_from`.

Test placement matches dbt convention: a `_<layer>__models.yml` co-located in each model folder.

## 7. Usage

The dbt project lives at `pipeline/dbt/` (it must be run from there — dbt 1.9+ has no `--project-dir`). The Makefile wraps all of this for you, so from the project root you can use `make dbt-*` directly:

```bash
cd pipeline/dbt
uv run --group dbt-duckdb --env-file ../../.env dbt debug    # verify connection & config
uv run --group dbt-duckdb --env-file ../../.env dbt run      # build all models (views + tables)
uv run --group dbt-duckdb --env-file ../../.env dbt test     # run all data tests
uv run --group dbt-duckdb --env-file ../../.env dbt build    # run + snapshot + test, in dependency order
uv run --group dbt-duckdb --env-file ../../.env dbt snapshot # run snapshots only
uv run --group dbt-duckdb --env-file ../../.env dbt docs ... # lineage docs
```

From the project root, `make dbt-build` runs the full gate (models + snapshot + tests) with the same flags. The `--env-file ../../.env` makes the `WAREHOUSE_LOCAL__PATH` (and future cloud creds) available to `profiles.yml`; `--group dbt-duckdb` guarantees the adapter is installed.

## 8. Key design decisions

| Decision | Why |
|---|---|
| DuckDB file is the database | Zero-ops single-node warehouse to iterate fast; swap the profile for BigQuery at Phase 7 |
| Staging = views, marts = tables | Staging is recomputed every run (cheap, always fresh); marts are stored for fast BI reads |
| Schema per layer (`main_stg`, etc.) | Layered architecture is visible at the database level; keeps `ecommerce_data` raw untouched |
| 3-CTE staging pattern | Uniform, readable, testable — same shape in every staging model |
| Dedup in staging with `row_number()` | Bronze appends history; silver picks the latest version per natural key |
| Enrichment split into focused intermediates | One job per model, composable in gold, easy to test and reuse |
| `fct_orders` composes two intermediates via `ref()` | The DAG expresses real reuse instead of copy-pasted joins |
| `dbt_utils` skipped | Keep dependencies minimal; only built-in tests + one tiny custom test |
| Snapshots on orders | Demonstrates SCD Type 2 against the simulator's status changes |

## 9. What's next

- **Prefect orchestration (Phase 5):** schedule dlt + dbt (`dbt build`) + later the report; respect DuckDB's single-writer rule (don't run dlt and dbt concurrently).
- **Airbyte (Phase 3 deferred):** build the ingestion comparison pipeline.
- **BigQuery (Phase 7):** swap the profile; incremental materialization becomes valuable at scale.

---

*Last updated: Phase 4 (dbt) — refreshed for the `pipeline/dbt/` layout (2026-09)*