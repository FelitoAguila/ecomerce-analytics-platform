# Orchestration (Prefect)

Schedules and runs the ELT pipeline: dlt (bronze) → dbt build (silver/gold + tests).

---

## 1. What it does

Orchestrates two sequential tasks:

```
elt_flow
  └── run_elt()  → uv run elt                           (cwd: repo root; reads root .env)
                    ├── dlt ingest (incremental Postgres → BigQuery bronze)
                    └── cd packages/pipeline/dbt && uv run --group dbt-bigquery dbt build
                        (models + snapshot + tests, the full gate)
```

Sequential by design: keeps ordering deterministic and resource use predictable.

The reconciliation run is **not** part of the flow yet. It is a separate,
self-contained job that recovers rows the incremental watermark skipped:

```bash
make ingest-backfill SINCE=2026-10-01T00:00:00
```

It writes to its own dataset (`bronze_reconcile`), never moves the incremental
watermark, and can run on its own schedule without touching this flow — see
[`docs/dlt-pipeline.md`](dlt-pipeline.md#3-reconciliation-periodic-backfill).

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
# or: uv run --package olist-orchestration python -m orchestration.flows
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
| `packages/orchestration/src/orchestration/flows.py` | Flow + task (`run_elt`, `elt_flow`); shells out to `uv run elt` |
| `packages/orchestration/Dockerfile` | Worker image: Python 3.12 + uv, env at `/opt/venv` |
| `packages/orchestration/docker-compose.yaml` | Server + worker containers |
| `Makefile` | `prefect-*` targets (host mode) and `orc-*` targets (container mode); the deployment (`elt-daily`, cron `0 7 * * *`, `elt-pool`, `concurrency_limit=1`) is defined inline by `prefect-deploy`/`orc-deploy`. There is intentionally no `prefect.yaml`: one source of truth avoids drift between the file and the CLI flags |

## 5. Concurrency limit

The deployment has `concurrency_limit=1`: at most one run executes at a time. If a second run is triggered while the first is running, it queues. This keeps overlapping ELT runs from racing on the same BigQuery datasets.

## 6. Timezone

Schedules use the server's local timezone by default (your machine: `America/Sao_Paulo`, UTC-3). For explicit timezone control, use a `Schedule` object with `CronSchedule(timezone="...")`.

## 7. Key design decisions

| Decision | Why |
|---|---|
| Subprocess, not Python imports | The `elt` runner script (`uv run elt`) is the single entrypoint: dlt ingest then dbt build, each shelled out with their verified commands. Maps 1:1 to Airflow `BashOperator` and GCP Cloud Run job (see `docs/elt-runner.md`). |
| `dbt build` (not `run`) | Models + snapshot + tests in one gate — the full Phase 4 verification. |
| `--group dbt-bigquery` in dbt task | Guarantees dbt is available even if the group isn't synced. Self-documenting. |
| `limit=1` on deployment | Avoids overlapping ELT runs racing on the same BigQuery datasets. |
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
# packages/orchestration/docker-compose.yaml
prefect-server   # official prefecthq/prefect:3.8.5-python3.12, localhost:4200, sqlite in a volume
prefect-worker   # custom image (packages/orchestration/Dockerfile), repo bind-mounted at /app
```

Why it works with zero flow changes: `flows.py` shells out to `uv run --package olist-pipeline ingest` (cwd `/app`) and `dbt build` with `--env-file /app/.env` — both resolve inside the worker via the bind mount. `UV_PROJECT_ENVIRONMENT=/opt/venv` keeps the venv out of the mounted repo (no host `.venv` shadowing, no rebuild on code edits).

```bash
make orc-up        # build + start server & worker (provisions network; --build)
make orc-deploy    # one-time: register the 'elt-daily' deployment
make orc-run       # manual trigger of one run (or click Run in the UI)
make orc-logs      # tail worker logs: dlt -> dbt -> "ELT flow complete"
make orc-down      # stop both (volume keeps the server's history)
```

Pitfalls (only this containerized mode):

- **Stop the host Prefect first** (`make prefect-server`/`prefect-worker` in their terminals) — port 4200 clashes, and the host and container servers have separate SQLite stores.
- **Creds come from `.env`** (repo root, via `--env-file .env`): `POSTGRES_DB__DSN` (Neon), `BIGQUERY__PROJECT`/`BIGQUERY__LOCATION`, and the SA key mounted read-only at `/app/secrets/gcp-sa.json`.
- **`docker compose down -v` deletes `prefect-server-data`** — deployment + run history gone; re-run `make orc-deploy`.

### See also

For a standalone ELT runner image (no Prefect — baked code, one-shot `make elt-docker`), see [`docs/elt-runner.md`](elt-runner.md).

---

*Last updated: BigQuery migration + reconciliation-aware ELT (2026-10)*
