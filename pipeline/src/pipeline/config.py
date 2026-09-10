from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, PostgresDsn

from config.settings import ConfigBase, WarehouseLocal


class PostgresDB(BaseModel):
    """Postgres Ecommerce OLTP Database"""

    dsn: PostgresDsn


class PipelineSettings(BaseModel):
    """Pipeline Settings"""

    name: str = "ecommerce_pipeline"
    destination: Literal["duckdb", "bigquery"] = "duckdb"
    dataset_name: str = "ecommerce_data"


class Settings(ConfigBase):
    """Pipeline Settings"""

    postgres_db: PostgresDB
    pipeline: PipelineSettings = PipelineSettings()
    warehouse_local: WarehouseLocal = WarehouseLocal()


@lru_cache
def get_settings() -> Settings:
    return Settings()