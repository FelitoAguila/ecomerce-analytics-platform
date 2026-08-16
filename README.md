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
cp .env.example .env    # edit with your Postgres credentials
make up                 # start Postgres in Docker
make db-init            # load the schema + all 9 CSVs
make db-shell           # open psql, explore the data, \q to exit
make down               # stop Postgres
```

One-liner to start fresh:

```bash
make up && make db-init
```

## Makefile targets

| Target | Command | Description |
|---|---|---|
| `make up` | `docker compose up -d` | Start Postgres in Docker |
| `make down` | `docker compose down` | Stop Postgres |
| `make db-init` | `uv run python src/oltp/seed.py` | Drop + recreate tables, load all 9 CSVs |
| `make db-shell` | `docker exec -it ... psql` | Open interactive SQL shell |

## Project structure

```
olist-ecommerce/
├── README.md
├── Makefile               # short targets for common commands
├── docker-compose.yaml    # Postgres 16 service
├── pyproject.toml         # uv project + deps
├── .env / .env.example    # DB credentials (gitignored)
├── data/olist-dataset/    # 9 Olist CSVs (~121MB, gitignored)
├── src/oltp/
│   ├── schema.sql         # 9 tables, PKs, FKs, updated_at triggers
│   └── seed.py            # drop + create + COPY CSVs → Postgres
└── docs/
    └── oltp-schema-decisions.md
```

## Design decisions

See [`docs/`](docs/) for detailed decision logs on schema, ELT, dbt, and orchestration choices.
