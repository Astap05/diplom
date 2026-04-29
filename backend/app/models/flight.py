"""
Flight model: represents a scheduled flight in the daily schedule.
Used as the primary entity for resource allocation (check-in counters, gates).
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum as SQLEnum, Text
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class FlightStatus(str, enum.Enum):
    """Flight lifecycle status for filtering and reporting."""

    SCHEDULED = "scheduled"
    CHECK_IN_OPEN = "check_in_open"
    BOARDING = "boarding"
    DEPARTED = "departed"
    CANCELLED = "cancelled"


class FlightType(str, enum.Enum):
    """
    Направление рейса.
    В контексте RMS оно определяет набор ресурсов и правила временных окон.
    """

    ARRIVAL = "arrival"
    DEPARTURE = "departure"


class Flight(Base):
    """
    Table: flights
    Stores daily flight schedule data; each row is one flight leg.
    """

    __tablename__ = "flights"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    flight_number = Column(String(20), nullable=False, index=True)
    airline = Column(String(100), nullable=False)
    aircraft_type = Column(String(50), nullable=False)
    # Legacy поле из первой версии проекта (оставлено для обратной совместимости).
    # В новой логике источником для временных окон являются plan_time / estimated_time.
    scheduled_departure = Column(DateTime(timezone=True), nullable=True)

    # Новые поля под реальные XML-дампы (arrival/departure).
    # external_flight_id: ID рейса из XML (<flight_id>) — помогает не путать рейсы с одинаковым номером
    external_flight_id = Column(String(50), nullable=True, index=True, default=None)

    # plan_time: плановое время (из <plan>)
    plan_time = Column(DateTime(timezone=True), nullable=True, index=True)
    # estimated_time: прогнозное/фактическое оценочное время (из <EAT>)
    estimated_time = Column(DateTime(timezone=True), nullable=True, index=True)
    # fact_time: фактическое время (из <fact>, если есть)
    fact_time = Column(DateTime(timezone=True), nullable=True, index=True)
    # delayed_to: время переноса (из <DelayedTo>, если есть)
    delayed_to = Column(DateTime(timezone=True), nullable=True, index=True)
    # is_delayed: 1 если рейс задержан (из <isDelayed>)
    is_delayed = Column(Boolean, nullable=False, default=False)
    # is_cancelled: 1 если рейс отменён (из <isCanseled>)
    is_cancelled = Column(Boolean, nullable=False, default=False)

    # airport_*: направление (из <airport>/<ru_airport>/<en_airport>)
    airport = Column(String(200), nullable=True, default=None)
    ru_airport = Column(String(200), nullable=True, default=None)
    en_airport = Column(String(200), nullable=True, default=None)

    # табло-статусы (из <status_tablo>/<status_tablo_en>) и сырой статус (из <status>)
    status_raw = Column(String(100), nullable=True, default=None)
    status_tablo = Column(String(100), nullable=True, default=None)
    status_tablo_en = Column(String(100), nullable=True, default=None)
    # arrival/departure — влияет на типы ресурсов и окна аллокации
    flight_type = Column(SQLEnum(FlightType), nullable=False, index=True, default=FlightType.DEPARTURE)
    # code_shares: строка с вторичными кодами (например, "WZ5941;SU1234")
    code_shares = Column(String(500), nullable=True, default=None)
    status = Column(
        SQLEnum(FlightStatus),
        nullable=False,
        default=FlightStatus.SCHEDULED,
    )
    passengers_count = Column(Integer, nullable=False, default=0)

    # JSON-строка с расширенными данными из Excel (175 колонок)
    extra_data = Column(Text, nullable=True, default=None)

    # Relationship: one flight can have many allocations (e.g. one check-in + one gate)
    allocations = relationship(
        "Allocation",
        back_populates="flight",
        foreign_keys="Allocation.flight_id",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Flight(id={self.id}, flight_number='{self.flight_number}', departure={self.scheduled_departure})>"
