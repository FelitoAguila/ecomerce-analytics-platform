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


class Settings(ConfigBase):
    """Pipeline Settings"""

    postgres_db: PostgresDB
    pipeline: PipelineSettings = PipelineSettings()
    bigquery: BigQuery


@lru_cache
def get_settings() -> Settings:
    return Settings()
