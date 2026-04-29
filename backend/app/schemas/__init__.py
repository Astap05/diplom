"""
Pydantic schemas for request/response validation and serialization.
"""

from app.schemas.flight import (
    FlightStatus,
    FlightBase,
    FlightCreate,
    FlightUpdate,
    FlightInDB,
    FlightResponse,
)
from app.schemas.resource import (
    ResourceType,
    ResourceBase,
    ResourceCreate,
    ResourceUpdate,
    ResourceInDB,
    ResourceResponse,
)
from app.schemas.allocation import (
    AllocationType,
    AllocationBase,
    AllocationCreate,
    AllocationUpdate,
    AllocationInDB,
    AllocationResponse,
)
from app.schemas.allocate import (
    AllocateRequest,
    AllocateResponse,
    AllocationConflict,
    AllocationSuccess,
)

__all__ = [
    "FlightStatus",
    "FlightBase",
    "FlightCreate",
    "FlightUpdate",
    "FlightInDB",
    "FlightResponse",
    "ResourceType",
    "ResourceBase",
    "ResourceCreate",
    "ResourceUpdate",
    "ResourceInDB",
    "ResourceResponse",
    "AllocationType",
    "AllocationBase",
    "AllocationCreate",
    "AllocationUpdate",
    "AllocationInDB",
    "AllocationResponse",
    "AllocateRequest",
    "AllocateResponse",
    "AllocationConflict",
    "AllocationSuccess",
]
