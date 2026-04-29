"""
Pydantic schemas for Allocation entity.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.models.allocation import AllocationType as AllocationTypeEnum


AllocationType = AllocationTypeEnum


class AllocationBase(BaseModel):
    """Base fields for allocation create/update."""

    flight_id: int
    resource_id: int
    start_time: datetime
    end_time: datetime
    allocation_type: AllocationType = Field(default=AllocationTypeEnum.AUTO)


class AllocationCreate(AllocationBase):
    """Schema for creating a new allocation."""

    pass


class AllocationUpdate(BaseModel):
    """Partial update; all fields optional."""

    flight_id: int | None = None
    resource_id: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    allocation_type: AllocationType | None = None


class AllocationInDB(AllocationBase):
    """Allocation as stored in DB (includes id)."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class AllocationResponse(AllocationInDB):
    """API response schema for a single allocation."""

    pass
