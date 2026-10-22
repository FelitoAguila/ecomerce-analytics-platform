# dbt Project

Transformations: bronze (dlt-loaded) → silver (staging) → intermediate → gold (marts), plus SCD Type 2 snapshots. Owns silver + gold and the test suite.

---

## 1. What it does

dbt reads the raw `bronze_data` dataset in BigQuery (loaded by dlt) and builds a
layered analytics model:

```
BigQuery (<project>)
│
├── bronze_data         bronze — dlt raw tables (customers, orders, ...)
├── bronze_reconcile    bronze — dlt reconciliation tables (latest version per key)
│
│   dbt sources (read-only)
│
├── stg           silver — staging views, cleaned + deduplicated (9 models)
├── int           intermediate — enriched/aggregated views (4 models)
├── mart          gold — star schema tables (dim_* + fct_*)  (5 models)
└── snapshots     SCD Type 2 history of orders (1 snapshot)
```

Running `uv run dbt run` (from `packages/pipeline/dbt/`) builds all models in dependency order. Running `dbt build` runs models **and** their data tests, plus the snapshot.

Two bronze sources are declared in `models/sources.yml`:

| Source | Dataset | Written by |
|---|---|---|
| `ecommerce_data` | `bronze_data` | the dlt incremental run (append-only history) |
| `ecommerce_data_reconcile` | `bronze_reconcile` | the dlt reconciliation run (merged by primary key) |

`bronze_reconcile` only exists after the first `make ingest-backfill`. The
staging models work either way — see section 2.

## 2. Layers

### Staging (`models/staging/`, materialized as views)

One model per source table, `stg_olist__<table>`. Job: **clean and deduplicate only** — no business logic, no joins across tables.

- Standard two-CTE pattern, then the final `select`: `source → deduplicated → select`.
- The `source` CTE unions the two bronze datasets through the `olist_staging_source` macro (`macros/olist_sources.sql`):

  ```sql
  with source as (

      {{ olist_staging_source('customers') }}

  ),
  ```

  The macro emits `select * from bronze_data.customers` and, **only when the
  reconcile table exists**, `union all select * from bronze_reconcile.customers`.
  The existence check (`adapter.get_relation`) happens at compile time, so the
  project still builds before the first reconciliation run.

- Deduplication via `row_number() over (partition by <natural key> order by updated_at desc, _dlt_load_id desc)`; keep `rn = 1`. This runs over the union, so a row recovered by a reconciliation run wins over an older version of the same key. `_dlt_load_id` is the deterministic tie-breaker: the seeder writes every row with the same `updated_at` in a single transaction, so without it the "latest" version would depend on engine row order. Both bronze datasets come from dlt, so the column is always present.
- Composite keys used where a single column isn't unique:
  - `order_items` → `(order_id, order_item_id)`
  - `order_payments` → `(order_id, payment_sequential)`
  - `reviews` → `(order_id, review_id)`
- Renames kept in source, fixed here: `product_name_lenght` → `product_name_length`, `product_description_lenght` → `product_description_length`.
- `geolocation_id` is the OLTP surrogate key (`BIGSERIAL`), carried through staging as-is. The 1M+ raw rows are collapsed later, in `int_geolocation_aggregated`, because the useful grain is city/state rather than a single point.

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
| `dim_products` | product attributes, with the raw (Portuguese) `product_category_name`; the English translation is joined in `int_order_items_enriched` |
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
`snapshots`. This works because `macros/generate_schema_name.sql` overrides dbt's
default macro, which would otherwise *append* the custom schema to the profile's
default schema (`bronze_data_stg`, `bronze_data_int`, `bronze_data_mart`).

```sql
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
```

Final dataset layout in BigQuery:

| Dataset | Written by | Contents |
|---|---|---|
| `bronze_data` | dlt | raw tables (the dbt source) |
| `bronze_reconcile` | dlt | reconciled tables (latest version per key) |
| `stg` | dbt | staging views |
| `int` | dbt | intermediate views |
| `mart` | dbt | gold tables (`fct_*`, `dim_*`) |
| `snapshots` | dbt | SCD2 `orders_snapshot` |
| `dbt_test__audit` | dbt | data test results |

