"""Application configuration loaded from environment variables."""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Disaster Relief Response Gap Tracker"
    database_url: str = os.getenv("DATABASE_URL", "postgresql+psycopg://drrgt:drrgt@db:5432/drrgt")
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    fema_base_url: str = "https://www.fema.gov/api/open"
    census_api_key: str | None = os.getenv("CENSUS_API_KEY")
    census_base_url: str = "https://api.census.gov/data"
    cache_ttl_seconds: int = 3600
    # Bump to invalidate all versioned cache keys without a separate flush
    cache_version: str = "v1"
    use_sample_data_fallback: bool = True
    # S3 bucket for raw FEMA/Census snapshots; leave empty to skip archival
    raw_bucket: str | None = os.getenv("RAW_BUCKET")
    # SQLAlchemy connection pool — sized for a Fargate 512 CPU task
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
