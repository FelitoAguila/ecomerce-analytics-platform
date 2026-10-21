FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY packages ./packages

# Orchestration (prefect) + the ELT package it triggers over subprocess, with
# dbt available so `uv run elt` works from inside the worker.
RUN uv sync --frozen --package olist-orchestration --package olist-pipeline --group dbt-bigquery
