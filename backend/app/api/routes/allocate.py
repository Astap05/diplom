"""
Эндпоинт запуска пайплайна:
- парсинг arrival/departure XML
- создание MANUAL аллокаций из дампа
- автоматическая аллокация оставшихся ресурсов

POST /api/v1/allocate
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.database import engine, Base
from app.schemas.allocate import AllocateRequest, AllocateResponse
from app.services.xml_parser import parse_and_upsert_from_xml
from app.services.allocator import allocate_all


router = APIRouter()


@router.post("/", response_model=AllocateResponse)
def allocate(payload: AllocateRequest, db: Session = Depends(get_db)) -> AllocateResponse:
    """
    Запускает полный цикл "реальные данные -> БД -> авто-распределение".

    Возвращает:
    - сколько рейсов/ресурсов распарсено
    - сколько MANUAL аллокаций создано из XML
    - сколько AUTO аллокаций создано алгоритмом
    - списки successes/conflicts (для визуализации и анализа на защите)
    """
    try:
        # Гарантируем наличие таблиц (для дипломного проекта удобно иметь "самонастраиваемый" старт).
        Base.metadata.create_all(bind=engine)

        stats = parse_and_upsert_from_xml(
            db,
            arrival_xml_path=payload.arrival_xml_path,
            departure_xml_path=payload.departure_xml_path,
        )

        result = allocate_all(db, replace_auto=payload.replace_auto_allocations)
    except Exception as exc:
        # Делает поведение понятным пользователю: чаще всего проблема — не запущен Postgres / неверный DATABASE_URL.
        raise HTTPException(
            status_code=503,
            detail=f"Не удалось выполнить allocate. Проверьте PostgreSQL и DATABASE_URL. Ошибка: {exc}",
        ) from exc

    return AllocateResponse(
        parsed_flights=stats.parsed_flights,
        parsed_resources=stats.parsed_resources,
        created_manual_allocations=stats.created_manual_allocations,
        auto_allocations_created=result.auto_allocations_created,
        successes=result.successes,
        conflicts=result.conflicts,
    )
