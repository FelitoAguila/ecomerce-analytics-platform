from pathlib import Path

import pytest
from pydantic import ValidationError

from config.paths import workspace_root
from config.settings import BigQuery, ConfigBase, GoldTableRefs, PostgresDB


def test_workspace_root_points_to_repo():
    root = workspace_root()
    assert (root / "pyproject.toml").exists()


def test_postgres_dsn_valid():
    db = PostgresDB(dsn="postgresql://user:pass@host:5432/db")
    assert str(db.dsn).startswith("postgresql://")


def test_bigquery_default_location():
    bq2 = BigQuery.model_validate({"project": "p", "keyfile": __file__})
    assert bq2.location == "us-central1"


def test_bigquery_keyfile_validates_existence(tmp_path):
    key = tmp_path / "sa.json"
    key.write_text("{}")
    bq = BigQuery(project="p", keyfile=str(key))
    assert Path(bq.keyfile).is_file()


def test_bigquery_missing_keyfile_raises():
    with pytest.raises(ValidationError):
        BigQuery(project="p", keyfile="/definitely/missing/file.json")


def test_gold_table_refs_defaults():
    g = GoldTableRefs()
    assert g.source == "bigquery"
    assert g.fct_orders == "mart.fct_orders"
    assert g.orders_snapshot == "snapshots.orders_snapshot"
    assert g.order_items == "int.int_order_items_enriched"


def test_configbase_extra_ignored(tmp_path):
    class S(ConfigBase):
        postgres_db: PostgresDB

    env = tmp_path / ".env"
    env.write_text("UNKNOWN__FOO=bar\nPOSTGRES_DB__DSN=postgresql://u:p@h/db\n")
    s = S(_env_file=str(env), _env_file_encoding="utf-8")
    assert str(s.postgres_db.dsn).find("@h/") >= 0
