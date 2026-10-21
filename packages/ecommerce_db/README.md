# ecommerce_db

Sets up the OLTP Postgres database: applies the schema and bulk-loads the Olist
dataset, then simulates a live backend producing new orders, payments, and
reviews on top of it.

This README covers the **one-time operational setup** (Neon account, object
storage bucket, dataset upload, credentials). For the schema design, seeding
internals, and simulator behavior, see [`docs/oltp-guide.md`](../../docs/oltp-guide.md).

---

## 1. Prerequisites

- A [Neon](https://neon.tech) account.
- A Neon **Postgres project** (this holds the OLTP tables).
- A Neon **Object Storage** bucket (S3-compatible) to hold the CSVs.

> Object Storage is a **separate Neon product** from the Postgres compute. The
> database and the dataset live in two different places; the seed script reads
> the CSVs from object storage and writes them into Postgres.

## 2. Get the dataset

The Olist public dataset is a ~121 MB zip containing a top-level
`olist-dataset/` folder with 9 CSVs. It is widely mirrored; any of these work:

- [Google Drive](https://drive.google.com/file/d/1HIy4LNNQESuXUj-u_mNJTCGCRrCeSbo-/view)
  (the link used in this project)
- The original Olist publication and common mirrors (Kaggle, Hugging Face).

Download the zip and unzip it locally — you should end up with an
`olist-dataset/` folder holding the 9 CSVs.

## 3. Create the bucket and upload the dataset

1. In the Neon console, create an Object Storage bucket named **`olist-dataset`**
   (this matches the `OBJECT_STORAGE__BUCKET` default; only override it if you
   pick a different name).
2. Upload the 9 CSVs so they land as **flat keys** — at the bucket root, using
   their filenames as keys. Do **not** nest them under an `olist-dataset/`
   prefix: `COPY_SPECS` looks up each CSV by its bare filename.

Expected bucket layout:

```
olist-dataset/
├── customers.csv
├── geolocation.csv
├── order_items.csv
├── order_payments.csv
├── orders.csv
├── product_category_name_translation.csv
├── products.csv
├── reviews.csv
└── sellers.csv
```

## 4. Configure credentials

Neon Object Storage exposes an S3-compatible API. From its console, copy the
endpoint, region, access key, and secret key into your `.env` (nested under the
`OBJECT_STORAGE__` prefix, matching the house convention):

```dotenv
POSTGRES_DB__DSN=postgresql://<user>:<password>@<host>/<database>

OBJECT_STORAGE__AWS_ENDPOINT_URL_S3=https://<region>.storage.<cloud>.aws.neon.tech
OBJECT_STORAGE__AWS_ACCESS_KEY_ID=<your-access-key-id>
OBJECT_STORAGE__AWS_SECRET_ACCESS_KEY=<your-secret-access-key>
OBJECT_STORAGE__AWS_REGION=<your-region>
# Optional — defaults to olist-dataset
# OBJECT_STORAGE__BUCKET=olist-dataset
```

`OBJECT_STORAGE__AWS_ENDPOINT_URL_S3` and `OBJECT_STORAGE__AWS_REGION` come from
the object-storage endpoint shown in the Neon console; the access/secret keys
are the S3 credentials it generates. Never commit `.env`.

## 5. Seed and verify

Run seed once to create the schema and bulk-load the dataset:

```bash
uv run --package olist-ecommerce-database seed --verify
```

`--verify` is the **acceptance test**: after loading, it asserts each table's
row count matches the known CSV totals (see `EXPECTED` in
`helpers/seed_helpers.py`). Exit code `1` means a mismatch.

## 6. Simulate live data (optional)

With the database seeded, generate new data on top of it:

```bash
uv run --package olist-ecommerce-database simulate                 # one batch of 50 orders
uv run --package olist-ecommerce-database simulate --orders 100
uv run --package olist-ecommerce-database simulate --continuous    # keep generating
```

---

## Running in Docker

Both steps can run as isolated containers against Neon — no local Postgres.
`seed` is a one-shot job; `simulate` runs continuously (100 orders every 20s).

All commands run **from the repo root**, and `--env-file .env` is required so
Compose can interpolate `${...}` from the repo-root `.env` (Compose looks in the
compose project directory, not here). You can also use the root `Makefile`
targets (`make seed`, `make simulate`) as shorthand.

### Build the image

One image serves both services; build it once.

```bash
docker compose -f packages/ecommerce_db/docker-compose.yaml --env-file .env build
```

### Seed (one-shot)

```bash
docker compose -f packages/ecommerce_db/docker-compose.yaml --env-file .env run --rm seed
```

Prints per-table `loaded …` lines, then the `--verify` count table. Exit code
`1` means a row-count mismatch, `2` means a bad CLI flag.

### Simulate (continuous)

```bash
docker compose -f packages/ecommerce_db/docker-compose.yaml --env-file .env up -d simulate
docker compose -f packages/ecommerce_db/docker-compose.yaml --env-file .env logs -f simulate
docker compose -f packages/ecommerce_db/docker-compose.yaml --env-file .env stop simulate
```

### Start both at once

```bash
docker compose -f packages/ecommerce_db/docker-compose.yaml --env-file .env up -d   # seed runs once; simulate stays up
docker compose -f packages/ecommerce_db/docker-compose.yaml --env-file .env logs -f
```

### Override flags per run

Anything after the service name **replaces** the service's `command`:

```bash
# one batch of 50, no continuous
docker compose -f packages/ecommerce_db/docker-compose.yaml --env-file .env run --rm simulate \
  uv run --no-sync --package olist-ecommerce-database simulate --orders 50

# seed without --verify
docker compose -f packages/ecommerce_db/docker-compose.yaml --env-file .env run --rm seed \
  uv run --no-sync --package olist-ecommerce-database seed
```

### Debug

| Task | Command |
|---|---|
| Validate compose config | `docker compose -f packages/ecommerce_db/docker-compose.yaml --env-file .env config` |
| List resources | `docker compose -f packages/ecommerce_db/docker-compose.yaml --env-file .env ps` |
| Shell into the image | `docker compose -f packages/ecommerce_db/docker-compose.yaml --env-file .env run --rm seed bash` |
| Confirm the injected DSN | `docker compose -f packages/ecommerce_db/docker-compose.yaml --env-file .env run --rm seed env \| grep POSTGRES_DB` |

> `localhost` inside a container refers to the container itself, so the DSN must
> be the external Neon host. Rebuild the image after code changes — it bakes the
> code in.
