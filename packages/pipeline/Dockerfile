FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY packages ./packages

# dlt (bronze) + dbt (silver/gold/tests): this image is the ELT job, nothing more.
RUN uv sync --frozen --package olist-pipeline --group dbt-bigquery

ENTRYPOINT ["uv", "run", "--no-sync", "--package", "olist-pipeline", "elt"]
