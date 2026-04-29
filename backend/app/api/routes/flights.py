"""
REST API endpoints for Flights.
CRUD: Create, Read (list + get by id), Update, Delete.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.flight import FlightCreate, FlightUpdate, FlightResponse
from app.crud import flight as crud_flight
from app.models.flight import Flight

router = APIRouter()


@router.get("/", response_model=list[FlightResponse])
def list_flights(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    List all flights with pagination.
    Ordered by scheduled_departure ascending by default.
    """
    flights = crud_flight.get_flights(db, skip=skip, limit=limit)
    return flights


@router.get("/airlines", response_model=list[str])
def list_airlines(db: Session = Depends(get_db)):
    """
    Список всех авиакомпаний из БД (distinct, непустые).
    Нужен для формы распределения, чтобы не ограничиваться текущей датой/вкладкой.
    """
    rows = db.query(func.distinct(func.trim(Flight.airline))).filter(Flight.airline.isnot(None)).all()
    out = sorted({(r[0] or "").strip() for r in rows if (r[0] or "").strip()}, key=lambda x: x.lower())
    return out


@router.get("/{flight_id}", response_model=FlightResponse)
def get_flight(flight_id: int, db: Session = Depends(get_db)):
    """Get a single flight by id. Returns 404 if not found."""
    flight = crud_flight.get_flight(db, flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    return flight


@router.post("/", response_model=FlightResponse, status_code=201)
def create_flight(payload: FlightCreate, db: Session = Depends(get_db)):
    """Create a new flight. Returns the created flight with id."""
    flight = crud_flight.create_flight(db, payload)
    return flight


@router.patch("/{flight_id}", response_model=FlightResponse)
def update_flight(
    flight_id: int,
    payload: FlightUpdate,
    db: Session = Depends(get_db),
):
    """Partially update a flight. Returns 404 if not found."""
    flight = crud_flight.update_flight(db, flight_id, payload)
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    return flight


@router.delete("/{flight_id}", status_code=204)
def delete_flight(flight_id: int, db: Session = Depends(get_db)):
    """Delete a flight. Returns 404 if not found."""
    deleted = crud_flight.delete_flight(db, flight_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Flight not found")
    return None
