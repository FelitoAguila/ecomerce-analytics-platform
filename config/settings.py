import os
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigBase(BaseSettings):
    """Shared settings foundation: every service reads the same root .env.

    Subclasses inherit the loader (env_file='.env', nested '__' delimiter,
    extra='ignore') and only declare the fields they actually consume.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


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


class GoldTableRefs(BaseModel):
    """Fully-qualified gold table names the serving layer reads from.

    Shared vocabulary between the dashboard and reports: the same source
    flag and table identities select local DuckDB vs BigQuery via config,
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