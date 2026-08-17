"""
Simulator: generate realistic new e-commerce data on top of the seeded OLTP.

Simulates what a real backend would produce: new orders with status
transitions, items, payments, reviews — plus backdated rows and
anomalies that test data quality checks in later phases.

Usage:
    python src/oltp/simulator.py            # 50 orders (default)
    python src/oltp/simulator.py --orders 100
"""
import argparse
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# ── 1. CONFIG ──────────────────────────────────────────────────────────────────

ANOMALY_RATES = {
    "backdated": 0.05,
    "missing_score": 0.02,
    "outlier_price": 0.01,
    "bad_status": 0.01,
}

STATUS_WEIGHTS = {"delivered": 97.0, "shipped": 1.1, "canceled": 0.6,
                  "unavailable": 0.6, "invoiced": 0.3, "processing": 0.3}

ITEMS_PER_ORDER = {1: 90.1, 2: 7.6, 3: 1.3, 4: 0.5, 5: 0.5}

REVIEW_SCORES = {5: 57.8, 4: 19.3, 1: 11.5, 3: 8.2, 2: 3.2}

PAYMENT_TYPES = {"credit_card": 73.9, "boleto": 19.0, "voucher": 5.6,
                 "debit_card": 1.5}

CC_INSTALLMENTS = {1: 40, 2: 15, 3: 10, 4: 8, 5: 6, 6: 5,
                   7: 4, 8: 3, 9: 3, 10: 3, 11: 2, 12: 1}

REVIEW_RATE = 0.993

# ── 2. ENV ─────────────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

dsn = (
    f"postgresql://{Path(__file__).resolve().parent.parent.parent / '.env'}"
)

# Actually build from env vars
import os
dsn = (
    f"postgresql://{os.environ['POSTGRES_USER']}"
    f":{os.environ['POSTGRES_PASSWORD']}"
    f"@{os.environ['OLTP_HOST']}:{os.environ['OLTP_PORT']}"
    f"/{os.environ['POSTGRES_DB']}"
)

# ── 3. HELPERS ─────────────────────────────────────────────────────────────────

def weighted_choice(weights: dict):
    items = list(weights.keys())
    probs = [v / sum(weights.values()) for v in weights.values()]
    return random.choices(items, weights=probs, k=1)[0]


def gen_uuid() -> str:
    return uuid.uuid4().hex


def gen_price() -> float:
    return round(random.lognormvariate(4.3, 0.8), 2)


def gen_freight(price: float) -> float:
    return round(max(5.0, price * random.uniform(0.12, 0.28)), 2)


