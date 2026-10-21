from functools import lru_cache

from config.settings import BigQuery, ConfigBase, GoldTableRefs


class Settings(ConfigBase):
    """Dashboard read settings."""

    dashboard: GoldTableRefs = GoldTableRefs()
    bigquery: BigQuery


@lru_cache
def get_settings() -> Settings:
    return Settings()
