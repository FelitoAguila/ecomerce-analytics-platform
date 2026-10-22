# Dashboard (Streamlit)

Phase 6: the serving layer reads the **gold** star schema from BigQuery and
renders it in a browser. Built with Streamlit (Python-native, zero extra infra),
Plotly for charts.

Job of the app: **read and visualize only.** It never writes to the warehouse,
never touches Postgres, and holds no business logic — that's dbt's job.

---

## 1. Pages

| Page | Shows |
|---|---|
| **Overview** | KPI cards (orders, revenue, AOV, avg delivery days, delivered %), monthly order/revenue, status funnel, top categories |
| **Orders** | Status-over-time per purchase cohort (SCD2 snapshot, latest version), current funnel, delivery performance by category, payment mix + installments |
| **Geography** | Brazil map (orders/revenue by state), state bars, top cities |

## 2. Files

| File | Purpose |
|---|---|
| `packages/dashboard/src/dashboard/app.py` | Entry point: `uv run --package olist-dashboard streamlit run .../app.py` |
| `packages/dashboard/src/dashboard/query.py` | Every SQL statement, parameterized, in one place |
| `packages/dashboard/src/dashboard/connection.py` | BigQuery client (cached) + cached query helper |
| `packages/dashboard/src/dashboard/views/` | One module per page |

## 3. Config-driven table identities

The dashboard never hardcodes a dataset or table name. Everything comes from
pydantic-settings (env/`.env`):

```
BIGQUERY__PROJECT=<project>
BIGQUERY__LOCATION=us-central1
BIGQUERY__KEYFILE=/path/to/service-account.json

DASHBOARD__FCT_ORDERS=mart.fct_orders
DASHBOARD__FCT_ORDER_PAYMENTS=mart.fct_order_payments
DASHBOARD__DIM_CUSTOMERS=mart.dim_customers
...
```

- Every SQL fragment uses `get_settings().dashboard.<table>` for fully-qualified names.
- The SQL is written in a **portable subset** (standard `EXTRACT`, `CAST`, `COALESCE`), and named params use a `$name` placeholder rewritten to BigQuery `@name` in `connection.py`.

## 4. Caching model

Results and the BigQuery client are cached: query results with a 5-minute TTL
(hashable args only — strings/tuples), the client with `st.cache_resource`. A
"Refresh data" button clears both `st.cache_data` and `st.cache_resource`.

## 5. Usage

```bash
# run the app (deps come from the workspace)
make dashboard
# or: uv run --package olist-dashboard streamlit run packages/dashboard/src/dashboard/app.py
# open http://localhost:8501
```

Preconditions: `dbt build` has already run against BigQuery (gold + snapshots +
intermediate views exist), and `BIGQUERY__*` are set in `.env`.

## 6. Known limits (honest notes)

- Reads a live BigQuery dataset; queries are billed per byte scanned (fine at this size).
- No ACLs or multi-user sharing (single-user local tool) — fine for a portfolio, wrong for stakeholders.
- Category/seller/geo views use two `int` intermediate tables (`int_order_items_enriched`, `int_geolocation_aggregated`) in addition to gold, because the gold marts intentionally keep dims/facts minimal.

---

*Last updated: config-driven gold tables + `run_query` connection path (2026-10)*
