"""
Эндпоинт для дашборда: список аллокаций с данными рейса и ресурса.
GET /api/v1/allocations — для построения таймлайна (groups = ресурсы, items = аллокации).
PATCH /api/v1/allocations/:id — ручное изменение ресурса аллокации диспетчером.
"""

from datetime import datetime, timedelta
import json
import re
from collections import Counter
from fastapi import APIRouter, Depends, Query, Path, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.database import get_db
from app.crud import allocation as crud_allocation
from app.schemas.dashboard import AllocationForDashboard
from app.services.aircraft_seats_catalog import enrich_extra_json, enrich_passenger_load_fields
from app.models.allocation import Allocation, AllocationType
from app.models.resource import Resource
from app.models.flight import Flight

router = APIRouter()


class PatchAllocationBody(BaseModel):
    resource_id: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class SimilarFlightHistoryItem(BaseModel):
    date: str
    aircraft_type: str
    checkin_interval: str
    counters: str
    pax_total: int
    seats_total: int
    status: str


def _num_from_extra(extra: dict, keys: list[str]) -> float | None:
    for k in keys:
        if k in extra:
            try:
                v = float(extra.get(k))
                if v > 0:
                    return v
            except Exception:
                continue
    return None


def _counter_sort_key(name: str) -> tuple[int, str]:
    m = re.match(r"^\s*(\d+)\s*$", name or "")
    if m:
        return (0, f"{int(m.group(1)):04d}")
    return (1, (name or "").strip())


def _first_str(extra: dict, keys: list[str]) -> str | None:
    for k in keys:
        v = extra.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def _parse_dt_value(v: object) -> datetime | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _looks_like_tail_number(value: str) -> bool:
    s = (value or "").strip().upper()
    if not s:
        return False
    # Частые шаблоны бортовых номеров: RA73103, EW455PA, UK32016 и т.п.
    if re.match(r"^[A-Z]{1,3}\d{3,6}[A-Z]{0,3}$", s):
        return True
    # Короткий числовой борт.
    if re.match(r"^\d{3,6}$", s):
        return True
    return False


@router.patch("/{allocation_id}", response_model=AllocationForDashboard)
def patch_allocation(
    allocation_id: int = Path(...),
    body: PatchAllocationBody = ...,
    db: Session = Depends(get_db),
):
    alloc = (
        db.query(Allocation)
        .options(
            joinedload(Allocation.flight),
            joinedload(Allocation.resource),
            joinedload(Allocation.original_resource),
        )
        .filter(Allocation.id == allocation_id)
        .first()
    )
    if not alloc:
        raise HTTPException(404, f"Allocation {allocation_id} not found")

    if body.resource_id is not None and body.resource_id != alloc.resource_id:
        res = db.query(Resource).filter(Resource.id == body.resource_id).first()
        if not res:
            raise HTTPException(404, f"Resource {body.resource_id} not found")
        if getattr(alloc, "original_resource_id", None) is None:
            alloc.original_resource_id = alloc.resource_id
        alloc.resource_id = body.resource_id
        alloc.resource = res
    if body.start_time is not None:
        alloc.start_time = body.start_time
    if body.end_time is not None:
        alloc.end_time = body.end_time

    db.commit()
    alloc = (
        db.query(Allocation)
        .options(
            joinedload(Allocation.flight),
            joinedload(Allocation.resource),
            joinedload(Allocation.original_resource),
        )
        .filter(Allocation.id == allocation_id)
        .first()
    )
    if not alloc:
        raise HTTPException(404, f"Allocation {allocation_id} not found")
    return _build_dashboard_item(alloc, alloc.flight, alloc.resource)


