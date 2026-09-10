from functools import lru_cache

from config.settings import ConfigBase, GoldTableRefs, WarehouseLocal


class Settings(ConfigBase):
    """Dashboard read settings."""

    dashboard: GoldTableRefs = GoldTableRefs()
    warehouse_local: WarehouseLocal = WarehouseLocal()


@lru_cache
def get_settings() -> Settings:
    return Settings()