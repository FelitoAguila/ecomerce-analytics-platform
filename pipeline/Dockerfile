FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY README.md pyproject.toml uv.lock ./
COPY config ./config
COPY pipeline/src/pipeline ./pipeline/src/pipeline
COPY pipeline/dbt ./pipeline/dbt
COPY dashboard ./dashboard
COPY ecommerce_db/src/ecommerce_db ./ecommerce_db/src/ecommerce_db

# Main + dbt-duckdb groups: dlt (bronze) and dbt (silver/gold/tests). No dev/
# orchestration/dashboard groups — this image is the ELT job, nothing more.
RUN uv sync --frozen --group dbt-duckdb

ENTRYPOINT ["uv", "run", "--no-sync", "elt"]