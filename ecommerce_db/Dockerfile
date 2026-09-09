FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY README.md pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-default-groups

COPY pipeline/src/pipeline ./pipeline/src/pipeline
COPY ecommerce_db/src/ecommerce_db ./ecommerce_db/src/ecommerce_db
RUN uv sync --frozen --no-default-groups

CMD ["uv", "run", "--no-sync", "seed"]