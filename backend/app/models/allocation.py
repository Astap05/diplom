"""
Allocation model: links a flight to a resource for a time window.
Supports both automatic (algorithm) and manual (user drag-and-drop) allocations.
"""

from sqlalchemy import Column, Integer, DateTime, ForeignKey, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class AllocationType(str, enum.Enum):
    """Origin of the allocation: automatic scheduler or manual override."""

    AUTO = "auto"
    MANUAL = "manual"


class Allocation(Base):
    """
    Table: allocations
    Assigns a resource to a flight for [start_time, end_time).
    allocation_type indicates whether the assignment was made by the algorithm or by the user.
    """

    __tablename__ = "allocations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    flight_id = Column(Integer, ForeignKey("flights.id", ondelete="CASCADE"), nullable=False)
    resource_id = Column(Integer, ForeignKey("resources.id", ondelete="CASCADE"), nullable=False)
    # Ресурс до первого ручного override диспетчером (для жёлтой подсветки после перезагрузки страницы)
    original_resource_id = Column(Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    plan_start_time = Column(DateTime(timezone=True), nullable=True)
    plan_end_time = Column(DateTime(timezone=True), nullable=True)
    allocation_type = Column(
        SQLEnum(AllocationType),
        nullable=False,
        default=AllocationType.AUTO,
    )

    # В новой версии проекта один рейс может получать несколько ресурсов одного типа
    # (например, 4 стойки регистрации). Это уже поддерживается тем, что Allocation — отдельная
    # сущность для связи Flight<->Resource. Уникальные ограничения на (resource_id, start_time)
    # убраны, потому что:
    # - пересечения по интервалам мы проверяем алгоритмом/валидатором
    # - для "общих" ресурсов (например, Drop-off стойка) допускаются пересечения
    __table_args__ = (
        Index("ix_allocations_resource_time", "resource_id", "start_time", "end_time"),
        Index("ix_allocations_flight_time", "flight_id", "start_time", "end_time"),
        Index("ix_allocations_type_start", "allocation_type", "start_time"),
    )

    flight = relationship("Flight", back_populates="allocations")
    resource = relationship("Resource", back_populates="allocations", foreign_keys=[resource_id])
    original_resource = relationship("Resource", foreign_keys=[original_resource_id])

    def __repr__(self) -> str:
        return f"<Allocation(id={self.id}, flight_id={self.flight_id}, resource_id={self.resource_id}, {self.start_time}–{self.end_time})>"
