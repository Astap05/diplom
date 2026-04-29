"""
CRUD API for check-in counter norms (нормативы стоек регистрации).
"""

from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.checkin_norm import CheckinNorm

router = APIRouter()


class CheckinNormOut(BaseModel):
    id: int
    name: str
    zone: str
    priority: int
    open_before_dep_min: int
    close_before_dep_min: int
    counters_count: int
    has_business_counter: bool
    business_counters_count: int
    airline_codes: Optional[str] = None
    aircraft_type_code: Optional[str] = None
    airport_codes: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_active: bool

    class Config:
        from_attributes = True


class CheckinNormCreate(BaseModel):
    name: str
    zone: str = "international"
    priority: int = 1
    open_before_dep_min: int = 120
    close_before_dep_min: int = 40
    counters_count: int = 2
    has_business_counter: bool = False
    business_counters_count: int = 0
    airline_codes: Optional[str] = None
    aircraft_type_code: Optional[str] = None
    airport_codes: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_active: bool = True


class CheckinNormUpdate(BaseModel):
    name: Optional[str] = None
    zone: Optional[str] = None
    priority: Optional[int] = None
    open_before_dep_min: Optional[int] = None
    close_before_dep_min: Optional[int] = None
    counters_count: Optional[int] = None
    has_business_counter: Optional[bool] = None
    business_counters_count: Optional[int] = None
    airline_codes: Optional[str] = None
    aircraft_type_code: Optional[str] = None
    airport_codes: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_active: Optional[bool] = None


@router.get("/", response_model=List[CheckinNormOut])
def list_norms(db: Session = Depends(get_db)):
    return db.query(CheckinNorm).order_by(CheckinNorm.priority, CheckinNorm.name).all()


@router.post("/", response_model=CheckinNormOut, status_code=201)
def create_norm(body: CheckinNormCreate, db: Session = Depends(get_db)):
    norm = CheckinNorm(**body.model_dump())
    db.add(norm)
    db.commit()
    db.refresh(norm)
    return norm


@router.patch("/{norm_id}", response_model=CheckinNormOut)
def update_norm(norm_id: int, body: CheckinNormUpdate, db: Session = Depends(get_db)):
    norm = db.query(CheckinNorm).filter(CheckinNorm.id == norm_id).first()
    if not norm:
        raise HTTPException(status_code=404, detail="Norm not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(norm, field, value)
    db.commit()
    db.refresh(norm)
    return norm


@router.delete("/{norm_id}", status_code=204)
def delete_norm(norm_id: int, db: Session = Depends(get_db)):
    norm = db.query(CheckinNorm).filter(CheckinNorm.id == norm_id).first()
    if not norm:
        raise HTTPException(status_code=404, detail="Norm not found")
    db.delete(norm)
    db.commit()