The names `mart.*` and `int.*` are what the dashboard reads (see
`GoldTableRefs` in `packages/config/src/config/settings.py`), so this override is
what keeps the serving layer and the warehouse in sync.

Clean separation: raw (`bronze_data`) is kept untouched; dbt never writes there.

## 4. Materialization & rebuild semantics

dbt is **declarative**: the model SQL describes the desired end state, and `dbt run` makes reality match it on every run.

- **Views** are recreated each run (create or replace). Cheap.
- **Tables** are fully rebuilt each run (create or replace from current SQL). At ~100k orders this takes seconds.
- dbt does **not** incrementally merge by default. The `materialized='incremental'` strategy is available on BigQuery (native `MERGE`), and becomes valuable at larger scale — but at this size full rebuilds keep the models simple and the tests fully deterministic.

**Orphan cleanup gotcha:** if you move/rename a model or change its dataset, `dbt run` creates the new object but does **not** drop the old one. You clean up old objects yourself. E.g. dropping the pre-override datasets:

```sql
DROP SCHEMA IF EXISTS `project.bronze_data_stg` OPTIONS (delete_contents=TRUE);
DROP SCHEMA IF EXISTS `project.bronze_data_int` OPTIONS (delete_contents=TRUE);
DROP SCHEMA IF EXISTS `project.bronze_data_mart` OPTIONS (delete_contents=TRUE);
```

## 5. BigQuery SQL dialect (DuckDB → BigQuery)

The models were originally written for DuckDB. BigQuery's GoogleSQL differs in
a few places that bite silently — dbt compiles fine and only the warehouse
rejects the query:

| DuckDB | BigQuery | Notes |
|---|---|---|
| `datediff('day', start, end)` | `date_diff(end, start, DAY)` | **Arguments swapped**, part is a bare keyword, not a string. |
| `datediff('hour', start, end)` | `timestamp_diff(end, start, HOUR)` | `DATE_DIFF` only supports date-level parts (`DAY, WEEK, ISOWEEK, MONTH, QUARTER, YEAR, ISOYEAR`). For sub-day parts use `TIMESTAMP_DIFF` (`MICROSECOND…HOUR, DAY`). |
| `::` casts, `strftime`, `epoch` | `CAST(x AS y)`, `FORMAT_TIMESTAMP`, `UNIX_SECONDS` | Prefer the standard `CAST` form. |

One more BigQuery-ism appears in the dashboard's hand-written SQL (not in the
dbt models): `countif(condition)` instead of Postgres/DuckDB's
`count(*) filter (where ...)`. BigQuery does **not** support the `FILTER`
clause; `extract(year from ts)` works as-is.

BigQuery truncates rather than rounds in `*_DIFF` functions, and counts
*elapsed whole units* instead of DuckDB's *boundaries crossed* — a difference
of at most one unit on sub-day metrics.

## 6. Snapshots (SCD Type 2)

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

## 7. Tests

Data tests guard the layers (73 in total). Built-in tests used: `unique`, `not_null`, `accepted_values`, `relationships`. Plus one custom generic test: `assert_non_negative` (`tests/generic/`), which fails any row where a column is negative — used on money/count columns.

- `staging`: 29 tests — `unique` + `not_null` on single-column keys, FK integrity (`relationships` to the staging models), value whitelists (`accepted_values`), and `not_null` on required columns. Review `accepted_values` uses a `where:` config to skip NULLs. Composite-key tables (`order_items`, `order_payments`, `reviews`) deliberately get no composite uniqueness test: that needs `dbt_utils.unique_combination_of_columns`, and this project keeps the dependency out (see the decisions table). Their keys are covered by `not_null` and FK tests.
- `intermediate`: `unique` + `not_null` on single-column keys, `not_null` on joined keys, `accepted_values` on `order_status`, and `assert_non_negative` on money/counts.
- `marts`: `unique` + `not_null` on each `dim_*` key, plus `fct_orders` FK → `dim_customers` and `fct_order_payments` FK → `fct_orders` (referential integrity in gold).
- `snapshots`: `not_null` on `order_id`, `order_status`, `dbt_valid_from`.

