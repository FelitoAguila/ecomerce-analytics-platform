# dashboard (`olist-dashboard`)

The serving layer: a Streamlit app that reads the gold star schema (plus two
intermediate views and the orders snapshot) from BigQuery and renders it in the
browser. Plotly handles the charts.

The app is **read-only**: it never writes to the warehouse, never touches
Postgres, and holds no business logic — that lives in dbt. Design decisions and
page rationale are in [`docs/dashboard.md`](../../docs/dashboard.md).

**Contents:** [1. Run](#1-run) · [2. Pages](#2-pages) ·
[3. Layout](#3-layout) · [4. Configuration](#4-configuration) ·
[5. How queries work](#5-how-queries-work) ·
[6. Adding a page or query](#6-adding-a-page-or-query) ·
[7. Troubleshooting](#7-troubleshooting) · [8. Known limits](#8-known-limits)

## 1. Run

```bash
make dashboard
# or explicitly:
uv run --package olist-dashboard streamlit run packages/dashboard/src/dashboard/app.py
```

Open <http://localhost:8501>. The sidebar shows the target
`project.location` and a **Refresh data** button that clears the query and
client caches.

Preconditions:

- `make dbt-build` has run, so the `mart` / `int` / `snapshots` datasets exist
  in BigQuery.
- `.env` at the repo root has the `BIGQUERY__*` keys (see
  [Configuration](#4-configuration)).

## 2. Pages

| Page | Shows |
|---|---|
| **Overview** | KPI cards (orders, revenue, AOV, avg delivery days, delivered %), monthly orders/revenue, status funnel, top categories |
| **Orders** | Status over time by purchase cohort (snapshot, current version), current funnel, delivery by category, payment mix, installments; date-range filters in the sidebar |
| **Geography** | Brazil map (orders/revenue per state), state bars, top cities by customers |

## 3. Layout

| Path | Purpose |
|---|---|
| `src/dashboard/app.py` | Entry point: page config, sidebar, `st.navigation` |
| `src/dashboard/settings.py` | `Settings(ConfigBase)`: `bigquery` + `dashboard` (gold table refs) |
| `src/dashboard/connection.py` | Cached BigQuery client + `run_query` (parameter rewriting) |
| `src/dashboard/query.py` | Every SQL statement and the cached `run()` wrapper |
| `src/dashboard/views/*.py` | One module per page (`overview`, `orders`, `geography`) |

## 4. Configuration

Settings come from the shared `ConfigBase`, so they are read from the repo-root
`.env` (or OS env). Only these keys are consumed:

```dotenv
BIGQUERY__PROJECT=<gcp-project-id>
BIGQUERY__LOCATION=us-central1
BIGQUERY__KEYFILE=/absolute/path/to/service-account.json
```

Table identities are config-driven too — the dashboard never hardcodes a dataset
name. Defaults live in `GoldTableRefs` and can be overridden with `DASHBOARD__*`:

| Env var | Default |
|---|---|
| `DASHBOARD__FCT_ORDERS` | `mart.fct_orders` |
| `DASHBOARD__FCT_ORDER_PAYMENTS` | `mart.fct_order_payments` |
| `DASHBOARD__DIM_PRODUCTS` | `mart.dim_products` |
| `DASHBOARD__DIM_SELLERS` | `mart.dim_sellers` |
| `DASHBOARD__DIM_CUSTOMERS` | `mart.dim_customers` |
| `DASHBOARD__ORDERS_SNAPSHOT` | `snapshots.orders_snapshot` |
| `DASHBOARD__GEOLOCATION` | `int.int_geolocation_aggregated` |
| `DASHBOARD__ORDER_ITEMS` | `int.int_order_items_enriched` |

Names are `<dataset>.<table>`; a fully-qualified
`project.dataset.table` also works.

## 5. How queries work

- **Named params.** SQL uses `$name` placeholders, which `run_query` rewrites to
  BigQuery `@name` and binds as `STRING` scalars. All current params (date
  bounds) are strings.
- **One fetch path.** `query.run(sql, **params)` → cached `_cached` →
  `connection.run_query` → `client.query(...).to_dataframe()`.
- **Caching.** Query results use `st.cache_data(ttl=300)` (5 minutes); the
  BigQuery client uses `st.cache_resource`. **Refresh data** clears both.
- **BigQuery SQL only.** Write BigQuery dialect, not Postgres/DuckDB. In
  particular, BigQuery has no `FILTER` clause: use
  `countif(condition)` rather than `count(*) filter (where ...)`.

## 6. Adding a page or query

1. Add a function in `query.py` that builds SQL from `tables()` and calls
   `run(...)`; keep user input in params, never f-string it into SQL.
2. Add a module in `views/` exposing `page()`.
3. Register it in `app.py` with `st.Page(<module>.page, title=..., url_path=...)`.
4. If it needs a new table, add the field to `GoldTableRefs`
   (`packages/config/src/config/settings.py`) and document it in `.env.example`.
5. Exercise the function directly to catch dialect errors before opening the UI:

   ```bash
   uv run --package olist-dashboard python -c "from dashboard import query; print(query.kpis())"
   ```

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `400 Syntax error ... FILTER` | Postgres-style `count(*) filter (where ...)`; use `countif(...)` |
| `404 Not found: Table ...` | Gold/int/snapshot datasets missing — run `make dbt-build`, or the `DASHBOARD__*` override points at the wrong dataset |
| `Location ... does not match` | `BIGQUERY__LOCATION` differs from the dataset's region (must be `us-central1`) |
| `Service account key file not found` | `BIGQUERY__KEYFILE` is relative or wrong; use an absolute path |
| Stale numbers after `dbt build` | Click **Refresh data** (query cache TTL is 5 minutes) |

## 8. Known limits

- Queries are billed per byte scanned; fine at this data size, but the views
  scan live tables on every cache miss.
- Single-user local tool: no ACLs or multi-user sharing.
- The category/seller/geo views also read two intermediate models
  (`int_order_items_enriched`, `int_geolocation_aggregated`), because the gold
  marts intentionally stay minimal.

---

### See also

- [Root README](../../README.md) — end-to-end quickstart.
- [`docs/dashboard.md`](../../docs/dashboard.md) — design decisions and page rationale.
- [`.env.example`](../../.env.example) — all keys, including `DASHBOARD__*`.
- [`packages/pipeline/README.md`](../pipeline/README.md) — the dbt build that produces these tables.
