FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY README.md pyproject.toml uv.lock ./
COPY pipeline/src/pipeline ./pipeline/src/pipeline
COPY ecommerce_db/src/ecommerce_db ./ecommerce_db/src/ecommerce_db

RUN uv sync --frozen --group dbt-duckdb --group orchestration