def _build_dashboard_item(a, f, r) -> AllocationForDashboard:
    orig_id = getattr(a, "original_resource_id", None)
    orig_row = getattr(a, "original_resource", None)
    active_override = orig_id is not None and orig_id != a.resource_id
    orig_name = None
    orig_type = None
    if active_override and orig_row is not None:
        orig_name = orig_row.name
        orig_type = orig_row.resource_type
    elif active_override:
        from sqlalchemy.orm import object_session

        sess = object_session(a)
        if sess is not None:
            res_orig = sess.query(Resource).filter(Resource.id == orig_id).first()
            if res_orig:
                orig_name = res_orig.name
                orig_type = res_orig.resource_type

    return AllocationForDashboard(
        id=a.id,
        flight_id=a.flight_id,
        resource_id=a.resource_id,
        start_time=a.start_time,
        end_time=a.end_time,
        plan_start_time=getattr(a, "plan_start_time", None),
        plan_end_time=getattr(a, "plan_end_time", None),
        allocation_type=a.allocation_type,
        flight_number=f.flight_number,
        airline=f.airline,
        aircraft_type=f.aircraft_type,
        plan_time=f.plan_time,
        estimated_time=f.estimated_time,
        fact_time=getattr(f, "fact_time", None),
        delayed_to=getattr(f, "delayed_to", None),
        is_delayed=f.is_delayed,
        code_shares=f.code_shares,
        is_cancelled=getattr(f, "is_cancelled", False),
        external_flight_id=getattr(f, "external_flight_id", None),
        airport=getattr(f, "airport", None),
        ru_airport=getattr(f, "ru_airport", None),
        en_airport=getattr(f, "en_airport", None),
        status_raw=getattr(f, "status_raw", None),
        status_tablo=getattr(f, "status_tablo", None),
        status_tablo_en=getattr(f, "status_tablo_en", None),
        extra_data=enrich_extra_json(getattr(f, "extra_data", None), getattr(f, "aircraft_type", None) or ""),
        resource_name=r.name,
        resource_type=r.resource_type,
        original_resource_id=orig_id if active_override else None,
        original_resource_name=orig_name if active_override else None,
        original_resource_type=orig_type if active_override else None,
    )


@router.get("/", response_model=list[AllocationForDashboard])
def list_allocations_for_dashboard(
    date: str | None = Query(None, description="День в формате YYYY-MM-DD. Если не передан — все аллокации."),
    allocation_type: AllocationType | None = Query(
        None,
        description="Фильтр по типу аллокации: manual (из XML) или auto (алгоритм).",
    ),
    db: Session = Depends(get_db),
):
    date_from = None
    date_to = None
    if date is not None:
        try:
            parsed = datetime.fromisoformat(date.replace("Z", "+00:00"))
        except ValueError:
            parsed = datetime.strptime(date[:10], "%Y-%m-%d")
        date_from = parsed.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        date_to = date_from + timedelta(days=1)

    allocations = crud_allocation.get_allocations(
        db,
        date_from=date_from,
        date_to=date_to,
        allocation_type=allocation_type,
    )
    return [_build_dashboard_item(a, a.flight, a.resource) for a in allocations]


