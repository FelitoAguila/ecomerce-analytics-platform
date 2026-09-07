from functools import lru_cache

from pydantic import BaseModel, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

class EcommercePostgresDB(BaseModel):
    """Postgres Ecommerce OLTP Database"""
    dsn: PostgresDsn
    data_dir: str = "data/olist-dataset"

class Settings(BaseSettings):
    """"Project Settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="forbid",
    )

    ecommerce_db: EcommercePostgresDB

@lru_cache
def get_settings() -> Settings:
    return Settings()