Test placement matches dbt convention: a `_<layer>__models.yml` co-located in each model folder.

**FK tests point at the staging models, not at the raw source.** A staging row may come from the reconciliation dataset, and that row is not present in `bronze_data` — a `relationships` test against the raw source would fail on it. Testing against `ref('stg_olist__customers')` validates the cleaned set the model actually joins to.

### dbt 1.12 YAML conventions

Two syntax rules apply to every generic test in this project:

```yaml
      - name: review_score
        data_tests:
          - accepted_values:
              arguments:
                values: [1, 2, 3, 4, 5]
                quote: false
              config:
                where: "review_score is not null"
```

- Test **arguments** go under `arguments:`; test **configuration** (`where`, `severity`, `tags`, …) goes under `config:`. Top-level arguments still work in dbt 1.12 but emit deprecation warnings.
- `accepted_values` quotes its values by default (`quote: true`), which renders `'1','2','3','4','5'`. Against an `INT64` column BigQuery rejects that with `No matching signature for operator IN for argument types INT64 and {STRING}` — so numeric columns need `quote: false`.

### Test ordering

`make dbt-test` depends on `make dbt-snapshot`, because the snapshot tests run against the `snapshots` dataset, which only exists once a snapshot has been run. `make dbt-build` runs models → snapshot → tests in the right order in one command.

## 8. Usage

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

## 9. Key design decisions

| Decision | Why |
|---|---|
| BigQuery is the warehouse | Cloud DW from day one; the DuckDB iteration warehouse has been removed |
| Staging = views, marts = tables | Staging is recomputed every run (cheap, always fresh); marts are stored for fast BI reads |
| Dataset per layer (`stg`, `int`, `mart`, `snapshots`) | Layered architecture is visible at the warehouse level; keeps `bronze_data` raw untouched |
| `generate_schema_name` macro override | Makes `+schema` map 1:1 to a BigQuery dataset instead of dbt's default `<target>_<custom>` concatenation; the names the dashboard reads (`mart.*`, `int.*`) depend on it |
| BigQuery-native SQL (`date_diff` / `timestamp_diff`) | The warehouse rejects DuckDB's `datediff(part, start, end)`; BigQuery swaps the argument order and needs `timestamp_diff` for sub-day parts |
| Two-CTE staging pattern (`source → deduplicated` + final select) | Uniform, readable, testable — same shape in every staging model |
| Dedup in staging with `row_number()` | Bronze appends history; silver picks the latest version per natural key |
| Staging unions `bronze_data` + `bronze_reconcile` | Rows the incremental watermark skipped are recovered by the reconciliation run and reach silver exactly once |
| `olist_staging_source` macro | One place that knows about the two bronze datasets; the reconcile branch is emitted only when its table exists, so the project builds before the first backfill |
| Enrichment split into focused intermediates | One job per model, composable in gold, easy to test and reuse |
| `fct_orders` composes two intermediates via `ref()` | The DAG expresses real reuse instead of copy-pasted joins |
| `dbt_utils` skipped | Keep dependencies minimal; only built-in tests + one tiny custom test |
| Snapshots on orders | Demonstrates SCD Type 2 against the simulator's status changes |

## 10. What's next

- **Daily digest report:** the dashboard's daily summary, materialized for sharing.
- **Airbyte (Phase 3 deferred):** build the ingestion comparison pipeline.
- **Cloud (Phase 7):** Secret Manager for the SA key, Workload Identity on Cloud Run.

> Prefect orchestration (Phase 5) is implemented — see
> [`orchestration.md`](orchestration.md) and the `prefect-*` Makefile targets.

---

*Last updated: staging unions both bronze datasets; dbt 1.12 `arguments:`/`config:` test syntax (2026-10)*
