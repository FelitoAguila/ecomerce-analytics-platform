from functools import lru_cache

from pydantic import BaseModel, PostgresDsn

from config.settings import BigQuery, ConfigBase


class PostgresDB(BaseModel):
    """Postgres Ecommerce OLTP Database"""

    dsn: PostgresDsn


class PipelineSettings(BaseModel):
    """Pipeline Settings"""

    name: str = "ecommerce_pipeline"
    dataset_name: str = "bronze_data"
    reconcile_name: str = "ecommerce_pipeline_reconcile"
    reconcile_dataset_name: str = "bronze_reconcile"


class Settings(ConfigBase):
    """Pipeline Settings"""

    postgres_db: PostgresDB
    pipeline: PipelineSettings = PipelineSettings()
    bigquery: BigQuery


@lru_cache
def get_settings() -> Settings:
    return Settings()
