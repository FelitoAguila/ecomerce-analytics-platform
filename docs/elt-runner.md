# ELT Runner (`uv run elt`)

The single entrypoint that runs the whole analytics pipeline from source to tested gold.

Phase 6 serving work surfaced the need for a reproducible, orchestration-free way to run the full ELT after the config refactor: `make ingest && make dbt-build` became `uv run elt`. The same script is what the Prefect flow and the Dockerized runner both shell out to.

---

## 1. What it does

```
uv run elt
├── dlt ingest                     cwd: repo root (reads root .env via pydantic-settings)
│   incremental Postgres → BigQuery bronze (bronze_data dataset)
└── dbt build                      cwd: packages/pipeline/dbt
    models (views + marts) → snapshot (SCD2) → 73 tests, the full gate
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
| `packages/pipeline/src/pipeline/run_elt.py` | The runner: `run_ingest()` + `run_dbt()` + `main()`; console script `elt` in `pyproject.toml` |
| `packages/orchestration/src/orchestration/flows.py` | `run_elt` task shells out to `uv run elt` (no duplicated subprocess logic) |
| `packages/pipeline/Dockerfile` | Baked job image: installs only `olist-pipeline` + `global-config` (`uv sync --frozen --package olist-pipeline --group dbt-bigquery`) plus the dbt project; `ENTRYPOINT uv run --no-sync --package olist-pipeline elt` |
| `packages/pipeline/docker-compose.yaml` | One-shot `elt` job: `BIGQUERY__*` env + SA key mount + `.env` |

## 3. Dockerized ELT (`make elt-docker`)

Why a container at all (the host `uv run elt` already works): reproducibility and it's the exact shape of a Phase 7 GCP **Cloud Run job** — code baked, env passed by the orchestrator, state in BigQuery.

```bash
make elt-build    # build the ELT job image (uv sync --frozen --group dbt-bigquery)
make elt-docker   # one-shot run against Neon + BigQuery
```

How it wires up (all in `packages/pipeline/docker-compose.yaml`):

- `POSTGRES_DB__DSN` (Neon) and `BIGQUERY__PROJECT`/`BIGQUERY__LOCATION` come from the repo-root `.env` via `--env-file .env` interpolation.
- The service-account key is mounted read-only at `/app/secrets/gcp-sa.json` and pointed to by `BIGQUERY__KEYFILE`.
- `.env` is mounted read-only so `uv run --env-file /app/.env dbt` works; the compose `environment:` block still wins (OS env > dotenv, same rule as the Prefect worker).
- No warehouse volume: BigQuery holds the data and the durable dlt watermark state (`_dlt_pipeline_state`). A fresh container syncs that state from BigQuery on startup, so runs stay incremental without a mounted `~/.dlt`.

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

- **Neon + BigQuery creds**: the job needs a reachable Postgres DSN and valid BigQuery creds (`BIGQUERY__KEYFILE`).
- **Source must be live**: the job reads Neon; the simulator's continuous mode is a prerequisite for new rows.

---

*Last updated: object-storage seeding + reconcile pipeline + baked ELT image (2026-10)*
