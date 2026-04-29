"""
Airport Resource Management System (RMS) - FastAPI application entry point.
Mounts API routes and initializes database tables on startup.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import inspect, text

from app.config import get_settings
from app.database import engine, Base
from app.models import Flight, Resource, Allocation, CheckinNorm, GateNorm, BreakdownEvent  # noqa: F401 - register models
from app.api.routes import api_router
from app.database import SessionLocal
from app.services.checkin_norms_seed import seed_checkin_norms
from app.services.gate_norms_seed import seed_gate_norms


def _sqlite_add_column_if_missing(table: str, column: str, ddl_suffix: str) -> None:
    """Добавить колонку в SQLite без Alembic (если её ещё нет)."""
    try:
        insp = inspect(engine)
        if not insp.has_table(table):
            return
        cols = {c["name"] for c in insp.get_columns(table)}
        if column in cols:
            return
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_suffix}"))
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan hook.
    Для SQLite при старте создаём файл БД и таблицы — так БД сразу готова к работе.
    Для PostgreSQL не создаём таблицы на старте, чтобы не зависать при недоступном сервере.
    """
    if get_settings().DATABASE_URL.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
        _sqlite_add_column_if_missing("allocations", "original_resource_id", "INTEGER")
        # Удаляем устаревшие данные по багажным лентам (модель каруселей снята).
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "DELETE FROM allocations WHERE resource_id IN "
                        "(SELECT id FROM resources WHERE resource_type = 'baggage_carousel')"
                    )
                )
                conn.execute(text("DELETE FROM resources WHERE resource_type = 'baggage_carousel'"))
                conn.execute(text("DROP TABLE IF EXISTS baggage_norms"))
        except Exception:
            pass
        db = SessionLocal()
        try:
            seed_checkin_norms(db)
            seed_gate_norms(db)
        finally:
            db.close()
    yield


settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    description="API for automating and visualizing allocation of check-in counters and boarding gates to flights.",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow frontend (e.g. Next.js on another port) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root():
    """Health check and API info."""
    return {
        "app": settings.APP_NAME,
        "docs": "/docs",
        "api_v1": settings.API_V1_PREFIX,
    }
