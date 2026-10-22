import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import dlt
from dlt.common.configuration.specs import GcpServiceAccountCredentials
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

PRIMARY_KEYS: dict[str, str | tuple[str, ...]] = {
    "customers": "customer_id",
    "geolocation": "geolocation_id",
    "order_items": ("order_id", "order_item_id"),
    "order_payments": ("order_id", "payment_sequential"),
    "orders": "order_id",
    "product_category_name_translation": "product_category_name",
    "products": "product_id",
    "reviews": ("review_id", "order_id"),
    "sellers": "seller_id",
}

RECONCILE_WRITE_DISPOSITION = {"disposition": "merge", "strategy": "upsert"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load Olist tables from Postgres into BigQuery bronze (dlt)."
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help=(
            "Reconciliation run: re-read a bounded window into the separate "
            "reconcile dataset without moving the incremental watermark."
        ),
    )
    parser.add_argument(
        "--since",
        type=datetime.fromisoformat,
        help="Reconciliation lower bound (ISO-8601). Required with --backfill.",
    )
    parser.add_argument(
        "--until",
        type=datetime.fromisoformat,
        help="Reconciliation upper bound (ISO-8601). Defaults to now.",
    )
    return parser


def to_naive_utc(value: datetime) -> datetime:
    """Cursor values are naive TIMESTAMPs in UTC, so bounds must be naive UTC too."""
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def build_source(backfill: bool, since: datetime | None, until: datetime | None):
    settings = get_settings()

    engine = create_engine(
        make_url(str(settings.postgres_db.dsn)).set(drivername="postgresql+psycopg")
    )

    source = sql_database(credentials=engine).with_resources(*ALL_TABLES)

    for table in ALL_TABLES:
        primary_key = PRIMARY_KEYS[table]
        resource = getattr(source, table)

        if backfill:
            resource.apply_hints(
                primary_key=primary_key,
                incremental=dlt.sources.incremental(
                    "updated_at",
                    primary_key=primary_key,
                    initial_value=since,
                    end_value=until,
                ),
            )
        else:
            resource.apply_hints(
                incremental=dlt.sources.incremental(
                    "updated_at",
                    primary_key=primary_key,
                    range_start="open",
                )
            )

    return source


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.since is not None and not args.backfill:
        parser.error("--since requires --backfill")
    if args.until is not None and not args.backfill:
        parser.error("--until requires --backfill")

    settings = get_settings()

    since: datetime | None = None
    until: datetime | None = None
    if args.backfill:
        if args.since is None:
            parser.error("--backfill requires --since")
        since = to_naive_utc(args.since)
        until = (
            to_naive_utc(args.until)
            if args.until is not None
            else datetime.now(UTC).replace(tzinfo=None)
        )
        if until < since:
            parser.error("--until must not be earlier than --since")

    source = build_source(args.backfill, since, until)

    credentials = GcpServiceAccountCredentials()
    credentials.parse_native_representation(Path(settings.bigquery.keyfile).read_text())

    if args.backfill:
        pipeline = dlt.pipeline(
            pipeline_name=settings.pipeline.reconcile_name,
            destination=dlt.destinations.bigquery(
                credentials=credentials,
                location=settings.bigquery.location,
            ),
            dataset_name=settings.pipeline.reconcile_dataset_name,
        )
        info = pipeline.run(source, write_disposition=RECONCILE_WRITE_DISPOSITION)
    else:
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
