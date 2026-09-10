import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PostgresDB(BaseModel):
    """Postgres Ecommerce OLTP Database"""

    dsn: PostgresDsn


class WarehouseLocal(BaseModel):
    """DuckDB Data Warehouse"""

    path: str = "data/warehouse/ecommerce.duckdb"

    @field_validator("path")
    @classmethod
    def _validate_warehouse_path(cls, v: str) -> str:
        if re.match(r"^[A-Za-z]:[\\/]", v) and os.name != "nt":
            raise ValueError(
                f"Windows-style path {v!r} is not valid on this platform; "
                "use an absolute path for the current OS"
            )
        path = Path(v).expanduser().resolve()
        if path.suffix != ".duckdb":
            raise ValueError(f"Warehouse path must end in .duckdb, got {v!r}")
        return str(path)


class PipelineSettings(BaseModel):
    """Pipeline Settings"""

    name: str = "ecommerce_pipeline"
    destination: Literal["duckdb", "bigquery"] = "duckdb"
    dataset_name: str = "ecommerce_data"


class DashboardSettings(BaseModel):
    """Dashboard read source.

    `source` selects the warehouse the dashboard reads from; `tables`
    provides fully-qualified gold table names so the dashboard can point
    at a different warehouse (local DuckDB vs BigQuery) purely via config,
    with no code changes.
    """

    source: Literal["duckdb", "bigquery"] = "duckdb"

    fct_orders: str = "main_mart.fct_orders"
    fct_order_payments: str = "main_mart.fct_order_payments"
    dim_products: str = "main_mart.dim_products"
    dim_sellers: str = "main_mart.dim_sellers"
    dim_customers: str = "main_mart.dim_customers"
    orders_snapshot: str = "main_snapshots.orders_snapshot"
    geolocation: str = "main_int.int_geolocation_aggregated"
    order_items: str = "main_int.int_order_items_enriched"


class Settings(BaseSettings):
    """ "Project Settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    postgres_db: PostgresDB
    pipeline: PipelineSettings = PipelineSettings()
    warehouse_local: WarehouseLocal = WarehouseLocal()
    dashboard: DashboardSettings = DashboardSettings()

@lru_cache
def get_settings() -> Settings:
    return Settings()
