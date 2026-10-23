# orchestration (`olist-orchestration`)

Prefect flows that schedule the ELT: dlt ingest (Postgres → BigQuery bronze)
followed by `dbt build` (silver/gold + snapshot + tests). The flow shells out to
the pipeline's `elt` entry point, so the same code path runs locally, under
Prefect, and in the container.

Design rationale, Airflow mapping, and WSL2 notes are in
[`docs/orchestration.md`](../../docs/orchestration.md).

**Contents:** [1. Flow model](#1-flow-model) · [2. Run modes](#2-run-modes) ·
[3. Configuration](#3-configuration) · [4. Container mode](#4-container-mode) ·
[5. Schedule and limits](#5-schedule-and-limits) ·
[6. Troubleshooting](#6-troubleshooting)

## 1. Flow model

| File | Contents |
|---|---|
| `src/orchestration/flows.py` | `elt_flow` (the `@flow`) and the `--serve` CLI flag |
| `src/orchestration/tasks.py` | `run_elt` task: `uv run --package olist-pipeline elt` in the repo root |

`run_elt`:

- Retries **once** after 10s (both dlt incremental and dbt rebuild are safe to repeat).
- Has a **2-hour timeout** (`ELT_TIMEOUT_SECONDS`) so a hung run can't block the worker.
- Captures stdout/stderr and prints them (including on failure, before re-raising)
  with `log_prints=True`, so dlt/dbt diagnostics appear in the Prefect run logs.

The reconciliation job is intentionally **not** in the flow. Run it separately
when needed: `make ingest-backfill SINCE=...` (see
[`docs/dlt-pipeline.md`](../../docs/dlt-pipeline.md)).

## 2. Run modes

All commands run from the repo root.

### Once (no server required)

```bash
make prefect-flow
# or: uv run --package olist-orchestration python -m orchestration.flows
```

### Serve (one long-running process)

Registers the `elt-daily` deployment and runs its own runner. Start the server
first if you want the UI:

```bash
make prefect-server   # terminal 1 → http://localhost:4200
make prefect-serve    # terminal 2
```

### Work pool + worker (production pattern)

```bash
make prefect-server   # terminal 1
make prefect-pool     # create/update elt-pool (idempotent)
make prefect-worker   # terminal 2
make prefect-deploy   # register the elt-daily deployment
```

`prefect-deploy` passes `--no-prompt`, so it never offers to write a
`prefect.yaml`. The deployment is defined by the Makefile flags (cron, pool,
concurrency); keeping it there avoids drift with a YAML file.

## 3. Configuration

Prefect itself needs no project-level config beyond `PREFECT_API_URL` (host mode
defaults to `http://127.0.0.1:4200/api`). The ELT tasks inherit the repo-root
`.env`:

```dotenv
POSTGRES_DB__DSN=postgresql://...
BIGQUERY__PROJECT=<gcp-project-id>
BIGQUERY__LOCATION=us-central1
BIGQUERY__KEYFILE=/absolute/path/to/service-account.json
```

## 4. Container mode

Runs both roles in Docker — the worker executes dlt + dbt inside the container.

```bash
make orc-up       # build + start server & worker (worker auto-creates elt-pool)
make orc-deploy   # register elt-daily
make orc-run      # trigger one run now (or click Run in the UI)
make orc-logs     # follow worker logs
make orc-down     # stop (volume keeps server history)
```

The worker image (`Dockerfile`) installs `olist-orchestration` +
`olist-pipeline` + the `dbt-bigquery` group. The repo is bind-mounted at `/app`
for live code, `UV_PROJECT_ENVIRONMENT=/opt/venv` keeps the venv out of the
mount, and the SA key is mounted read-only at `/app/secrets/gcp-sa.json`.

## 5. Schedule and limits

- **Schedule:** daily at **07:00 `America/Sao_Paulo`**. Prefect cron schedules
  default to UTC, so both deploy paths pass the timezone explicitly
  (`prefect deploy --timezone`, `CronSchedule(timezone=...)` in `.serve`).
- **Concurrency:** `prefect deploy` sets the deployment's
  `concurrency_limit=1`; `flow.serve(limit=1)` sets the runner limit. Either way
  one ELT runs at a time, so runs never race on the same BigQuery datasets.
- `pause_on_shutdown=False` in serve mode keeps the schedule registered when the
  serve process stops.

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Port 4200 already in use | Stop the host server before `make orc-up` (host and container servers have separate SQLite stores) |
| `Work pool ... does not exist` on deploy | Start the worker (auto-creates it) or run `make prefect-pool` |
| Deployment runs at the wrong hour | Check the timezone arg; Prefect cron defaults to UTC |
| `prefect.yaml` reappeared after deploy | It was an older deploy without `--no-prompt`; delete it and redeploy |
| Deployment/history lost | `docker compose down -v` deletes `prefect-server-data`; re-run `make orc-deploy` |
| Task timed out | 2h cap reached; check dlt/dbt logs (now included in the run logs) |

---

### See also

- [Root README](../../README.md) — end-to-end quickstart and target list.
- [`docs/orchestration.md`](../../docs/orchestration.md) — architecture, Airflow mapping, design decisions.
- [`docs/elt-runner.md`](../../docs/elt-runner.md) — the `uv run elt` entry point the flow calls.
- [`packages/pipeline/README.md`](../pipeline/README.md) — dlt + dbt details.
