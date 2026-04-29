"""
Импорт расписания из XML без авто-алгоритма.

POST /api/v1/import-xml

Задача: получить только «настоящие» назначения ресурсов из XML (MANUAL),
без дорисовки AUTO аллокаций.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db, engine, Base
from app.config import get_settings
from app.schemas.allocate import AllocateRequest
from app.services.xml_parser import parse_and_upsert_from_xml
from app.models.allocation import Allocation, AllocationType

router = APIRouter()


@router.post("/", response_model=dict)
def import_xml(payload: AllocateRequest, db: Session = Depends(get_db)):
    """
    Импортирует arrival/departure XML в БД и создаёт только MANUAL-аллокации.
    AUTO аллокации удаляются, чтобы на дашборде отображались только реальные данные.
    """
    try:
        settings = get_settings()
        # Для SQLite (дипломный режим без миграций) делаем "reset schema",
        # чтобы новые колонки из модели Flight гарантированно появились.
        if settings.DATABASE_URL.startswith("sqlite"):
            Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        # Удаляем AUTO, чтобы «придуманные» назначения не попадали в таймлайн.
        db.query(Allocation).filter(Allocation.allocation_type == AllocationType.AUTO).delete(synchronize_session=False)
        db.commit()

        stats = parse_and_upsert_from_xml(
            db,
            arrival_xml_path=payload.arrival_xml_path,
            departure_xml_path=payload.departure_xml_path,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Не удалось импортировать XML. Ошибка: {exc}") from exc

    return {
        "parsed_flights": stats.parsed_flights,
        "parsed_resources": stats.parsed_resources,
        "created_manual_allocations": stats.created_manual_allocations,
    }

