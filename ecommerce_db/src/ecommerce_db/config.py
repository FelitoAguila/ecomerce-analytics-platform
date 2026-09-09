from functools import lru_cache

from pydantic import BaseModel, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class PostgresDB(BaseModel):
    """ Seed Ecommerce Postgres DB """

    dsn: PostgresDsn
    data_dir: str = "ecommerce_db/olist-dataset"


class Settings(BaseSettings):
    """ Project Settings """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    postgres_db: PostgresDB 


@lru_cache
def get_settings() -> Settings:
    return Settings()
