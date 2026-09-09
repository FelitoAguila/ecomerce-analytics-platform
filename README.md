# Olist E-Commerce — Data Engineering Portfolio

A simulated Brazilian e-commerce OLTP database (Postgres, ~100k orders) with
an analytics pipeline feeding a DuckDB warehouse, dbt transformations, and
orchestration. 

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker + Docker Compose

## Dataset

Download the Olist public dataset:

1. Download the zip from [Google Drive](https://drive.google.com/file/d/1HIy4LNNQESuXUj-u_mNJTCGCRrCeSbo-/view?usp=share_link)
2. Extract the `olist-dataset` folder into `ecommerce_db/` so you get `ecommerce_db/olist-dataset/*.csv`

The 9 CSVs (~121MB total) are gitignored and not shipped with the repo.

## Quickstart

```bash
cp .env.example .env
docker compose up -d

# Seed loads historical data once → simulator starts generating live data
# Open a SQL shell to explore:
make db-shell

# Run the ELT pipeline: extract from Postgres → load into DuckDB (bronze)
make ingest

# Run dbt: build models + snapshot + tests (silver/gold layers)
make dbt-build

# Stop everything:
docker compose down
```

One-liner to reset from scratch:

```bash
docker compose down -v && docker compose up -d
```

## Makefile targets

| Target | Command | Description |
|---|---|---|
| `make up` | `docker compose up -d` | Start the full OLTP stack |
| `make down` | `docker compose down` | Stop everything |
| `make db-init` | `docker compose run --rm seed` | Re-seed the database |
| `make db-shell` | `docker exec -it ... psql` | Open interactive SQL shell |
| `make simulator` | `docker compose run --rm simulator` | Run simulator once (manual) |
| `make ingest` | `uv run ingest` | Run dlt ELT pipeline (Postgres → DuckDB bronze) |
| `make dbt-debug` | `cd pipeline/dbt && uv run dbt debug` | Verify DuckDB connection + config |
| `make dbt-parse` | `cd pipeline/dbt && uv run dbt parse` | Re-render project; catch YAML/syntax errors |
| `make dbt-run` | `cd pipeline/dbt && uv run dbt run` | Build all models (staging → intermediate → marts) |
| `make dbt-test` | `cd pipeline/dbt && uv run dbt test` | Run all data tests |
| `make dbt-build` | `cd pipeline/dbt && uv run dbt build` | Full gate: models + snapshot + tests in order |
| `make dbt-snapshot` | `cd pipeline/dbt && uv run dbt snapshot` | Run SCD Type 2 snapshots only |
| `make dbt-docs` | `cd pipeline/dbt && uv run dbt docs ...` | Generate + serve lineage docs (localhost:8080) |
| `make prefect-server` | `prefect server start --host 0.0.0.0` | Start local Prefect server (localhost:4200) |
| `make prefect-flow` | `python orchestration/prefect/flows.py` | Run ELT flow once (manual trigger) |
| `make prefect-serve` | `python orchestration/prefect/flows.py --serve` | Serve as daily 07:00 deployment |
| `make prefect-pool` | `prefect work-pool create --type process elt-pool` | Create process work pool (one-time) |
| `make prefect-deploy` | `prefect deploy ... --name elt-daily --pool elt-pool` | Deploy flow to work pool |
| `make prefect-worker` | `prefect worker start --pool elt-pool` | Start worker that pulls from pool |

## Project structure

```
olist-ecommerce/
├── README.md
├── Makefile                  # short targets for common commands
├── pyproject.toml            # uv project + deps (main, dbt-duckdb, orchestration groups)
├── .env / .env.example       # DB credentials (gitignored)
├── ecommerce_db/             # OLTP: postgres + seed + simulator (dockerized)
│   ├── Dockerfile            # Python 3.12 + uv (shared by seed + simulator)
│   ├── docker-compose.yaml   # Postgres (healthcheck) + seed + simulator
│   ├── olist-dataset/        # 9 Olist CSVs (~121MB, gitignored)
│   └── src/ecommerce_db/     # package: config, seed.py, simulator.py, helpers/
├── pipeline/
│   ├── src/pipeline/         # ELT package (installed via uv/hatch)
│   │   ├── config.py         # pydantic-settings: Postgres / warehouse / pipeline
│   │   └── ingestion.py      # dlt: Postgres → DuckDB bronze (entry: `ingest`)
│   └── dbt/                  # transformations: silver + gold + tests
│       ├── dbt_project.yml   # per-layer materialization + schema config
│       ├── profiles.yml      # DuckDB connection (WAREHOUSE_LOCAL__PATH)
│       ├── models/           # staging/ → intermediate/ → marts/
│       ├── snapshots/        # orders snapshots (SCD Type 2)
│       └── tests/generic/    # custom generic tests
├── orchestration/
│   └── prefect/
│       └── flows.py          # elt_flow: ingest → dbt build (tasks, --serve)
├── data/warehouse/           # DuckDB ecommerce.duckdb (gitignored)
└── docs/
    ├── oltp-guide.md      # schema, seed, and simulator decisions
    ├── dlt-pipeline.md    # dlt pipeline architecture and decisions
    ├── dbt-guide.md       # dbt layers, schema strategy, tests, snapshots
    └── orchestration.md   # Prefect setup, Airflow mapping, WSL2 notes
```

## Phase status

- [x] **0. Foundations** — repo layout, deps (uv), Makefile
- [x] **1. OLTP + seed** — Postgres schema, triggers, COPY loader
- [x] **2. Simulator** — fake backend generating live data + anomalies
- [x] **3. ELT (dlt)** — incremental Postgres → DuckDB bronze
- [x] **4. dbt** — silver/gold star schema, SCD2 snapshots, 73 tests
- [x] **5. Orchestration** — Prefect flows (Airflow port later)
- [ ] **6. Serving** — dashboard + daily digest (decision gates)
- [ ] **7. Cloud (GCP)** — BigQuery, managed Postgres, IaC

## Design decisions

See [`docs/`](docs/) for detailed decision logs on schema, ELT, dbt, and orchestration choices.
