"""
Seed the OLTP database: apply schema + COPY all 9 Olist CSVs.

Usage:
    python src/oltp/seed.py          # drop + recreate + load
    python src/oltp/seed.py --verify # run count checks after loading
"""

import sys
from pathlib import Path

import psycopg

from ecommerce_db.config import get_settings
from ecommerce_db.helpers.seed_helpers import (
    COPY_SPECS,
    copy_table,
    load_schema,
    verify_counts,
)


def main() -> None:
    """Seed the ecommerce OLTP database with the Olist dataset."""
    settings = get_settings()
    run_verify = "--verify" in sys.argv
    data_dir = Path(settings.postgres_db.data_dir)
    dsn = str(settings.postgres_db.dsn)

    with psycopg.connect(dsn) as conn:
        load_schema(conn)

        for table, csv_filename, columns in COPY_SPECS:
            csv_path = data_dir / csv_filename
            copy_table(conn, table, csv_path, columns)
            print(f"  loaded {table}")

        conn.commit()

    if run_verify:
        with psycopg.connect(dsn) as conn:
            verify_counts(conn)


if __name__ == "__main__":
    main()
