"""CRUD API for gate norms (нормативы выходов на посадку)."""

from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.gate_norm import GateNorm

router = APIRouter()


class GateNormOut(BaseModel):
    id: int
    name: str
    zone: str
    priority: int
    open_before_dep_min: int
    close_before_dep_min: int
    gates_count: int
    airline_codes: Optional[str] = None
    aircraft_type_code: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_active: bool

    class Config:
        from_attributes = True


class GateNormCreate(BaseModel):
    name: str
    zone: str = "international"
    priority: int = 1
    open_before_dep_min: int = 40
    close_before_dep_min: int = 15
    gates_count: int = 1
    airline_codes: Optional[str] = None
    aircraft_type_code: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_active: bool = True


class GateNormUpdate(BaseModel):
    name: Optional[str] = None
    zone: Optional[str] = None
    priority: Optional[int] = None
    open_before_dep_min: Optional[int] = None
    close_before_dep_min: Optional[int] = None
    gates_count: Optional[int] = None
    airline_codes: Optional[str] = None
    aircraft_type_code: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_active: Optional[bool] = None


@router.get("/", response_model=List[GateNormOut])
def list_norms(db: Session = Depends(get_db)):
    return db.query(GateNorm).order_by(GateNorm.priority, GateNorm.name).all()


@router.post("/", response_model=GateNormOut, status_code=201)
def create_norm(body: GateNormCreate, db: Session = Depends(get_db)):
    norm = GateNorm(**body.model_dump())
    db.add(norm)
    db.commit()
    db.refresh(norm)
    return norm


@router.patch("/{norm_id}", response_model=GateNormOut)
def update_norm(norm_id: int, body: GateNormUpdate, db: Session = Depends(get_db)):
    norm = db.query(GateNorm).filter(GateNorm.id == norm_id).first()
    if not norm:
        raise HTTPException(status_code=404, detail="Norm not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(norm, field, value)
    db.commit()
    db.refresh(norm)
    return norm


@router.delete("/{norm_id}", status_code=204)
def delete_norm(norm_id: int, db: Session = Depends(get_db)):
    norm = db.query(GateNorm).filter(GateNorm.id == norm_id).first()
    if not norm:
        raise HTTPException(status_code=404, detail="Norm not found")
    db.delete(norm)
    db.commit()
