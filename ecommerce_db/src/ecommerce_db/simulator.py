"""
Simulator: generate realistic new e-commerce data on top of the seeded OLTP.

Simulates what a real backend would produce: new orders with status
transitions, items, payments, reviews — plus backdated rows and
anomalies that test data quality checks in later phases.

Usage:
    python src/olist/oltp/simulator.py              # 50 orders (default)
    python src/olist/oltp/simulator.py --orders 100
    python src/olist/oltp/simulator.py --continuous --interval 30
"""

import argparse
import time

import psycopg

from ecommerce_db.config import get_settings
from ecommerce_db.helpers.simulator_helpers import run_batch


def print_summary(stats: dict[str, int]) -> None:
    print("\n  Simulator run complete:")
    print(f"  {'─' * 40}")
    print(f"  New orders:      {stats['new_orders']}")
    print(f"  New items:       {stats['new_items']}")
    print(f"  New payments:    {stats['new_payments']}")
    print(f"  New reviews:     {stats['new_reviews']}")
    print(f"  Status updates:  {stats['status_updates']}")
    print(f"  {'─' * 40}")
    print("  Anomalies:")
    print(f"    Backdated orders:    {stats['backdated']}")
    print(f"    Missing review score:{stats['anom_missing_score']}")
    print(f"    Outlier prices:      {stats['anom_outlier_price']}")
    print(f"    Bad status transition:{stats['anom_bad_status']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate new e-commerce data")
    parser.add_argument(
        "--orders",
        type=int,
        default=50,
        help="Number of new orders to generate (default: 50)",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run forever, generating batches at each interval",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Seconds between batches in continuous mode (default: 30)",
    )
    args = parser.parse_args()

    settings = get_settings()
    dsn = str(settings.postgres_db.dsn)

    while True:
        with psycopg.connect(dsn) as conn:
            stats = run_batch(args, conn)
            conn.commit()

        print_summary(stats)

        if not args.continuous:
            break

        print(f"\n  Next batch in {args.interval}s...")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
