# OLTP Guide

Everything about the Postgres OLTP layer: schema design, seeding, and live simulation.

---

## 1. Schema (`src/oltp/schema.sql`)

### Table names

Source CSV filenames are used as table names (`customers`, `geolocation`, `product_category_name_translation`). This keeps the mapping transparent: anyone can trace a table back to its origin file with zero guessing. Plural/singular is mixed in the source (it is what it is).

### Types

| Decision | Why |
|---|---|
| All text → `TEXT` | In Postgres, `TEXT` and `VARCHAR(n)` perform identically (same internal storage). `TEXT` is simpler and idiomatic in Postgres. |
| `CHAR(2)` for state codes | States are exactly 2 letters (SP, RJ, MG, …). A fixed-length type signals "this field always has the same length" and lets the DB enforce it. |
| `VARCHAR(20)` for statuses/payment types | Short enumerated values with a predictable ceiling. The explicit length is documentation, not a hard limit (Postgres pads to the right, doesn't truncate). |
| `INTEGER` vs `SMALLINT` | `SMALLINT` for review_score (1–5, tiny range) — a minor space savings that also reads as "this is a small number." |
| `DOUBLE PRECISION` for lat/lng | Float is fine for coordinates — precision error is negligible at city level. Money is the only place where rounding bites, and here we don't touch money. |
| `NUMERIC(10,2)` for price/freight/payment | Exact decimal arithmetic. `FLOAT` would introduce rounding errors on money (e.g. 0.1 + 0.2 ≠ 0.3). `NUMERIC` is what banks use. |
| `TIMESTAMP` (without timezone) | The Olist CSVs store Brazilian local times with no timezone info. `TIMESTAMP` preserves the literal values as-is. `TIMESTAMPTZ` would interpret them under the server's timezone and silently shift every value. We normalize to UTC in silver (Phase 4). |
| `BIGSERIAL` for geolocation surrogate PK | Auto-increment integer. Needed because `geolocation` has duplicate zip codes (no natural key exists). |

### Nullable columns

| Column | Why nullable |
|---|---|
| `products.product_category_name` | 610 products have no category in the source data. Making it `NOT NULL` would reject valid rows. |
| `orders.order_approved_at` | 160 orders are not yet approved (status `created`). |
| All delivery timestamps on `orders` | An order may not have shipped or arrived yet. |
| `reviews.review_comment_title` / `review_comment_message` | Many reviews leave the title empty. |
| `reviews.review_creation_date` / `review_answer_timestamp` | Some reviews are incomplete. |

Everything else is `NOT NULL` — every customer has a state, every item has a price, etc. A `NOT NULL` constraint catches broken ETL/imports before they silently propagate.

### Primary keys

| Table | PK | Why |
|---|---|---|
| `customers` | `customer_id` | UUID assigned per order (Olist convention). |
| `sellers` | `seller_id` | Stable seller identifier. |
| `products` | `product_id` | SHA-256-ish product hash. |
| `orders` | `order_id` | UUID per order. |
| `order_items` | `(order_id, order_item_id)` | Composite — an item is identified by *which order* it belongs to *and* its position within it. |
| `order_payments` | `(order_id, payment_sequential)` | Same logic: a payment is scoped to an order. |
| `reviews` | `(review_id, order_id)` | Composite — the same `review_id` can appear with different `order_id`s (789 duplicates in the source). The pair is always unique. |
| `product_category_name_translation` | `product_category_name` | The Portuguese category name is unique and is the join key. |
| `geolocation` | `geolocation_id` (surrogate) | Duplicate zip prefixes make a natural key impossible. A synthetic id gives a clean PK and future join key. |

### Foreign keys

| FK | What it enforces |
|---|---|
| `orders.customer_id → customers.customer_id` | An order must belong to an existing customer. |
| `order_items.order_id → orders.order_id` | An item must belong to an existing order. |
| `order_items.product_id → products.product_id` | An item must reference a real product. |
| `order_items.seller_id → sellers.seller_id` | An item must reference a real seller. |
| `order_payments.order_id → orders.order_id` | A payment must belong to an existing order. |
| `reviews.order_id → orders.order_id` | A review must belong to an existing order. |

**Deliberately absent:** `products.product_category_name → product_category_name_translation.product_category_name`. The source data has 73 distinct categories in `products` but the translation table only has 71. Two categories (`pc_gamer`, `portateis_cozinha_e_preparadores_de_alimentos`) are missing from the translation. A strict FK would reject those rows on load. The join lives in silver (Phase 4) where we handle the gap.

### reviews composite PK

The source CSV contains 789 duplicate `review_id` values (up to 3 copies each, 98,410 distinct out of 99,224 rows). However, every duplicate has a **different `order_id`** — the same review content appears across multiple orders (a data collection artifact). So `(review_id, order_id)` is always unique, and works as a composite PK. This matches the pattern used by `order_items` and `order_payments`: a row is scoped to its parent order.

### CHECK constraint on review_score

`CHECK (review_score BETWEEN 1 AND 5)` on `reviews.review_score` rejects out-of-range integers at the database level. NULLs still pass (Postgres treats NULLs as passing all CHECKs by default), which is correct: a missing score is not the same as an invalid one.

### updated_at + trigger

`DEFAULT NOW()` on every table stamps the insert time. The `BEFORE UPDATE` trigger stamps every subsequent change. Together they guarantee the column always reflects reality — and that's what Phase 3's incremental watermark reads.

Why on all 9 tables and not just the ones the simulator mutates? Uniformity. Every table follows the same rule, bronze loads identically for all, and no one has to remember which tables are "special."

---

## 2. Seeding (`src/oltp/seed.py`)

### How it works

`seed.py` connects to Postgres, executes `schema.sql` (drop + recreate all tables), then uses the Postgres `COPY` protocol to bulk-load each CSV. The COPY protocol streams data at wire speed — much faster than per-row INSERT.

### BOM handling

`product_category_name_translation.csv` starts with a UTF-8 BOM (byte order mark). Postgres COPY with `HEADER TRUE` reads the header line positionally, but a BOM prepended to the first column name causes a mismatch. Opening with `encoding='utf-8-sig'` tells Python to strip the BOM before COPY sees it.

### Copy order

`COPY` checks FKs per-row, so parents must exist before children:

1. `customers`, `sellers`, `products` (no FK dependencies)
2. `orders` (depends on `customers`)
3. `order_items`, `order_payments`, `reviews` (depend on `orders` + `products` + `sellers`)
4. `geolocation`, `product_category_name_translation` (no FK deps, any order)

### Idempotency

`DROP TABLE IF EXISTS` (children first) + `CREATE TABLE` makes `schema.sql` safe to run any number of times. Each run wipes and rebuilds cleanly — no "already exists" errors, no orphan data from a previous partial run.

### psycopg3 API

psycopg3 (the `psycopg` package) is **not** psycopg2. The COPY method is `cursor.copy(sql)` (a context manager with `.write()`), not `cursor.copy_expert(sql, file)`. The latter is psycopg2-only.

### Verification

`--verify` flag asserts each table's row count matches the CSV target. Exit code 1 on mismatch.

---

## 3. Simulator (`src/oltp/simulator.py`)

### What it does

Simulates a live e-commerce backend producing new data on top of the seeded historical dataset. Generates new orders, items, payments, reviews, status transitions — plus backdated rows and anomalies.

### Distributions (from historical data)

| Dimension | Distribution |
|---|---|
| Order status | 97% delivered, 1.1% shipped, 0.6% canceled, 0.6% unavailable, 0.3% invoiced, 0.3% processing |
| Items per order | 90% single item, 7.6% two, 1.3% three, 0.5% four, 0.5% five |
| Review scores | 58% five-star, 19% four-star, 12% one-star, 8% three-star, 3% two-star |
| Payment types | 74% credit card, 19% boleto, 6% voucher, 1.5% debit card |
| Review rate | 99.3% of delivered orders get a review |
| Prices | Log-normal around R$75 median, right-skewed to R$6,735 max |

### Anomaly rates

| Anomaly | Rate | What it produces |
|---|---|---|
| Backdated orders | 5% | Purchase timestamps from 2017–2018 instead of current date |
| Missing review score | 2% | `review_score` is NULL instead of 1–5 |
| Outlier prices | 1% | Item price between R$5,000 and R$6,735 |
| Bad status transition | 1% | Existing order status goes backwards (e.g., shipped → created) |

### Status transitions

The simulator also advances 5 existing orders from `shipped` to `delivered` per run. This generates UPDATE rows that fire the `updated_at` trigger — useful for testing the incremental watermark in Phase 3.

### Usage

```bash
make simulator              # 50 orders (default)
uv run python src/oltp/simulator.py --orders 100
```

### Summary output

After each run, the script prints counts of new orders, items, payments, reviews, status updates, and anomalies.

---

*Last updated: Phase 2 (simulator)*
