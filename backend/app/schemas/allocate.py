"""
Контракты API для запуска парсинга XML + автоматической аллокации ресурсов.

Эндпоинт: POST /api/v1/allocate
"""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

from app.schemas.resource import ResourceType
from app.schemas.allocation import AllocationType


class AllocateRequest(BaseModel):
    """
    Параметры запуска пайплайна.

    По умолчанию используются пути из Settings (ARRIVAL_XML_PATH / DEPARTURE_XML_PATH).
    Если передать `arrival_xml_path` / `departure_xml_path`, они переопределят значения из настроек.
    """

    arrival_xml_path: str | None = Field(default=None)
    departure_xml_path: str | None = Field(default=None)

    # Если True — перезаписываем/пересоздаём auto-аллокации для выбранного периода.
    # Manual-аллокации (из реального XML) не трогаем.
    replace_auto_allocations: bool = Field(default=True)


class AllocationSuccess(BaseModel):
    flight_id: int
    flight_number: str
    flight_type: str
    resource_type: ResourceType
    resource_names: list[str]
    start_time: datetime
    end_time: datetime
    allocation_type: AllocationType = AllocationType.AUTO


class AllocationConflict(BaseModel):
    flight_number: str
    flight_type: str
    resource_type: ResourceType
    start_time: datetime
    end_time: datetime
    required_count: int | None = None
    reason: str


class AllocateResponse(BaseModel):
    parsed_flights: int
    parsed_resources: int
    created_manual_allocations: int

    auto_allocations_created: int
    successes: list[AllocationSuccess]
    conflicts: list[AllocationConflict]
