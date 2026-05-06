from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "DoctorFinder API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database (PostgreSQL)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/doctorfinder"
    DATABASE_URL_SYNC: str = "postgresql://postgres:password@localhost:5432/doctorfinder"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL: int = 300
    SEARCH_CACHE_TTL: int = 60

    # Elasticsearch
    ELASTICSEARCH_URL: str = "https://localhost:9200"
    ELASTICSEARCH_USER: Optional[str] = "elastic"
    ELASTICSEARCH_PASSWORD: Optional[str] = None
    ELASTICSEARCH_VERIFY_CERTS: bool = False
    ELASTICSEARCH_INDEX_DOCTORS: str = "doctors"

    # JWT
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Pagination
    DEFAULT_PAGE_SIZE: int = 10
    MAX_PAGE_SIZE: int = 50

    # Geo search radius (km)
    DEFAULT_SEARCH_RADIUS_KM: float = 10.0

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