@router.get("/history/similar", response_model=list[SimilarFlightHistoryItem])
def list_similar_flights_history(
    flight_number: str = Query(..., min_length=1),
    airline: str = Query(..., min_length=1),
    exclude_flight_id: int | None = Query(None),
    reference_plan_time: datetime | None = Query(None),
    limit: int = Query(7, ge=1, le=20),
    db: Session = Depends(get_db),
):
    fn = flight_number.strip().upper()
    an = airline.strip().casefold()

    def _query_similar(use_airline: bool):
        q = db.query(Flight).filter(
            func.upper(func.trim(Flight.flight_number)) == fn,
            Flight.plan_time.isnot(None),
        )
        if use_airline:
            q = q.filter(func.lower(func.trim(Flight.airline)) == an)
        if exclude_flight_id is not None:
            q = q.filter(Flight.id != exclude_flight_id)
        # "Последние" считаем относительно выбранного рейса:
        # не показываем будущие (после plan_time текущего рейса).
        if reference_plan_time is not None:
            q = q.filter(Flight.plan_time <= reference_plan_time)
        return q.order_by(Flight.plan_time.desc()).limit(limit).all()

    flights = _query_similar(use_airline=True)
    if not flights:
        # Fallback: иногда в БД у одной и той же АК разные написания.
        # Тогда берём по номеру рейса без строгого фильтра АК.
        flights = _query_similar(use_airline=False)

    if not flights:
        return []

    flight_ids = [f.id for f in flights]
    checkin_allocs = (
        db.query(Allocation)
        .join(Resource, Allocation.resource_id == Resource.id)
        .filter(
            Allocation.flight_id.in_(flight_ids),
            Resource.resource_type == "check-in",
        )
        .all()
    )
    by_flight: dict[int, list[Allocation]] = {}
    for a in checkin_allocs:
        by_flight.setdefault(a.flight_id, []).append(a)

    def _resolve_aircraft_type(extra: dict, fallback: str | None) -> str:
        aircraft_type = _first_str(
            extra,
            ["Полное назв ВС (Рус)", "Тип ВС (IATA)", "Тип ВС", "predicted_aircraft_type"],
        )
        if not aircraft_type:
            hist_types = extra.get("predicted_aircraft_types")
            if isinstance(hist_types, list) and hist_types:
                first = hist_types[0]
                if isinstance(first, dict):
                    t = str(first.get("type") or "").strip()
                    if t:
                        aircraft_type = t
        if not aircraft_type:
            aircraft_type = str(fallback or "").strip()
        if aircraft_type and not _looks_like_tail_number(aircraft_type):
            return aircraft_type
        return ""

    parsed_extras: dict[int, dict] = {}
    for f in flights:
        extra_raw = getattr(f, "extra_data", None)
        try:
            extra = json.loads(extra_raw) if extra_raw else {}
        except Exception:
            extra = {}
        if not isinstance(extra, dict):
            extra = {}
        parsed_extras[f.id] = extra

    # Фолбэк "без UNKNOWN": тип-мода по найденным прошлым рейсам + тип текущего выбранного рейса.
    type_counter: Counter[str] = Counter()
    for f in flights:
        t = _resolve_aircraft_type(parsed_extras.get(f.id, {}), getattr(f, "aircraft_type", None))
        if t:
            type_counter[t] += 1
    if exclude_flight_id is not None:
        ref_flight = db.query(Flight).filter(Flight.id == exclude_flight_id).first()
        if ref_flight is not None:
            ref_extra_raw = getattr(ref_flight, "extra_data", None)
            try:
                ref_extra = json.loads(ref_extra_raw) if ref_extra_raw else {}
            except Exception:
                ref_extra = {}
            if not isinstance(ref_extra, dict):
                ref_extra = {}
            ref_type = _resolve_aircraft_type(ref_extra, getattr(ref_flight, "aircraft_type", None))
            if ref_type:
                type_counter[ref_type] += 2
    fallback_type = type_counter.most_common(1)[0][0] if type_counter else "Тип ВС не указан"

    out: list[SimilarFlightHistoryItem] = []
    for f in flights:
        extra = parsed_extras.get(f.id, {})
        aircraft_type = _resolve_aircraft_type(extra, getattr(f, "aircraft_type", None)) or fallback_type

        pax_total = _num_from_extra(extra, ["Пассаж. всего", "predicted_pax_total"])
        if pax_total is None:
            try:
                pax_total = float(getattr(f, "passengers_count", 0) or 0) or None
            except Exception:
                pax_total = None

        seats_total = _num_from_extra(extra, ["Кол-во кресел", "Кол-во кресел для типа ВС (макс.)"])

        allocs = by_flight.get(f.id, [])
        counters = ""
        checkin_interval = ""
        if allocs:
            names = sorted([a.resource.name for a in allocs if a.resource is not None], key=_counter_sort_key)
            counters = "-".join([n for n in names if n]) or ""
            s = min(a.plan_start_time or a.start_time for a in allocs)
            e = max(a.plan_end_time or a.end_time for a in allocs)
            checkin_interval = f"{s.strftime('%H:%M')} - {e.strftime('%H:%M')}"
        else:
            # Fallback к плановым данным рейса/прогноза:
            # 1) набор стоек из extra_data (Excel/forecast),
            # 2) интервал регистрации по умолчанию от планового времени (-120..-40 мин).
            counters = _first_str(extra, ["Стойки регистрации", "predicted_counter_set"]) or ""
            t = getattr(f, "plan_time", None)
            if t is not None:
                s = t - timedelta(minutes=120)
                e = t - timedelta(minutes=40)
                checkin_interval = f"{s.strftime('%H:%M')} - {e.strftime('%H:%M')}"

        if not counters:
            counters = "нет данных"
        if not checkin_interval:
            checkin_interval = "нет данных"
        if pax_total is None:
            pax_total = 0.0

        merged_extra = dict(extra)
        if pax_total is not None:
            merged_extra["Пассаж. всего"] = float(pax_total)
        if seats_total is not None:
            merged_extra["Кол-во кресел"] = float(seats_total)
        enriched = enrich_passenger_load_fields(merged_extra, aircraft_type)
        pax_disp = enriched.get("Пассаж. всего")
        if pax_disp is None:
            pax_disp = enriched.get("predicted_pax_total")
        pax_int = int(max(0, round(float(pax_disp or 0))))
        seats_int = int(enriched.get("Кол-во кресел") or 0)
        if seats_int <= 0:
            seats_int = max(pax_int, 1)

        # Задержка: только если отклонение от плана > 10 минут.
        plan_dt = getattr(f, "plan_time", None)
        fact_dt = getattr(f, "fact_time", None) or getattr(f, "delayed_to", None)
        if fact_dt is None:
            fact_dt = _parse_dt_value(extra.get("Дата/Время отпр. факт"))
        delay_min = 0
        if plan_dt is not None and fact_dt is not None:
            delay_min = int(round((fact_dt - plan_dt).total_seconds() / 60.0))
        status = "Задержка" if delay_min > 10 else "По плану"

        out.append(
            SimilarFlightHistoryItem(
                date=f.plan_time.date().isoformat(),
                aircraft_type=str(aircraft_type),
                checkin_interval=checkin_interval,
                counters=counters,
                pax_total=pax_int,
                seats_total=seats_int,
                status=status,
            )
        )
    return out