# ── 4. MAIN ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate new e-commerce data")
    parser.add_argument("--orders", type=int, default=50,
                        help="Number of new orders to generate (default: 50)")
    args = parser.parse_args()

    stats = {
        "new_orders": 0, "new_items": 0, "new_payments": 0,
        "new_reviews": 0, "status_updates": 0, "backdated": 0,
        "anom_missing_score": 0, "anom_outlier_price": 0,
        "anom_bad_status": 0,
    }

    with psycopg.connect(dsn) as conn:
        # ── Load reference IDs ─────────────────────────────────────────────
        customers = [r[0] for r in
                     conn.execute("SELECT customer_id FROM customers").fetchall()]
        products = [r[0] for r in
                    conn.execute("SELECT product_id FROM products").fetchall()]
        sellers = [r[0] for r in
                   conn.execute("SELECT seller_id FROM sellers").fetchall()]

        # ── Generate new orders ────────────────────────────────────────────
        new_orders = []
        for _ in range(args.orders):
            order_id = gen_uuid()
            customer_id = random.choice(customers)
            status = weighted_choice(STATUS_WEIGHTS)

            is_backdated = random.random() < ANOMALY_RATES["backdated"]
            if is_backdated:
                purchase_ts = datetime(2017, 1, 1) + timedelta(
                    days=random.randint(0, 730))
                stats["backdated"] += 1
            else:
                purchase_ts = datetime.now() - timedelta(
                    hours=random.randint(0, 48))

            approved_ts = purchase_ts + timedelta(minutes=random.randint(5, 120))
            estimated_delivery = purchase_ts + timedelta(
                days=random.randint(10, 30))

            carrier_ts = None
            delivered_ts = None
            if status == "delivered":
                carrier_ts = approved_ts + timedelta(days=random.randint(1, 5))
                delivered_ts = carrier_ts + timedelta(days=random.randint(1, 7))
            elif status == "shipped":
                carrier_ts = approved_ts + timedelta(days=random.randint(1, 5))

            new_orders.append({
                "order_id": order_id, "customer_id": customer_id,
                "status": status, "purchase_ts": purchase_ts,
                "approved_ts": approved_ts, "carrier_ts": carrier_ts,
                "delivered_ts": delivered_ts, "estimated_ts": estimated_delivery,
            })

        for o in new_orders:
            conn.execute("""
                INSERT INTO orders (order_id, customer_id, order_status,
                    order_purchase_timestamp, order_approved_at,
                    order_delivered_carrier_date, order_delivered_customer_date,
                    order_estimated_delivery_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (o["order_id"], o["customer_id"], o["status"],
                  o["purchase_ts"], o["approved_ts"], o["carrier_ts"],
                  o["delivered_ts"], o["estimated_ts"]))
        stats["new_orders"] = len(new_orders)

        # ── Generate items ─────────────────────────────────────────────────
        order_totals: dict[str, float] = {}
        for o in new_orders:
            n_items = int(weighted_choice(ITEMS_PER_ORDER))
            total = 0.0
            for item_idx in range(1, n_items + 1):
                product_id = random.choice(products)
                seller_id = random.choice(sellers)

                is_outlier = random.random() < ANOMALY_RATES["outlier_price"]
                if is_outlier:
                    price = round(random.uniform(5000, 6735), 2)
                    stats["anom_outlier_price"] += 1
                else:
                    price = gen_price()

                freight = gen_freight(price)
                shipping_limit = o["purchase_ts"] + timedelta(
                    days=random.randint(3, 10))

                conn.execute("""
                    INSERT INTO order_items (order_id, order_item_id, product_id,
                        seller_id, shipping_limit_date, price, freight_value)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (o["order_id"], item_idx, product_id, seller_id,
                      shipping_limit, price, freight))
                total += price + freight
                stats["new_items"] += 1
            order_totals[o["order_id"]] = total

        # ── Generate payments ──────────────────────────────────────────────
        for o in new_orders:
            n_payments = 1 if random.random() > 0.1 else 2
            total = order_totals[o["order_id"]]

            for pay_idx in range(1, n_payments + 1):
                pay_type = weighted_choice(PAYMENT_TYPES)
                if pay_type == "credit_card":
                    installments = int(weighted_choice(CC_INSTALLMENTS))
                else:
                    installments = 1

                pay_value = round(total / n_payments, 2)

                conn.execute("""
                    INSERT INTO order_payments (order_id, payment_sequential,
                        payment_type, payment_installments, payment_value)
                    VALUES (%s, %s, %s, %s, %s)
                """, (o["order_id"], pay_idx, pay_type, installments, pay_value))
                stats["new_payments"] += 1

        # ── Generate reviews ───────────────────────────────────────────────
        for o in new_orders:
            if o["status"] != "delivered" or random.random() > REVIEW_RATE:
                continue

            review_id = gen_uuid()
            if random.random() < ANOMALY_RATES["missing_score"]:
                score = None
                stats["anom_missing_score"] += 1
            else:
                score = int(weighted_choice(REVIEW_SCORES))

            creation_date = o["delivered_ts"] + timedelta(
                days=random.randint(1, 30))
            answer_date = creation_date + timedelta(days=random.randint(0, 7))

            conn.execute("""
                INSERT INTO reviews (review_id, order_id, review_score,
                    review_comment_title, review_comment_message,
                    review_creation_date, review_answer_timestamp)
                VALUES (%s, %s, %s, NULL, NULL, %s, %s)
            """, (review_id, o["order_id"], score, creation_date, answer_date))
            stats["new_reviews"] += 1

        # ── Status transitions on existing orders ──────────────────────────
        shipped = conn.execute("""
            SELECT order_id FROM orders
            WHERE order_status = 'shipped'
            ORDER BY RANDOM() LIMIT 5
        """).fetchall()

        for (order_id,) in shipped:
            if random.random() < ANOMALY_RATES["bad_status"]:
                new_status = "created"
                stats["anom_bad_status"] += 1
            else:
                new_status = "delivered"

            delivered_ts = datetime.now() - timedelta(hours=random.randint(1, 24))
            conn.execute("""
                UPDATE orders SET order_status = %s,
                    order_delivered_customer_date = %s
                WHERE order_id = %s
            """, (new_status, delivered_ts, order_id))
            stats["status_updates"] += 1

        conn.commit()

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n  Simulator run complete:")
    print(f"  {'─' * 40}")
    print(f"  New orders:      {stats['new_orders']}")
    print(f"  New items:       {stats['new_items']}")
    print(f"  New payments:    {stats['new_payments']}")
    print(f"  New reviews:     {stats['new_reviews']}")
    print(f"  Status updates:  {stats['status_updates']}")
    print(f"  {'─' * 40}")
    print(f"  Anomalies:")
    print(f"    Backdated orders:    {stats['backdated']}")
    print(f"    Missing review score:{stats['anom_missing_score']}")
    print(f"    Outlier prices:      {stats['anom_outlier_price']}")
    print(f"    Bad status transition:{stats['anom_bad_status']}")


if __name__ == "__main__":
    main()
