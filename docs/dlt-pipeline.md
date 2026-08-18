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
DuckDB (load_ecommerce_data.duckdb)
   └── ecommerce_data schema (customers, orders, order_items, ...)
```

## 2. How incremental loading works

Every table in Postgres has an `updated_at` column maintained by a trigger:
- `DEFAULT NOW()` stamps the insert time.
- `BEFORE UPDATE` triggers stamp every subsequent change.

dlt uses this column as a **cursor** (watermark). On each run:

1. dlt queries `_dlt_loads` to find the max `updated_at` from the previous load.
2. Extracts only rows where `updated_at > <previous max>`.
3. Loads the new rows into DuckDB (append-only).
4. Updates the watermark for the next run.

This means:
- **First run:** loads all rows (no previous watermark).
- **Second run onward:** only new/changed rows. Fast.
- **Status transitions** (e.g., shipped → delivered) appear as separate rows because the simulator creates new rows with a fresh `updated_at`. This is correct for a bronze layer — it preserves historical truth. The silver layer (dbt, Phase 4) deduplicates.

### Why append-only?

A bronze layer should be a faithful copy of the source. If an order goes from `shipped` to `delivered`, both states should exist in bronze. Silver (dbt) applies business logic to pick the latest state.

## 3. Files

| File | Purpose |
|---|---|
| `dlt_pipeline.py` | Main pipeline script |
| `.dlt/secrets.toml` | dlt config directory (empty — credentials come from `.env`) |
| `.dlt/config.toml` | Log level (INFO), telemetry (off) |
| `.gitignore` | Ignores `.duckdb`, `.wal`, `__pycache__/`, etc. |
| `load_ecommerce_data.duckdb` | DuckDB warehouse file (gitignored, ~90MB) |

## 4. Credentials

No secrets are committed. The flow:

```
.env (gitignored)
   │  load_dotenv() in Python
   v
os.environ
   │  os.getenv() builds DSN
   v
sql_database(credentials=dsn)
```

`secrets.toml` is kept empty — it exists only so dlt finds its `.dlt/` directory. The actual credentials live in `.env` (gitignored).

## 5. Usage

```bash
make dlt-pipeline           # run the pipeline (from project root)
uv run python src/dlt_pipeline/dlt_pipeline.py   # same thing, explicit path
```

First run takes several minutes (~1.3M rows, especially geolocation). Subsequent runs are fast (only new/changed rows).

## 6. Key design decisions

| Decision | Why |
|---|---|
| `pg8000` driver | Pure Python, no compiled dependencies. Works everywhere without system-level Postgres libs. |
| `updated_at` cursor | Change tracking without modifying the source. The Postgres triggers guarantee this column is always current. |
| Append-only bronze | Historical truth. Status transitions preserved as separate rows. Deduplication is silver's job. |
| `ALL_TABLES` list | Single source of truth. Adding a table means editing one list, not two. |
| `load_dotenv()` | Loads `.env` from project root. Needed because `make dlt-pipeline` changes to `src/dlt_pipeline/` (dlt looks for `.dlt/` relative to cwd). |
| DSN string | Credentials as a connection string. Simpler than passing a credentials dict, and works with `pg8000`. |

## 7. dlt warnings

You'll see warnings like:

```
Large number of records (50000) sharing the same value of cursor field 'updated_at'
```

This is expected. The Olist dataset has many rows with the same timestamp (e.g., all historical orders seeded at once). dlt handles this correctly — it uses internal deduplication. The warning is informational, not an error.

## 8. What's next

- **Verify incremental:** run the pipeline twice, confirm row counts don't grow.
- **Airbyte comparison:** build the same pipeline with Airbyte Python API, compare ergonomics, speed, and features.
- **dbt (Phase 4):** dbt reads `ecommerce_data.*` from DuckDB, builds silver + gold models with tests.

---

*Last updated: Phase 3 (dlt pipeline)*
