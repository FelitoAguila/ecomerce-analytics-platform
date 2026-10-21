import sys

import dlt
from dlt.sources.sql_database import sql_database
from google.oauth2 import service_account
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

SCOPES = ["https://www.googleapis.com/auth/bigquery"]


def main() -> None:
    settings = get_settings()

    engine = create_engine(
        make_url(str(settings.postgres_db.dsn)).set(drivername="postgresql+psycopg")
    )

    source = sql_database(credentials=engine).with_resources(*ALL_TABLES)

    for table in ALL_TABLES:
        getattr(source, table).apply_hints(
            incremental=dlt.sources.incremental("updated_at")
        )

    credentials = service_account.Credentials.from_service_account_file(
        settings.bigquery.keyfile, scopes=SCOPES
    )

    pipeline = dlt.pipeline(
        pipeline_name=settings.pipeline.name,
        destination=dlt.destinations.bigquery(
            credentials=credentials,
            location=settings.bigquery.location,
        ),
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
