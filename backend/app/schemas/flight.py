"""
Pydantic schemas for Flight entity.
Used for API request validation and response serialization.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.models.flight import FlightStatus as FlightStatusEnum, FlightType as FlightTypeEnum


# Re-export enum for schema consumers
FlightStatus = FlightStatusEnum
FlightType = FlightTypeEnum


class FlightBase(BaseModel):
    """Base fields shared by create and update."""

    flight_number: str = Field(..., min_length=1, max_length=20)
    airline: str = Field(..., min_length=1, max_length=100)
    aircraft_type: str = Field(..., min_length=1, max_length=50)
    # Новая модель времени: plan_time / estimated_time (+ is_delayed).
    # scheduled_departure оставлено для обратной совместимости и может быть пустым.
    scheduled_departure: datetime | None = None
    plan_time: datetime | None = None
    estimated_time: datetime | None = None
    fact_time: datetime | None = None
    delayed_to: datetime | None = None
    is_delayed: bool = False
    is_cancelled: bool = False
    flight_type: FlightType = Field(default=FlightTypeEnum.DEPARTURE)
    code_shares: str | None = None
    external_flight_id: str | None = None
    airport: str | None = None
    ru_airport: str | None = None
    en_airport: str | None = None
    status_raw: str | None = None
    status_tablo: str | None = None
    status_tablo_en: str | None = None
    status: FlightStatus = Field(default=FlightStatusEnum.SCHEDULED)
    passengers_count: int = Field(default=0, ge=0)


class FlightCreate(FlightBase):
    """Schema for creating a new flight. No id."""

    pass


class FlightUpdate(BaseModel):
    """Partial update; all fields optional."""

    flight_number: str | None = Field(None, min_length=1, max_length=20)
    airline: str | None = Field(None, min_length=1, max_length=100)
    aircraft_type: str | None = Field(None, min_length=1, max_length=50)
    scheduled_departure: datetime | None = None
    plan_time: datetime | None = None
    estimated_time: datetime | None = None
    fact_time: datetime | None = None
    delayed_to: datetime | None = None
    is_delayed: bool | None = None
    is_cancelled: bool | None = None
    flight_type: FlightType | None = None
    code_shares: str | None = None
    external_flight_id: str | None = None
    airport: str | None = None
    ru_airport: str | None = None
    en_airport: str | None = None
    status_raw: str | None = None
    status_tablo: str | None = None
    status_tablo_en: str | None = None
    status: FlightStatus | None = None
    passengers_count: int | None = Field(None, ge=0)


class FlightInDB(FlightBase):
    """Flight as stored in DB (includes id)."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class FlightResponse(FlightInDB):
    """API response schema for a single flight."""

    pass
