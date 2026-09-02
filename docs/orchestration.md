# Orchestration (Prefect)

Schedules and runs the ELT pipeline: dlt (bronze) → dbt build (silver/gold + tests).

---

## 1. What it does

Orchestrates two sequential tasks:

```
elt_flow
  │
  ├── run_dlt()    → cd src/dlt_pipeline && uv run python dlt_pipeline.py
  │                  (incremental extract from Postgres → DuckDB bronze)
  │
  └── run_dbt()    → cd dbt && uv run dbt build
                     (models + snapshot + tests, the full gate)
```

Sequential by design: dlt and dbt must never run concurrently (DuckDB single-writer rule).

## 2. Architecture

Prefect has two decoupled roles:

| Component | Role | Local | Phase 7 (GCP) |
|---|---|---|---|
| **Server** | Brain: stores schedules, runs, logs, UI | `prefect server start` | Prefect Cloud (managed) |
| **Worker** | Executor: listens for work, runs flows | `prefect worker start --pool elt-pool` | GCP Cloud Run container |

The server and worker are independent processes. The server never runs flow code; the worker never stores state. This is the same pattern as Airflow (scheduler + worker) — porting later is 1:1.

## 3. Deployment modes

### Run once (manual trigger)
```bash
make prefect-flow
# or: uv run --group orchestration python orchestration/prefect/flows.py
```
No server needed (but run appears in UI if server is up). Good for testing.

### Serve (scheduled, one process)
```bash
# Terminal 1: server
make prefect-server

# Terminal 2: serve process
make prefect-serve
```
Registers a deployment + starts a long-running process that listens for scheduled runs. Daily at 07:00.

### Work pool + worker (production pattern)
```bash
# Terminal 1: server
make prefect-server

# Terminal 2: worker
make prefect-worker

# Deploy (one-time):
make prefect-deploy
```
Deployment is registered with the server, bound to a work pool. Worker polls the pool and executes. This is the pattern that maps to Airflow and GCP Cloud Run.

## 4. Files

| File | Purpose |
|---|---|
| `orchestration/prefect/flows.py` | Flow + tasks (`run_dlt`, `run_dbt`, `elt_flow`) |
| `prefect.yaml` | Deployment config (name, pool, schedule) |
| `Makefile` | `prefect-*` targets |

## 5. Concurrency limit

The deployment has `concurrency_limit=1`: at most one run executes at a time. If a second run is triggered while the first is running, it queues. This enforces the DuckDB single-writer rule at the orchestration level.

## 6. Timezone

Schedules use the server's local timezone by default (your machine: `America/Sao_Paulo`, UTC-3). For explicit timezone control, use a `Schedule` object with `CronSchedule(timezone="...")`.

## 7. Key design decisions

| Decision | Why |
|---|---|
| Subprocess, not Python imports | dlt needs `cwd=src/dlt_pipeline` for `.dlt/` config; dbt needs `cwd=dbt` (no `--project-dir` in 1.9+). Preserves verified behavior. Maps 1:1 to Airflow `BashOperator`. |
| `dbt build` (not `run`) | Models + snapshot + tests in one gate — the full Phase 4 verification. |
| `--group dbt-duckdb` in dbt task | Guarantees dbt is available even if the group isn't synced. Self-documenting. |
| `limit=1` on deployment | DuckDB single-writer guarantee enforced at orchestration level. |
| `retries=1` on tasks | Both dlt (incremental) and dbt (declarative rebuild) are idempotent — safe to retry. |
| Local server, not Cloud | Fast iteration for development. Cloud for demos/Phase 7. |

## 8. WSL2 networking

`prefect server start` defaults to `127.0.0.1` which is unreachable from Windows browsers. Use `--host 0.0.0.0` so Windows can access the UI via `localhost:4200`.

## 9. Airflow mapping

| Prefect | Airflow equivalent |
|---|---|
| `@flow` | DAG |
| `@task` | Operator (BashOperator for subprocess) |
| Work pool | Task queue |
| Worker | Celery/Kubernetes executor |
| `prefect.yaml` | `dag_bag` + deployment config |
| `flow.serve()` | `airflow dags trigger` + scheduler |
| `PREFECT_API_URL` | `AIRFLOW__CORE__SQL_ALCHEMY_CONN` |

## 10. Usage

```bash
# Quick test (no server needed)
make prefect-flow

# Scheduled mode (two terminals)
make prefect-server    # Terminal 1
make prefect-serve     # Terminal 2

# Production pattern (three terminals)
make prefect-server    # Terminal 1
make prefect-worker    # Terminal 2
make prefect-deploy    # Run once to register deployment
```

---

*Last updated: Phase 5 (orchestration)*