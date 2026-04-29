"""
CRUD operations for Flight entity.
All functions accept a database session and return ORM models or None.
"""

from sqlalchemy.orm import Session

from app.models.flight import Flight
from app.schemas.flight import FlightCreate, FlightUpdate


def get_flight(db: Session, flight_id: int) -> Flight | None:
    """Fetch a single flight by primary key."""
    return db.query(Flight).filter(Flight.id == flight_id).first()


def get_flights(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    order_by_departure: bool = True,
) -> list[Flight]:
    """
    List flights with optional pagination.
    Default order: plan_time ascending (earliest first). Если plan_time пустой — будет NULLS FIRST/last в зависимости от СУБД.
    """
    q = db.query(Flight)
    if order_by_departure:
        q = q.order_by(Flight.plan_time, Flight.scheduled_departure)
    return q.offset(skip).limit(limit).all()


def create_flight(db: Session, payload: FlightCreate) -> Flight:
    """Create a new flight and return the persisted model."""
    flight = Flight(
        flight_number=payload.flight_number,
        airline=payload.airline,
        aircraft_type=payload.aircraft_type,
        scheduled_departure=payload.scheduled_departure,
        plan_time=payload.plan_time,
        estimated_time=payload.estimated_time,
        is_delayed=payload.is_delayed,
        flight_type=payload.flight_type,
        code_shares=payload.code_shares,
        status=payload.status,
        passengers_count=payload.passengers_count,
    )
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return flight


def update_flight(db: Session, flight_id: int, payload: FlightUpdate) -> Flight | None:
    """
    Partially update a flight. Only provided fields are updated.
    Returns the updated flight or None if not found.
    """
    flight = get_flight(db, flight_id)
    if not flight:
        return None
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(flight, key, value)
    db.commit()
    db.refresh(flight)
    return flight


def delete_flight(db: Session, flight_id: int) -> bool:
    """Delete a flight by id. Returns True if deleted, False if not found."""
    flight = get_flight(db, flight_id)
    if not flight:
        return False
    db.delete(flight)
    db.commit()
    return True
