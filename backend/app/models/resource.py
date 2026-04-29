"""
Resource model: represents physical airport resources (check-in counters, boarding gates).
Each resource can be allocated to at most one flight in any given time interval.
"""

from sqlalchemy import Column, Integer, String, Boolean, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class ResourceType(str, enum.Enum):
    """Type of static resource; determines allocation rules and UI grouping."""

    # Важно: реальные данные и UI часто используют написание "check-in".
    # Мы сохраняем строковые значения именно так, чтобы JSON/API совпадали с требованиями диплома.
    CHECK_IN = "check-in"
    GATE = "gate"


class Resource(Base):
    """
    Table: resources
    Physical resources that can be assigned to flights (counters, gates).
    specifications: flexible JSON for capacity, zone, terminal, etc.
    """

    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    resource_type = Column(
        SQLEnum(ResourceType),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False, index=True)
    # Зона/сектор аэропорта (например, "Sector A"). Удобно для фильтрации и визуализации.
    zone = Column(String(100), nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    # Flexible metadata: e.g. {"capacity": 2, "terminal": "A", "zone": "domestic"}
    specifications = Column(JSON, nullable=True, default=dict)

    # Relationship: one resource can have many allocations over time
    allocations = relationship(
        "Allocation",
        back_populates="resource",
        foreign_keys="Allocation.resource_id",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Resource(id={self.id}, type='{self.resource_type}', name='{self.name}')>"
