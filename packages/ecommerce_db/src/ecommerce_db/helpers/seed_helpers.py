import codecs
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

import psycopg
from botocore.client import BaseClient

# ── 1. COPY SPECS ──────────────────────────────────────────────────────────────
# Order matters: parents before children (FKs checked per-row).
# Geolocation skips geolocation_id (BIGSERIAL fills it automatically).
# Object keys are the flat CSV filenames in the olist-dataset bucket.


class CopySpec(NamedTuple):
    table: str
    object_key: str
    columns: str


COPY_SPECS = [
    CopySpec(
        table="customers",
        object_key="customers.csv",
        columns="customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state",
    ),
    CopySpec(
        table="sellers",
        object_key="sellers.csv",
        columns="seller_id, seller_zip_code_prefix, seller_city, seller_state",
    ),
    CopySpec(
        table="products",
        object_key="products.csv",
        columns="product_id, product_category_name, product_name_lenght, product_description_lenght, product_photos_qty, product_weight_g, product_length_cm, product_height_cm, product_width_cm",
    ),
    CopySpec(
        table="geolocation",
        object_key="geolocation.csv",
        columns="geolocation_zip_code_prefix, geolocation_lat, geolocation_lng, geolocation_city, geolocation_state",
    ),
    CopySpec(
        table="product_category_name_translation",
        object_key="product_category_name_translation.csv",
        columns="product_category_name, product_category_name_english",
    ),
    CopySpec(
        table="orders",
        object_key="orders.csv",
        columns="order_id, customer_id, order_status, order_purchase_timestamp, order_approved_at, order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date",
    ),
    CopySpec(
        table="order_items",
        object_key="order_items.csv",
        columns="order_id, order_item_id, product_id, seller_id, shipping_limit_date, price, freight_value",
    ),
    CopySpec(
        table="order_payments",
        object_key="order_payments.csv",
        columns="order_id, payment_sequential, payment_type, payment_installments, payment_value",
    ),
    CopySpec(
        table="reviews",
        object_key="reviews.csv",
        columns="review_id, order_id, review_score, review_comment_title, review_comment_message, review_creation_date, review_answer_timestamp",
    ),
]


# ── 2. TARGET COUNTS (CSV row counts, used by --verify) ────────────────────────

EXPECTED = {
    "customers": 99_441,
    "geolocation": 1_000_163,
    "order_items": 112_650,
    "order_payments": 103_886,
    "orders": 99_441,
    "product_category_name_translation": 71,
    "products": 32_951,
    "reviews": 99_224,
    "sellers": 3_095,
}


# ── 3. HELPERS ─────────────────────────────────────────────────────────────────


def load_schema(conn: psycopg.Connection) -> None:
    """Read schema.sql and execute it."""
    schema_path = Path(__file__).with_name("schema.sql")
    sql = schema_path.read_text()
    conn.execute(sql)


def iter_csv_text(
    s3: BaseClient, bucket: str, key: str, chunk_size: int = 8192
) -> Iterator[str]:
    """Stream one CSV object from S3 as decoded text.

    utf-8-sig strips the BOM that product_category_name_translation.csv
    starts with; the incremental decoder keeps multibyte chars intact
    across chunk boundaries.
    """
    body = s3.get_object(Bucket=bucket, Key=key)["Body"]
    decoder = codecs.getincrementaldecoder("utf-8-sig")()
    while chunk := body.read(chunk_size):
        yield decoder.decode(chunk)
    tail = decoder.decode(b"", final=True)
    if tail:
        yield tail


def copy_table(
    conn: psycopg.Connection,
    table: str,
    s3: BaseClient,
    bucket: str,
    key: str,
    columns: str,
) -> None:
    """COPY one S3 CSV object into a Postgres table using the fast COPY protocol."""
    sql = f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
    with conn.cursor() as cur, cur.copy(sql) as copy:
        for text in iter_csv_text(s3, bucket, key):
            copy.write(text)


def verify_counts(conn: psycopg.Connection) -> None:
    """Assert each table's row count matches the CSV target."""
    ok = True
    for table, expected in EXPECTED.items():
        count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        status = "✓" if count == expected else "✗"
        if count != expected:
            ok = False
        print(f"  {status} {table}: {count:,} (expected {expected:,})")
    if not ok:
        sys.exit(1)
