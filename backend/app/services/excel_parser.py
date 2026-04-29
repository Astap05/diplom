"""
Парсер Excel-файла практики: импорт всех рейсов (1 фев — 18 мар 2026)
с созданием ресурсов и аллокаций (стойки, выходы).
"""

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.database import Base, engine
from app.models.flight import Flight, FlightType, FlightStatus
from app.models.resource import Resource
from app.models.allocation import Allocation, AllocationType

EXCEL_PATH = Path(__file__).resolve().parents[3] / "практика 2026.xls"

CHECKIN_BEFORE_DEP_MIN = 150  # check-in opens 2.5h before departure
CHECKIN_CLOSE_BEFORE_DEP_MIN = 40  # check-in closes 40min before departure
GATE_BEFORE_DEP_MIN = 60  # gate opens 1h before departure
GATE_AFTER_DEP_MIN = 10  # gate buffer after departure

def _safe_str(val) -> str | None:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return str(val).strip() or None


def _safe_dt(val) -> datetime | None:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    if isinstance(val, pd.Timestamp):
        return val.to_pydatetime()
    if isinstance(val, datetime):
        return val
    return None


def _safe_int(val) -> int:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return 0
    return int(val)


def _safe_float(val) -> float | None:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return float(val)


def _row_to_extra(row: pd.Series, columns: list[str]) -> str:
    """Serialize entire row to JSON for extra_data."""
    data = {}
    for col in columns:
        val = row.get(col)
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        if isinstance(val, pd.Timestamp):
            if pd.isna(val):
                continue
            data[col] = val.isoformat()
        elif isinstance(val, datetime):
            data[col] = val.isoformat()
        elif isinstance(val, bool):
            data[col] = val
        else:
            s = str(val)
            if s in ("NaT", "nan", "NaN", "None"):
                continue
            data[col] = val if isinstance(val, (int, float)) else s
    return json.dumps(data, ensure_ascii=False)


def _get_or_create_resource(db: Session, cache: dict, resource_type: str, name: str) -> Resource:
    key = (resource_type, name)
    if key in cache:
        return cache[key]
    res = db.query(Resource).filter(
        Resource.resource_type == resource_type, Resource.name == name
    ).first()
    if not res:
        res = Resource(resource_type=resource_type, name=name, is_active=True)
        db.add(res)
        db.flush()
    cache[key] = res
    return res


