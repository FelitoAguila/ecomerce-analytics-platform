# ELT Runner (`uv run elt`)

The single entrypoint that runs the whole analytics pipeline from source to tested gold.

Phase 6 serving work surfaced the need for a reproducible, orchestration-free way to run the full ELT after the config refactor: `make ingest && make dbt-build` became `uv run elt`. The same script is what the Prefect flow and the Dockerized runner both shell out to.

---

## 1. What it does

```
uv run elt
├── dlt ingest                     cwd: repo root (reads root .env via pydantic-settings)
│   incremental Postgres → DuckDB bronze (ecommerce_data schema)
└── dbt build                      cwd: pipeline/dbt
    models (views + marts) → snapshot (SCD2) → 92 tests, the full gate
```

Usage:

```bash
uv run elt                 # everything
uv run elt --ingest-only   # bronze only
uv run elt --dbt-only      # silver/gold/tests only (mutually exclusive flags)
make elt                   # same as `uv run elt`
```

Exit code is propagated: a failing dlt job or failing dbt test exits non-zero — fail-fast by design.

## 2. Files

| File | Purpose |
|---|---|
| `pipeline/src/pipeline/run_elt.py` | The runner: `run_ingest()` + `run_dbt()` + `main()`; console script `elt` in `pyproject.toml` |
| `orchestration/prefect/flows.py` | `run_elt` task shells out to `uv run elt` (no duplicated subprocess logic) |
| `pipeline/Dockerfile` | Baked job image: project wheel (config/pipeline/dashboard/ecommerce_db) + the dbt project; `ENTRYPOINT uv run --no-sync elt` |
| `pipeline/docker-compose.yaml` | One-shot `elt` job: joins the OLTP network, mounts the warehouse + `.env` |

## 3. Dockerized ELT (`make elt-docker`)

Why a container at all (the host `uv run elt` already works): reproducibility and it's the exact shape of a Phase 7 GCP **Cloud Run job** — code baked, env passed by the orchestrator, state in persistent storage.

```bash
make elt-build    # build image ecommerce_db-elt (uv sync --frozen --group dbt-duckdb)
make elt-docker   # one-shot run against the live OLTP stack
```

How it wires up (all in `pipeline/docker-compose.yaml`):

- `name: ecommerce_db` → the job joins the existing `ecommerce_db_default` network, so the DSN resolves `postgresql://...@ecommerce_db:5432/ecommerce`.
- `WAREHOUSE_LOCAL__PATH=/app/data/warehouse/ecommerce.duckdb` with `../data/warehouse:/app/data/warehouse` mounted — the DuckDB file lives on the host, so the **dlt watermark travels with it** and container runs stay incremental.
- `.env` is mounted read-only so `uv run --env-file /app/.env dbt` works; the compose `environment:` block still wins (OS env > dotenv, same rule as the Prefect worker).

Why the image is *baked*, not bind-mounted: it stays Cloud Run-shaped (build → run anywhere). The Prefect worker, by contrast, bind-mounts the repo for hot code reloading — two different trade-offs for two different tools.

## 4. Relationship to orchestration

`uv run elt` is the work; Prefect is the schedule. The same command appears in three layers with no copy-paste:

```
make elt          → host, manual
make elt-docker   → container, manual (Cloud Run-shaped)
elt_flow          → prefect-worker/container, scheduled (daily 07:00, concurrency 1)
```

Airflow (Phase 7 comparison) will shell out to `uv run elt` the same way — a `BashOperator` mapping 1:1 to the current `run_elt` task.

## 5. Rules that still apply

- **DuckDB single-writer**: don't run `elt-docker` while host `make ingest`/`dbt-build` or the dashboard is mid-read (host and container share the same warehouse file).
- **OLTP must be up**: the job reads Postgres; the simulator's continuous mode is a prerequisite for new rows.

---

*Phase 6 (config → runner → container): the ELT moves from scripts to a deployable unit.*