"""
Application configuration using Pydantic Settings.
Loads environment variables for database and app settings.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Centralized configuration for the Airport RMS backend."""

    # Application
    APP_NAME: str = "Airport Resource Management System"
    DEBUG: bool = False

    # База данных по умолчанию: SQLite (файл рядом с backend/).
    # Это позволяет разворачивать дипломный проект без установки PostgreSQL/pgAdmin.
    #
    # Если захотите PostgreSQL позже:
    # DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/airport_rms
    DATABASE_URL: str = "sqlite:///./airport_rms.db"

    # API
    API_V1_PREFIX: str = "/api/v1"

    # Пути к XML-дампам (можно переопределить через .env)
    ARRIVAL_XML_PATH: str = "arrival_SPP_ru.xml"
    DEPARTURE_XML_PATH: str = "departure_SPP_ru.xml"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance to avoid re-reading env on every request."""
    return Settings()