def import_excel(db: Session, excel_path: str | None = None, force: bool = False) -> dict:
    """Main import: read Excel, create flights + resources + allocations."""
    path = Path(excel_path) if excel_path else EXCEL_PATH
    if not path.exists():
        raise FileNotFoundError(f"Excel file not found: {path}")

    if not force:
        try:
            existing = db.query(Allocation).count()
            if existing > 0:
                return {"flights": 0, "allocations": existing, "checkin": 0, "gate": 0, "skipped": True}
        except Exception:
            pass

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db.commit()

    df = pd.read_excel(str(path))
    columns = df.columns.tolist()
    resource_cache: dict = {}

    stats = {"flights": 0, "allocations": 0, "checkin": 0, "gate": 0}

    for _, row in df.iterrows():
        flight_number = _safe_str(row.get("Номер рейса"))
        if not flight_number:
            continue

        dep_airport = _safe_str(row.get("АП Отправления (полное, рус)")) or ""
        arr_airport = _safe_str(row.get("АП Прибытия (полное, рус)")) or ""
        is_departure = "МИНСК" in dep_airport.upper()
        is_arrival = "МИНСК" in arr_airport.upper()

        plan_dep = _safe_dt(row.get("Дата/Время отпр. план"))
        fact_dep = _safe_dt(row.get("Дата/Время отпр. факт"))
        plan_arr = _safe_dt(row.get("Дата/Время приб. план"))
        fact_arr = _safe_dt(row.get("Дата/Время приб. факт"))
        takeoff = _safe_dt(row.get("Дата/Время взлета"))
        landing = _safe_dt(row.get("Дата/Время посадки"))
        expected_arr = _safe_dt(row.get("Время ожидаемого прибытия"))

        plan_time = plan_dep if is_departure else (plan_arr or landing)
        estimated_time = expected_arr if is_arrival else fact_dep
        fact_time = fact_dep if is_departure else (fact_arr or landing)

        delay_min = _safe_int(row.get("Время задержки (мин)"))
        is_delayed = delay_min > 0

        airline = _safe_str(row.get("Название АК")) or _safe_str(row.get("Код АК IATA")) or "—"
        aircraft = _safe_str(row.get("Полное назв ВС (Рус)")) or _safe_str(row.get("Тип ВС (IATA)")) or "—"

        direction = arr_airport if is_departure else dep_airport

        flight = Flight(
            flight_number=flight_number,
            airline=airline,
            aircraft_type=aircraft,
            external_flight_id=str(_safe_int(row.get("ID рейса"))) if row.get("ID рейса") else None,
            plan_time=plan_time,
            estimated_time=estimated_time,
            fact_time=fact_time,
            delayed_to=None,
            is_delayed=is_delayed,
            is_cancelled=False,
            airport=direction,
            ru_airport=direction,
            en_airport=_safe_str(row.get("АП Прибытия (полное, лат)")) if is_departure else _safe_str(row.get("АП Отправления (полное, лат)")),
            status_raw=_safe_str(row.get("Код задержки")),
            status_tablo="ЗАДЕРЖКА" if is_delayed else ("ВЫЛЕТЕЛ" if is_departure else "ПРИБЫЛ"),
            status_tablo_en="DELAYED" if is_delayed else ("DEPARTED" if is_departure else "ARRIVED"),
            flight_type=FlightType.DEPARTURE if is_departure else FlightType.ARRIVAL,
            code_shares=None,
            status=FlightStatus.DEPARTED if is_departure else FlightStatus.SCHEDULED,
            passengers_count=_safe_int(row.get("Пассаж. всего")),
            extra_data=_row_to_extra(row, columns),
        )
        db.add(flight)
        db.flush()
        stats["flights"] += 1

        # --- Check-in counters (departures only) ---
        counters_str = _safe_str(row.get("Стойки регистрации"))
        if is_departure and counters_str and plan_dep:
            p_start = plan_dep - timedelta(minutes=CHECKIN_BEFORE_DEP_MIN)
            p_end = plan_dep - timedelta(minutes=CHECKIN_CLOSE_BEFORE_DEP_MIN)
            real_ref = fact_dep or plan_dep
            r_start = real_ref - timedelta(minutes=CHECKIN_BEFORE_DEP_MIN)
            r_end = real_ref - timedelta(minutes=CHECKIN_CLOSE_BEFORE_DEP_MIN)
            for c in counters_str.split(","):
                c = c.strip()
                if not c:
                    continue
                res = _get_or_create_resource(db, resource_cache, "check-in", c)
                db.add(Allocation(
                    flight_id=flight.id, resource_id=res.id,
                    start_time=r_start, end_time=r_end,
                    plan_start_time=p_start, plan_end_time=p_end,
                    allocation_type=AllocationType.MANUAL,
                ))
                stats["allocations"] += 1
                stats["checkin"] += 1

        # --- Boarding gates (departures only) ---
        gates_str = _safe_str(row.get("Выходы на посадку"))
        if is_departure and gates_str and plan_dep:
            p_start = plan_dep - timedelta(minutes=GATE_BEFORE_DEP_MIN)
            p_end = plan_dep + timedelta(minutes=GATE_AFTER_DEP_MIN)
            real_ref = fact_dep or plan_dep
            r_start = real_ref - timedelta(minutes=GATE_BEFORE_DEP_MIN)
            r_end = real_ref + timedelta(minutes=GATE_AFTER_DEP_MIN)
            for g in gates_str.split(","):
                g = g.strip()
                if not g:
                    continue
                res = _get_or_create_resource(db, resource_cache, "gate", g)
                db.add(Allocation(
                    flight_id=flight.id, resource_id=res.id,
                    start_time=r_start, end_time=r_end,
                    plan_start_time=p_start, plan_end_time=p_end,
                    allocation_type=AllocationType.MANUAL,
                ))
                stats["allocations"] += 1
                stats["gate"] += 1

    db.commit()
    return stats
