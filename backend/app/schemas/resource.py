"""
Pydantic schemas for Resource entity.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.models.resource import ResourceType as ResourceTypeEnum


ResourceType = ResourceTypeEnum


class ResourceBase(BaseModel):
    """Base fields for resource create/update."""

    resource_type: ResourceType
    name: str = Field(..., min_length=1, max_length=100)
    zone: str | None = Field(default=None, max_length=100)
    is_active: bool = True
    specifications: dict | None = Field(default_factory=dict)


class ResourceCreate(ResourceBase):
    """Schema for creating a new resource."""

    pass


class ResourceUpdate(BaseModel):
    """Partial update; all fields optional."""

    resource_type: ResourceType | None = None
    name: str | None = Field(None, min_length=1, max_length=100)
    zone: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None
    specifications: dict | None = None


class ResourceInDB(ResourceBase):
    """Resource as stored in DB (includes id)."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class ResourceResponse(ResourceInDB):
    """API response schema for a single resource."""

    pass
