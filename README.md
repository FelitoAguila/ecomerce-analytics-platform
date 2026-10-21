# Olist E-Commerce — Analytics Platform

A simulated Brazilian e-commerce OLTP database (Postgres on Neon, ~100k orders)
with an analytics pipeline feeding a BigQuery warehouse, dbt transformations,
Prefect orchestration, and a Streamlit dashboard.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker + Docker Compose
- A Neon Postgres database (managed OLTP)
- A GCP project + BigQuery service-account key

## Dataset

Download the Olist public dataset:

1. Download the zip from [Google Drive](https://drive.google.com/file/d/1HIy4LNNQESuXUj-u_mNJTCGCRrCeSbo-/view?usp=share_link)
2. Extract the `olist-dataset` folder into `packages/ecommerce_db/` so you get
   `packages/ecommerce_db/olist-dataset/*.csv`

The 9 CSVs (~121MB total) are gitignored and not shipped with the repo.

## Configuration

```bash
cp .env.example .env
```

Fill in `.env`:

```
POSTGRES_DB__DSN=postgresql://<user>:<password>@<host>/olist_db
BIGQUERY__PROJECT=<gcp-project-id>
BIGQUERY__LOCATION=US
BIGQUERY__KEYFILE=/absolute/path/to/service-account.json
```

## Quickstart

```bash
# Seed Neon with the historical Olist data (one-shot, verified):
make seed

# Simulate live data (continuous, detached):
make simulate

# Full ELT: dlt ingest (Neon -> BigQuery bronze) -> dbt build (silver + gold + tests):
make elt

# Launch the dashboard (reads BigQuery gold):
make dashboard
```

## Makefile targets

| Target | Description |
|---|---|
| `make docker-build` | Build the seeder/simulator image |
| `make seed` | Seed Neon (one-shot, row-count verified) |
| `make simulate` | Run the continuous simulator (detached) |
| `make simulate-once` | One simulator batch locally (50 orders) |
| `make ingest` | dlt pipeline: Neon → BigQuery bronze |
| `make elt` | Full ELT: dlt ingest → dbt build (the everyday command) |
| `make elt-build` | Build the baked ELT job image |
| `make elt-docker` | Run the full ELT inside a container |
| `make dbt-debug` | Verify the BigQuery connection + config |
| `make dbt-parse` | Re-render project; catch YAML/syntax errors |
| `make dbt-run` | Build all models (staging → intermediate → marts) |
| `make dbt-test` | Run all data tests |
| `make dbt-build` | Full gate: models + snapshot + tests in order |
| `make dbt-snapshot` | Run SCD Type 2 snapshots only |
| `make dbt-docs` | Generate + serve lineage docs (localhost:8080) |
| `make prefect-server` | Start local Prefect server (localhost:4200) |
| `make prefect-flow` | Run ELT flow once (manual trigger) |
| `make prefect-serve` | Serve as daily 07:00 deployment |
| `make prefect-pool` | Create process work pool (one-time) |
| `make prefect-deploy` | Deploy flow to work pool |
| `make prefect-worker` | Start worker that pulls from pool |
| `make dashboard` | Launch the Streamlit dashboard (localhost:8501) |

`make dbt-*` targets run from `packages/pipeline/dbt/` and pass
`--group dbt-bigquery` (installs the adapter) and `--env-file .env` (so
`BIGQUERY__*` reaches `profiles.yml`). `make elt` wraps both stages with
exit-code propagation; `make elt-docker` is the containerized version
(docs: `docs/elt-runner.md`).

## Project structure

```
olist-ecommerce/                # uv virtual workspace; members under packages/*
├── README.md
├── Makefile                    # short targets for common commands
├── pyproject.toml              # workspace root: members + sources + ruff config
├── .env / .env.example         # Neon DSN + BigQuery creds (gitignored)
├── config/                     # shared settings foundation (ConfigBase, BigQuery, GoldTableRefs)
├── packages/ecommerce_db/      # OLTP: seed + simulator (dockerized, Neon-backed)
│   ├── Dockerfile              # Python 3.12 + uv (shared by seed + simulator)
│   ├── docker-compose.yaml     # seed + simulator services (no local Postgres)
│   ├── olist-dataset/          # 9 Olist CSVs (~121MB, gitignored)
│   └── src/ecommerce_db/       # package: config, seed.py, simulator.py, helpers/
├── packages/pipeline/          # analytics pipeline: ELT runner + dbt
│   ├── Dockerfile              # baked ELT job image (`uv sync --frozen --group dbt-bigquery`)
│   ├── docker-compose.yaml     # one-shot elt job (BIGQUERY__* env + SA key mount + .env)
│   ├── src/pipeline/           # ELT package (installed via uv/hatch)
│   │   ├── config.py           # pydantic-settings: Postgres / BigQuery / pipeline
│   │   ├── ingestion.py        # dlt: Postgres → BigQuery bronze (entry: `ingest`)
│   │   └── run_elt.py          # `uv run elt`: ingest → dbt build (--ingest-only / --dbt-only)
│   └── dbt/                    # transformations: silver + gold + tests
│       ├── dbt_project.yml     # per-layer materialization + schema config
│       ├── profiles.yml        # BigQuery connection (project/location/keyfile via env_var)
│       ├── models/             # staging/ → intermediate/ → marts/
│       ├── snapshots/          # orders snapshots (SCD Type 2)
│       └── tests/generic/      # custom generic tests
├── packages/orchestration/     # containerized Prefect server + worker
│   ├── src/orchestration/
│   │   └── flows.py            # elt_flow: ingest → dbt build (tasks, --serve)
│   ├── Dockerfile              # worker image (server+worker stack, docker compose)
│   └── docker-compose.yaml     # containerized Prefect
├── packages/dashboard/         # Streamlit BI (reads BigQuery gold)
│   └── src/dashboard/
│       ├── app.py              # Streamlit entry (Overview / Orders / Geography)
│       ├── query.py            # all SQL (portable dialect subset), config-driven table names
│       ├── connection.py       # BigQuery client + cached query helper
│       └── views/              # one module per page
└── docs/
    ├── oltp-guide.md      # schema, seed, and simulator decisions
    ├── dlt-pipeline.md    # dlt pipeline architecture and decisions
    ├── dbt-guide.md       # dbt layers, schema strategy, tests, snapshots
    ├── orchestration.md   # Prefect setup, Airflow mapping, WSL2 notes
    ├── dashboard.md       # Phase 6: Streamlit dashboard, config-driven tables
    └── elt-runner.md      # the `uv run elt` runner + Dockerized ELT job
```

## Phase status

- [x] **0. Foundations** — repo layout, deps (uv), Makefile
- [x] **1. OLTP + seed** — Postgres schema, triggers, COPY loader
- [x] **2. Simulator** — fake backend generating live data + anomalies
- [x] **3. ELT (dlt)** — incremental Neon → BigQuery `bronze_data`
- [x] **4. dbt** — silver/gold star schema, SCD2 snapshots, 73 tests
- [x] **5. Orchestration** — Prefect flows (Airflow port later)
- [x] **6. Serving** — Streamlit dashboard (daily digest pending)
- [ ] **7. Cloud (GCP)** — managed Postgres, managed orchestration, IaC

## Design decisions

See [`docs/`](docs/) for detailed decision logs on schema, ELT, dbt, and orchestration choices.
