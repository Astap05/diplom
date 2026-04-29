"""
Схемы для дашборда: аллокации с вложенными данными рейса и ресурса.
Используются в GET /api/v1/allocations для таймлайна и карточек.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.models.resource import ResourceType
from app.models.allocation import AllocationType


class AllocationForDashboard(BaseModel):
    """Одна аллокация с полями рейса и ресурса для отображения на таймлайне."""

    id: int
    flight_id: int
    resource_id: int
    start_time: datetime
    end_time: datetime
    plan_start_time: datetime | None = None
    plan_end_time: datetime | None = None
    allocation_type: AllocationType

    # Поля рейса (для тултипа и раскраски)
    flight_number: str
    airline: str
    aircraft_type: str
    plan_time: datetime | None
    estimated_time: datetime | None
    fact_time: datetime | None
    delayed_to: datetime | None
    is_delayed: bool
    is_cancelled: bool
    code_shares: str | None
    external_flight_id: str | None
    airport: str | None
    ru_airport: str | None
    en_airport: str | None
    status_raw: str | None
    status_tablo: str | None
    status_tablo_en: str | None

    # Расширенные данные из Excel (все 175 колонок)
    extra_data: str | None = None

    # Поля ресурса (для группы на оси Y)
    resource_name: str
    resource_type: ResourceType
    # Ручное изменение ресурса: исходный ресурс (если отличается от текущего — жёлтая плитка)
    original_resource_id: int | None = None
    original_resource_name: str | None = None
    original_resource_type: ResourceType | None = None
