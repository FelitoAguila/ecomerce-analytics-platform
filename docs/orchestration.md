# Orchestration (Prefect)

Schedules and runs the ELT pipeline: dlt (bronze) → dbt build (silver/gold + tests).

---

## 1. What it does

Orchestrates two sequential tasks:

```
elt_flow
  └── run_elt()  → uv run elt                           (cwd: repo root; reads root .env)
                    ├── dlt ingest (incremental Postgres → DuckDB bronze)
                    └── cd pipeline/dbt && uv run --group dbt-duckdb dbt build
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
| `orchestration/prefect/flows.py` | Flow + task (`run_elt`, `elt_flow`); shells out to `uv run elt` |
| `orchestration/Dockerfile` | Worker image: Python 3.12 + uv, env at `/opt/venv` (main + dbt-duckdb + orchestration groups) |
| `orchestration/docker-compose.yaml` | Server + worker containers (project `ecommerce_db`, joins the OLTP network) |
| `Makefile` | `prefect-*` targets (host mode) and `orc-*` targets (container mode); deployment config lives in the `prefect-deploy`/`orc-deploy` targets (no `prefect.yaml` needed) |

## 5. Concurrency limit

The deployment has `concurrency_limit=1`: at most one run executes at a time. If a second run is triggered while the first is running, it queues. This enforces the DuckDB single-writer rule at the orchestration level.

## 6. Timezone

Schedules use the server's local timezone by default (your machine: `America/Sao_Paulo`, UTC-3). For explicit timezone control, use a `Schedule` object with `CronSchedule(timezone="...")`.

## 7. Key design decisions

| Decision | Why |
|---|---|
| Subprocess, not Python imports | The `elt` runner script (`uv run elt`) is the single entrypoint: dlt ingest then dbt build, each shelled out with their verified commands. Maps 1:1 to Airflow `BashOperator` and GCP Cloud Run job (see `docs/elt-runner.md`). |
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
| `prefect deploy ...` (Makefile) | `dag_bag` + deployment config |
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

## 10b. Containerized orchestration (docker compose)

The same server + worker pattern, but **both run in containers** — the worker executes the whole ELT (dlt + dbt subprocesses) inside Docker. Closest to the Phase 7 story (worker becomes a Cloud Run container).

```yaml
# orchestration/docker-compose.yaml  (name: ecommerce_db so it shares the OLTP network)
prefect-server   # official prefecthq/prefect:3.8.5-python3.12, localhost:4200, sqlite in a volume
prefect-worker   # custom image (orchestration/Dockerfile), repo bind-mounted at /app
```

Why it works with zero flow changes: `flows.py` shells out to `uv run ingest` (cwd `/app`) and `dbt build` with `--env-file /app/.env` — both resolve inside the worker via the bind mount. `UV_PROJECT_ENVIRONMENT=/opt/venv` keeps the venv out of the mounted repo (no host `.venv` shadowing, no rebuild on code edits).

```bash
make orc-up        # build + start server & worker (provisions network; --build)
make orc-deploy    # one-time: register the 'elt-daily' deployment
make orc-run       # manual trigger of one run (or click Run in the UI)
make orc-logs      # tail worker logs: dlt -> dbt -> "ELT flow complete"
make orc-down      # stop both (volume keeps the server's history)
```

Pitfalls (only this containerized mode):

- **Stop the host Prefect first** (`make prefect-server`/`prefect-worker` in their terminals) — port 4200 clashes, and the host and container servers have separate SQLite stores.
- **DSN is overridden on purpose** in compose: `POSTGRES_DB__DSN=postgresql://postgres:postgres@ecommerce_db:5432/ecommerce`. The host `.env` says `localhost`, which is meaningless inside the worker; compose env wins over the `.env` file (pydantic-settings priority: OS env > dotenv).
- **DuckDB single-writer still applies across the boundary** — don't run host `make ingest`/`dbt-build` while the worker is mid-flow.
- **`docker compose down -v` deletes `prefect-server-data`** — deployment + run history gone; re-run `make orc-deploy`.

### See also

For a standalone ELT runner image (no Prefect — baked code, one-shot `make elt-docker`), see [`docs/elt-runner.md`](elt-runner.md).

---

*Last updated: Phase 5 (orchestration) + containerized mode (2026-09)*