"""
ELT pipeline: extract from Postgres OLTP → load into DuckDB (bronze layer).

Uses dlt's sql_database source with incremental loading on `updated_at`.
First run loads all rows; subsequent runs only fetch new/changed rows.

Usage:
    uv run python src/dlt_pipeline/dlt_pipeline.py
    make dlt-pipeline
"""
import os
import sys
from pathlib import Path

import dlt
from dotenv import load_dotenv
from dlt.sources.sql_database import sql_database

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

ALL_TABLES = [
    "customers",
    "geolocation",
    "order_items",
    "order_payments",
    "orders",
    "product_category_name_translation",
    "products",
    "reviews",
    "sellers",
]


def load_ecommerce_data() -> None:
    dsn = (
        f"postgresql+pg8000://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('OLTP_HOST')}:{os.getenv('OLTP_PORT')}/{os.getenv('POSTGRES_DB')}"
    )
    source = sql_database(credentials=dsn).with_resources(*ALL_TABLES)

    for name in ALL_TABLES:
        getattr(source, name).apply_hints(
            incremental=dlt.sources.incremental("updated_at")
        )

    pipeline = dlt.pipeline(
        pipeline_name="load_ecommerce_data",
        destination="duckdb",
        dataset_name="ecommerce_data",
    )

    try:
        load_info = pipeline.run(source)
    except Exception as e:
        print(f"\n  Pipeline failed: {e}")
        sys.exit(1)

    print(load_info)

    if load_info.has_failed_jobs:
        print("\n  WARNING: some jobs failed. Check load_info above.")
        sys.exit(1)

    print("\n  Load complete — all jobs succeeded.")


if __name__ == "__main__":
    load_ecommerce_data()
