"""
SQLAlchemy ORM models for the Airport RMS.
Import all models here so Base.metadata and Alembic can discover them.
"""

from app.models.flight import Flight
from app.models.resource import Resource
from app.models.allocation import Allocation
from app.models.checkin_norm import CheckinNorm
from app.models.gate_norm import GateNorm
from app.models.breakdown_event import BreakdownEvent

__all__ = ["Flight", "Resource", "Allocation", "CheckinNorm", "GateNorm", "BreakdownEvent"]
