# dbt Project

Transformations: bronze (dlt-loaded) → silver (staging) → intermediate → gold (marts), plus SCD Type 2 snapshots. Owns silver + gold and the test suite.

---

## 1. What it does

dbt reads the raw `bronze_data` dataset in BigQuery (loaded by dlt) and builds a
layered analytics model:

```
BigQuery (<project>)
│
├── bronze_data   bronze — dlt raw tables (customers, orders, ...)
│
│   dbt sources (read-only)
│
├── stg           silver — staging views, cleaned + deduplicated (9 models)
├── int           intermediate — enriched/aggregated views (4 models)
├── mart          gold — star schema tables (dim_* + fct_*)  (5 models)
└── snapshots     SCD Type 2 history of orders (1 snapshot)
```

Running `uv run dbt run` (from `packages/pipeline/dbt/`) builds all models in dependency order. Running `dbt build` runs models **and** their data tests, plus the snapshot.

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

## 3. Schema-per-layer (datasets)

Configured in `dbt_project.yml` via `+schema`:

```yaml
staging:      { +materialized: view,  +schema: stg }
intermediate: { +materialized: view,  +schema: int }
marts:        { +materialized: table, +schema: mart }
snapshots:    target_schema: snapshots
```

On BigQuery, `+schema` maps **directly** to a **dataset**: `stg`, `int`, `mart`,
`snapshots`. (On the earlier DuckDB warehouse the adapter *appended* `+schema` to
the profile's default schema, producing a `main_` prefix — that quirk is gone
now.)

Clean separation: raw (`bronze_data`) is kept untouched; dbt never writes there.

## 4. Materialization & rebuild semantics

dbt is **declarative**: the model SQL describes the desired end state, and `dbt run` makes reality match it on every run.

- **Views** are recreated each run (create or replace). Cheap.
- **Tables** are fully rebuilt each run (create or replace from current SQL). At ~100k orders this takes seconds.
- dbt does **not** incrementally merge by default. The `materialized='incremental'` strategy is available on BigQuery (native `MERGE`), and becomes valuable at larger scale — but at this size full rebuilds keep the models simple and the tests fully deterministic.

**Orphan cleanup gotcha:** if you move/rename a model or change its dataset, `dbt run` creates the new object but does **not** drop the old one. You clean up old objects yourself.

## 5. Snapshots (SCD Type 2)

`snapshots/orders_snapshot.sql` tracks the full history of order status changes:

```sql
{% snapshot orders_snapshot %}
{{
    config(
        target_schema='snapshots',
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

The dbt project lives at `packages/pipeline/dbt/` (it must be run from there — dbt 1.9+ has no `--project-dir`). The Makefile wraps all of this for you, so from the project root you can use `make dbt-*` directly:

```bash
cd packages/pipeline/dbt
uv run --package olist-pipeline --group dbt-bigquery --env-file ../../../.env dbt debug    # verify connection & config
uv run --package olist-pipeline --group dbt-bigquery --env-file ../../../.env dbt run      # build all models (views + tables)
uv run --package olist-pipeline --group dbt-bigquery --env-file ../../../.env dbt test     # run all data tests
uv run --package olist-pipeline --group dbt-bigquery --env-file ../../../.env dbt build    # run + snapshot + test, in dependency order
uv run --package olist-pipeline --group dbt-bigquery --env-file ../../../.env dbt snapshot # run snapshots only
uv run --package olist-pipeline --group dbt-bigquery --env-file ../../../.env dbt docs ... # lineage docs
```

From the project root, `make dbt-build` runs the full gate (models + snapshot + tests) with the same flags. The `--env-file ../../../.env` makes `BIGQUERY__PROJECT`/`BIGQUERY__LOCATION`/`BIGQUERY__KEYFILE` available to `profiles.yml`; `--group dbt-bigquery` guarantees the adapter is installed.

## 8. Key design decisions

| Decision | Why |
|---|---|
| BigQuery is the warehouse | Cloud DW from day one; the DuckDB iteration warehouse has been removed |
| Staging = views, marts = tables | Staging is recomputed every run (cheap, always fresh); marts are stored for fast BI reads |
| Dataset per layer (`stg`, `int`, `mart`, `snapshots`) | Layered architecture is visible at the warehouse level; keeps `bronze_data` raw untouched |
| 3-CTE staging pattern | Uniform, readable, testable — same shape in every staging model |
| Dedup in staging with `row_number()` | Bronze appends history; silver picks the latest version per natural key |
| Enrichment split into focused intermediates | One job per model, composable in gold, easy to test and reuse |
| `fct_orders` composes two intermediates via `ref()` | The DAG expresses real reuse instead of copy-pasted joins |
| `dbt_utils` skipped | Keep dependencies minimal; only built-in tests + one tiny custom test |
| Snapshots on orders | Demonstrates SCD Type 2 against the simulator's status changes |

## 9. What's next

- **Prefect orchestration (Phase 5):** schedule dlt + dbt (`dbt build`) + later the report.
- **Airbyte (Phase 3 deferred):** build the ingestion comparison pipeline.
- **Cloud (Phase 7):** Secret Manager for the SA key, Workload Identity on Cloud Run.

---

*Last updated: BigQuery migration — dbt targets BigQuery datasets `stg`/`int`/`mart`/`snapshots` (2026-10)*