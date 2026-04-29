"""
REST API endpoints for Resources.
CRUD: Create, Read (list + get by id), Update, Delete.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.resource import ResourceCreate, ResourceUpdate, ResourceResponse, ResourceType
from app.crud import resource as crud_resource

router = APIRouter()


@router.get("/", response_model=list[ResourceResponse])
def list_resources(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    resource_type: ResourceType | None = Query(None),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    List all resources with optional filters.
    - resource_type: filter by check_in or gate
    - active_only: only return resources where is_active is True
    """
    resources = crud_resource.get_resources(
        db,
        skip=skip,
        limit=limit,
        resource_type=resource_type,
        active_only=active_only,
    )
    return resources


@router.get("/{resource_id}", response_model=ResourceResponse)
def get_resource(resource_id: int, db: Session = Depends(get_db)):
    """Get a single resource by id. Returns 404 if not found."""
    resource = crud_resource.get_resource(db, resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource


@router.post("/", response_model=ResourceResponse, status_code=201)
def create_resource(payload: ResourceCreate, db: Session = Depends(get_db)):
    """Create a new resource. Returns the created resource with id."""
    resource = crud_resource.create_resource(db, payload)
    return resource


@router.patch("/{resource_id}", response_model=ResourceResponse)
def update_resource(
    resource_id: int,
    payload: ResourceUpdate,
    db: Session = Depends(get_db),
):
    """Partially update a resource. Returns 404 if not found."""
    resource = crud_resource.update_resource(db, resource_id, payload)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource


@router.delete("/{resource_id}", status_code=204)
def delete_resource(resource_id: int, db: Session = Depends(get_db)):
    """Delete a resource. Returns 404 if not found."""
    deleted = crud_resource.delete_resource(db, resource_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Resource not found")
    return None
