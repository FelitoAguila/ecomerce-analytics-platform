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
2. Extract the `olist-dataset` folder into `data/` so you get `data/olist-dataset/*.csv`

The 9 CSVs (~121MB total) are gitignored and not shipped with the repo.

## Quickstart

```bash
cp .env.example .env
docker compose up -d

# Seed loads historical data once → simulator starts generating live data
# Open a SQL shell to explore:
make db-shell

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
| `make dlt-pipeline` | `cd src/dlt_pipeline && uv run python dlt_pipeline.py` | Run dlt ELT pipeline |

## Project structure

```
olist-ecommerce/
├── README.md
├── Makefile               # short targets for common commands
├── Dockerfile             # Python 3.12 + uv + deps (shared by seed + simulator)
├── docker-compose.yaml    # Postgres + seed + simulator services
├── pyproject.toml         # uv project + deps
├── .env / .env.example    # DB credentials (gitignored)
├── data/olist-dataset/    # 9 Olist CSVs (~121MB, gitignored)
├── src/oltp/
│   ├── schema.sql         # 9 tables, PKs, FKs, updated_at triggers
│   ├── seed.py            # drop + create + COPY CSVs → Postgres
│   └── simulator.py       # fake backend: new orders + anomalies
├── src/dlt_pipeline/
│   ├── dlt_pipeline.py    # dlt ELT: Postgres → DuckDB (incremental)
│   └── .dlt/              # dlt config (empty secrets.toml, config.toml)
└── docs/
    ├── oltp-guide.md      # schema, seed, and simulator decisions
    └── dlt-pipeline.md    # dlt pipeline architecture and decisions
```

## Design decisions

See [`docs/`](docs/) for detailed decision logs on schema, ELT, dbt, and orchestration choices.
