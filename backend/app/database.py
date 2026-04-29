"""
SQLAlchemy database engine and session management.
Provides dependency injection for FastAPI route handlers.

Поддерживаем:
- SQLite (по умолчанию, для простого запуска дипломного проекта)
- PostgreSQL (опционально)
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings

settings = get_settings()

# SQLite требует special-case: check_same_thread=False для работы из разных потоков (FastAPI).
_connect_args: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
elif "postgresql" in settings.DATABASE_URL:
    # Важно для Windows/локальной разработки: если Postgres недоступен,
    # приложение должно "падать быстро", а не зависать на старте.
    _connect_args = {"connect_timeout": 3}

# Create engine with connection pool; echo=True in development for SQL logging
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DEBUG,
    connect_args=_connect_args,
)

# Session factory: each request gets a new session, which is closed after use
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all ORM models; all models must inherit from this
Base = declarative_base()


def get_db():
    """
    Dependency that yields a database session.
    Ensures the session is closed after the request, even if an error occurs.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
