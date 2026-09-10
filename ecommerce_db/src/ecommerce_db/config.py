from functools import lru_cache

from pydantic import BaseModel, PostgresDsn

from config.settings import ConfigBase


class PostgresDB(BaseModel):
    """Seed Ecommerce Postgres DB"""

    dsn: PostgresDsn
    data_dir: str = "ecommerce_db/olist-dataset"


class Settings(ConfigBase):
    """Seed Ecommerce Postgres DB"""

    postgres_db: PostgresDB


@lru_cache
def get_settings() -> Settings:
    return Settings()