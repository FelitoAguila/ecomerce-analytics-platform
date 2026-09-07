import sys
from pathlib import Path

import psycopg

# ── 1. COPY SPECS ──────────────────────────────────────────────────────────────
# Order matters: parents before children (FKs checked per-row).
# Geolocation skips geolocation_id (BIGSERIAL fills it automatically).

COPY_SPECS = [
    (
        "customers",
        "customers.csv",
        "customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state",
    ),
    (
        "sellers",
        "sellers.csv",
        "seller_id, seller_zip_code_prefix, seller_city, seller_state",
    ),
    (
        "products",
        "products.csv",
        "product_id, product_category_name, product_name_lenght, product_description_lenght, product_photos_qty, product_weight_g, product_length_cm, product_height_cm, product_width_cm",
    ),
    (
        "geolocation",
        "geolocation.csv",
        "geolocation_zip_code_prefix, geolocation_lat, geolocation_lng, geolocation_city, geolocation_state",
    ),
    (
        "product_category_name_translation",
        "product_category_name_translation.csv",
        "product_category_name, product_category_name_english",
    ),
    (
        "orders",
        "orders.csv",
        "order_id, customer_id, order_status, order_purchase_timestamp, order_approved_at, order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date",
    ),
    (
        "order_items",
        "order_items.csv",
        "order_id, order_item_id, product_id, seller_id, shipping_limit_date, price, freight_value",
    ),
    (
        "order_payments",
        "order_payments.csv",
        "order_id, payment_sequential, payment_type, payment_installments, payment_value",
    ),
    (
        "reviews",
        "reviews.csv",
        "review_id, order_id, review_score, review_comment_title, review_comment_message, review_creation_date, review_answer_timestamp",
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


def copy_table(
    conn: psycopg.Connection, table: str, csv_path: Path, columns: str
) -> None:
    """COPY one CSV into a Postgres table using the fast COPY protocol."""
    sql = f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
    with open(csv_path, encoding="utf-8-sig") as f, conn.cursor() as cur:
        with cur.copy(sql) as copy:
            while chunk := f.read(8192):
                copy.write(chunk)


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
