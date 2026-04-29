"""
История и состояние поломок для аварийного перераспределения стоек.
"""

from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.database import Base
from app.airport_time import utc_now


class BreakdownEvent(Base):
    __tablename__ = "breakdown_events"

    id = Column(String(64), primary_key=True, index=True)
    kind = Column(String(32), nullable=False)  # belt_gap | conveyor_engine
    kind_label = Column(String(128), nullable=False)

    broken_resource_id = Column(Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    broken_counter_name = Column(String(100), nullable=False)
    broken_island = Column(Integer, nullable=False)  # 1 | 2
    target_island = Column(Integer, nullable=False)  # 2 | 1

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    repaired_at = Column(DateTime(timezone=True), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="active", index=True)  # active | repaired
    note = Column(Text, nullable=True)

    # JSON в текстовом виде для SQLite-совместимости
    moves_json = Column(Text, nullable=False, default="[]")
    moved_allocation_ids_json = Column(Text, nullable=False, default="[]")
    original_by_allocation_id_json = Column(Text, nullable=False, default="{}")

    broken_resource = relationship("Resource", foreign_keys=[broken_resource_id])

    __table_args__ = (
        Index("ix_breakdown_events_status_created", "status", "created_at"),
    )

