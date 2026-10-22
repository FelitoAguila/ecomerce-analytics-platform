from functools import lru_cache

import boto3
from botocore.client import BaseClient
from pydantic import AnyUrl, BaseModel, SecretStr

from config.settings import ConfigBase, PostgresDB


class ObjectStorage(BaseModel):
    """Neon Object Storage (S3-compatible) holding the olist-dataset CSVs."""

    aws_endpoint_url_s3: AnyUrl
    aws_access_key_id: SecretStr
    aws_secret_access_key: SecretStr
    aws_region: str
    bucket: str = "olist-dataset"

    def s3_client(self) -> BaseClient:
        """Build an explicit S3 client from these settings."""
        return boto3.client(
            "s3",
            endpoint_url=str(self.aws_endpoint_url_s3),
            aws_access_key_id=self.aws_access_key_id.get_secret_value(),
            aws_secret_access_key=self.aws_secret_access_key.get_secret_value(),
            region_name=self.aws_region,
        )


class Settings(ConfigBase):
    """Application settings root for the OLTP database service."""

    postgres_db: PostgresDB
    object_storage: ObjectStorage


@lru_cache
def get_settings() -> Settings:
    return Settings()
