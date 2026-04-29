"""
CRUD для аллокаций. Используется эндпоинтом дашборда GET /allocations.
"""

from datetime import datetime
from sqlalchemy.orm import Session, joinedload

from app.models.allocation import Allocation
from app.models.allocation import AllocationType


def get_allocations(
    db: Session,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 10000,
    allocation_type: AllocationType | None = None,
) -> list[Allocation]:
    """
    Список аллокаций с подгрузкой flight и resource.
    date_from/date_to — опциональная фильтрация по интервалу (по start_time).
    """
    q = (
        db.query(Allocation)
        .options(
            joinedload(Allocation.flight),
            joinedload(Allocation.resource),
            joinedload(Allocation.original_resource),
        )
    )
    if allocation_type is not None:
        q = q.filter(Allocation.allocation_type == allocation_type)
    if date_from is not None:
        q = q.filter(Allocation.start_time >= date_from)
    if date_to is not None:
        q = q.filter(Allocation.start_time < date_to)
    q = q.order_by(Allocation.start_time)
    return q.limit(limit).all()
