from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.paths import workspace_root


class ConfigBase(BaseSettings):
    """Shared settings foundation: every service reads the same workspace .env.

    Subclasses inherit the loader (env_file=<workspace>/.env, nested '__'
    delimiter, extra='ignore') and only declare the fields they actually
    consume. The .env is resolved from the workspace root, not the CWD, so
    commands work from any package directory.
    """

    model_config = SettingsConfigDict(
        env_file=str(workspace_root() / ".env"),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


class BigQuery(BaseModel):
    """BigQuery Data Warehouse"""

    project: str
    location: str = "US"
    keyfile: str

    @field_validator("keyfile")
    @classmethod
    def _validate_keyfile(cls, v: str) -> str:
        path = Path(v).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Service account key file not found: {v!r}")
        return str(path)


class GoldTableRefs(BaseModel):
    """Fully-qualified gold table names the serving layer reads from.

    Shared vocabulary between the dashboard and reports: the same source
    flag and table identities select the active warehouse via config, with
    no code changes.
    """

    source: Literal["bigquery"] = "bigquery"

    fct_orders: str = "mart.fct_orders"
    fct_order_payments: str = "mart.fct_order_payments"
    dim_products: str = "mart.dim_products"
    dim_sellers: str = "mart.dim_sellers"
    dim_customers: str = "mart.dim_customers"
    orders_snapshot: str = "snapshots.orders_snapshot"
    geolocation: str = "int.int_geolocation_aggregated"
    order_items: str = "int.int_order_items_enriched"
