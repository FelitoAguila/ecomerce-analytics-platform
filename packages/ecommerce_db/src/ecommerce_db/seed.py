"""
Seed the OLTP database: apply schema + COPY all 9 Olist CSVs from Neon Object Storage.

Usage:
    uv run --package olist-ecommerce-database seed           # drop + recreate + load
    uv run --package olist-ecommerce-database seed --verify  # run count checks after loading
"""

import argparse

import psycopg

from ecommerce_db.config import get_settings
from ecommerce_db.helpers.seed_helpers import (
    COPY_SPECS,
    copy_table,
    load_schema,
    verify_counts,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the seed command-line parser."""
    parser = argparse.ArgumentParser(
        description="Seed the ecommerce OLTP database with the Olist dataset.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run row-count checks after loading (exit 1 on mismatch).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Seed the ecommerce OLTP database with the Olist dataset."""
    args = build_parser().parse_args(argv)

    settings = get_settings()
    s3 = settings.object_storage.s3_client()
    bucket = settings.object_storage.bucket
    dsn = str(settings.postgres_db.dsn)

    with psycopg.connect(dsn) as conn:
        load_schema(conn)

        for spec in COPY_SPECS:
            copy_table(conn, spec.table, s3, bucket, spec.object_key, spec.columns)
            print(f"  loaded {spec.table}")

        conn.commit()

    if args.verify:
        with psycopg.connect(dsn) as conn:
            verify_counts(conn)


if __name__ == "__main__":
    main()
