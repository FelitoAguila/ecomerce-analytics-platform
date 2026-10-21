import sys
from pathlib import Path

import dlt
from dlt.sources.sql_database import sql_database
from sqlalchemy.engine import create_engine, make_url

from pipeline.config import get_settings

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


def main() -> None:
    settings = get_settings()

    warehouse_path = Path(settings.warehouse_local.path)
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        make_url(str(settings.postgres_db.dsn)).set(drivername="postgresql+psycopg")
    )

    source = sql_database(credentials=engine).with_resources(*ALL_TABLES)

    for table in ALL_TABLES:
        getattr(source, table).apply_hints(
            incremental=dlt.sources.incremental("updated_at")
        )

    pipeline = dlt.pipeline(
        pipeline_name=settings.pipeline.name,
        destination=dlt.destinations.duckdb(credentials=str(warehouse_path)),
        dataset_name=settings.pipeline.dataset_name,
    )

    info = pipeline.run(source)
    print(info)

    if info.has_failed_jobs:
        print("\n  WARNING: some jobs failed — see load info above.")
        sys.exit(1)

    print("\n  Load complete — all jobs succeeded.")


if __name__ == "__main__":
    main()
