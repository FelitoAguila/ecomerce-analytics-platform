from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class EcommercePostgresDB(BaseModel):
    """Postgres Ecommerce OLTP Database"""

    dsn: PostgresDsn
    data_dir: str = "data/olist-dataset"


class WarehouseLocal(BaseModel):
    """DuckDB Data Warehouse"""

    path: str = "data/warehouse/ecommerce.duckdb"


class PipelineSettings(BaseModel):
    """Pipeline Settings"""

    name: str = "ecommerce_pipeline"
    destination: Literal["duckdb", "bigquery"] = "duckdb"
    dataset_name: str = "ecommerce_data"


class Settings(BaseSettings):
    """ "Project Settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="forbid",
    )

    ecommerce_db: EcommercePostgresDB
    pipeline: PipelineSettings = PipelineSettings()
    warehouse_local: WarehouseLocal = WarehouseLocal()

@lru_cache
def get_settings() -> Settings:
    return Settings()
