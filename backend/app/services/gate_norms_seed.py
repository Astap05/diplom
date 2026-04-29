"""Seed data for gate norms."""

from datetime import date
from sqlalchemy.orm import Session

from app.models.gate_norm import GateNorm

SEED_DATA = [
    {"name": "Inner", "zone": "internal", "priority": 1, "open_before_dep_min": 40, "close_before_dep_min": 15, "gates_count": 1, "airline_codes": None, "aircraft_type_code": None, "valid_from": date(2015, 1, 31)},
    {"name": "International", "zone": "international", "priority": 1, "open_before_dep_min": 40, "close_before_dep_min": 15, "gates_count": 1, "airline_codes": None, "aircraft_type_code": None, "valid_from": date(2015, 1, 31)},
    {"name": "Air China", "zone": "international", "priority": 1, "open_before_dep_min": 30, "close_before_dep_min": 15, "gates_count": 2, "airline_codes": "CA", "aircraft_type_code": None, "valid_from": date(2021, 2, 18)},
    {"name": "Uzbekistan airways", "zone": "international", "priority": 1, "open_before_dep_min": 30, "close_before_dep_min": 15, "gates_count": 1, "airline_codes": "HY", "aircraft_type_code": None, "valid_from": date(2022, 6, 8)},
    {"name": "FlyDubai", "zone": "international", "priority": 1, "open_before_dep_min": 30, "close_before_dep_min": 10, "gates_count": 2, "airline_codes": "FZ", "aircraft_type_code": None, "valid_from": date(2022, 8, 8)},
    {"name": "Победа", "zone": "international", "priority": 1, "open_before_dep_min": 30, "close_before_dep_min": 23, "gates_count": 2, "airline_codes": "DP", "aircraft_type_code": None, "valid_from": date(2022, 8, 8)},
    {"name": "Белавиа", "zone": "international", "priority": 1, "open_before_dep_min": 35, "close_before_dep_min": 20, "gates_count": 2, "airline_codes": "B2", "aircraft_type_code": None, "valid_from": date(2023, 9, 19)},
    {"name": "Аэрофлот", "zone": "international", "priority": 1, "open_before_dep_min": 40, "close_before_dep_min": 20, "gates_count": 1, "airline_codes": "SU", "aircraft_type_code": None, "valid_from": date(2024, 8, 31)},
]


def seed_gate_norms(db: Session) -> int:
    existing = db.query(GateNorm).count()
    if existing > 0:
        return 0
    for row in SEED_DATA:
        db.add(GateNorm(**row, is_active=True))
    db.commit()
    return len(SEED_DATA)
