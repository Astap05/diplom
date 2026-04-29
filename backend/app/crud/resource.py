"""
CRUD operations for Resource entity.
"""

from sqlalchemy.orm import Session

from app.models.resource import Resource, ResourceType
from app.schemas.resource import ResourceCreate, ResourceUpdate


def get_resource(db: Session, resource_id: int) -> Resource | None:
    """Fetch a single resource by primary key."""
    return db.query(Resource).filter(Resource.id == resource_id).first()


def get_resources(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    resource_type: ResourceType | None = None,
    active_only: bool = False,
) -> list[Resource]:
    """
    List resources with optional filters and pagination.
    """
    q = db.query(Resource)
    if resource_type is not None:
        q = q.filter(Resource.resource_type == resource_type)
    if active_only:
        q = q.filter(Resource.is_active == True)
    q = q.order_by(Resource.resource_type, Resource.name)
    return q.offset(skip).limit(limit).all()


def create_resource(db: Session, payload: ResourceCreate) -> Resource:
    """Create a new resource and return the persisted model."""
    resource = Resource(
        resource_type=payload.resource_type,
        name=payload.name,
        zone=payload.zone,
        is_active=payload.is_active,
        specifications=payload.specifications or {},
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


def update_resource(
    db: Session, resource_id: int, payload: ResourceUpdate
) -> Resource | None:
    """
    Partially update a resource. Only provided fields are updated.
    Returns the updated resource or None if not found.
    """
    resource = get_resource(db, resource_id)
    if not resource:
        return None
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(resource, key, value)
    db.commit()
    db.refresh(resource)
    return resource


def delete_resource(db: Session, resource_id: int) -> bool:
    """Delete a resource by id. Returns True if deleted, False if not found."""
    resource = get_resource(db, resource_id)
    if not resource:
        return False
    db.delete(resource)
    db.commit()
    return True
