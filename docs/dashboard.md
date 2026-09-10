# Dashboard (Streamlit)

Phase 6: the serving layer reads the **gold** star schema from the warehouse and renders it in a browser. Built with Streamlit (Python-native, zero extra infra), Plotly for charts.

Job of the app: **read and visualize only.** It never writes to the warehouse (opened `read_only=True`), never touches Postgres, and holds no business logic — that's dbt's job.

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
| `dashboard/app.py` | Entry point: `uv run --group dashboard streamlit run dashboard/app.py` |
| `dashboard/query.py` | Every SQL statement, parameterized, in one place |
| `dashboard/connection.py` | Read connection (cached) + cached query helper |
| `dashboard/views/` | One module per page |

## 3. Config-driven, no code changes to swap warehouses

The dashboard never hardcodes a warehouse path or table name. Everything comes from pydantic-settings (env/`.env`):

```
DASHBOARD__SOURCE=duckdb            # duckdb | bigquery (Phase 7)
DASHBOARD__FCT__ORDERS=main_mart.fct_orders
DASHBOARD__FCT__ORDER_PAYMENTS=main_mart.fct_order_payments
DASHBOARD__DIM_CUSTOMERS=main_mart.dim_customers
...
```

- `get_settings().dashboard.source` selects the connection.
- Every SQL fragment uses `get_settings().dashboard.<table>` for fully-qualified names.
- The SQL is written in a **portable subset** (standard `EXTRACT`, `CAST`, `COALESCE`, no DuckDB-only `date_trunc`/`strftime`), so the same statements run on BigQuery.

Switching to BigQuery at Phase 7 = set `DASHBOARD__SOURCE=bigquery` + the table names, and implement the `bigquery` branch in `connection.py`. No query or view changes.

Why not `st.connection("duckdb")`: it's SQLAlchemy-oriented; a direct DuckDB connection is simpler and reads as a clear pattern. If BigQuery integration wants `st.connection("bigquery")` later, the swap stays confined to `connection.py`.

## 4. Caching model

Per DuckDB + Streamlit guidance, results are cached (not the connection object) with a 5-minute TTL, and query functions take only hashable args (strings/tuples). A "Refresh data" button clears both `st.cache_data` and `st.cache_resource`.

## 5. Usage

```bash
# one-time: install the dashboard group
uv sync --group dashboard

# run the app
make dashboard                       # or: uv run --group dashboard streamlit run dashboard/app.py
# open http://localhost:8501
```

Preconditions: warehouse exists with `dbt build` already run (gold + snapshots + intermediate views), and the ELT is **not** running concurrently (DuckDB single-writer rule — the dashboard opens read-only; it fails to open while dlt/dbt holds the write lock, which is a clear signal).

## 6. Known limits (honest notes)

- Reads the live DuckDB file; concurrent ELT writes block reads (see §5). Containerizing with a read replica / export is a Phase 7 concern.
- No ACLs or multi-user sharing (single-user local tool) — fine for a portfolio, wrong for stakeholders.
- Category/seller/geo views use two `main_int` intermediate tables (`int_order_items_enriched`, `int_geolocation_aggregated`) in addition to gold, because the gold marts intentionally keep dims/facts minimal.

---

*Phase 6 (serving) — first gate: dashboard. Reports/digest is the second gate.*