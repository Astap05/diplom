from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.orm import Session

from app.database import get_db
from app.airport_time import airport_now_naive, utc_now
from app.models.breakdown_event import BreakdownEvent
from app.models.allocation import Allocation
from app.models.resource import Resource

router = APIRouter()


class BreakdownMoveItem(BaseModel):
    flight_number: str
    from_counters: str
    to_counters: str


class BreakdownEventOut(BaseModel):
    id: str
    kind: str
    kind_label: str
    broken_resource_id: int | None
    broken_counter_name: str
    broken_island: int
    target_island: int
    created_at: datetime
    repaired_at: datetime | None = None
    status: str
    note: str | None = None
    moves: list[BreakdownMoveItem] = Field(default_factory=list)

    @field_serializer("created_at", "repaired_at", when_used="json")
    def _serialize_times_iso_z(self, v: datetime | None) -> str | None:
        """Naive UTC из старых записей трактуем как UTC; в JSON всегда с суффиксом Z для корректного Date() в браузере."""
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class BreakdownStartIn(BaseModel):
    kind: str
    checkin_resource_id: int


class BreakdownActionOut(BaseModel):
    ok: bool
    event: BreakdownEventOut
    moved_allocations: int
    moved_flights: int
    failed_flights: int


class BreakdownReconcileOut(BaseModel):
    ok: bool
    total_moved_allocations: int
    total_moved_flights: int
    events_touched: int


def _counter_num(name: str) -> int | None:
    m = re.match(r"^\s*(\d+)\s*$", str(name or ""))
    return int(m.group(1)) if m else None


def _island_of_resource(res: Resource | None) -> int | None:
    if res is None or str(res.resource_type) != "ResourceType.CHECK_IN":
        # enum string repr for SQLAlchemy Enum in Python objects
        if res is None or str(getattr(res, "resource_type", "")) != "check-in":
            return None
    n = _counter_num(res.name)
    if n is None:
        return None
    if 1 <= n <= 22:
        return 1
    if 23 <= n <= 43:
        return 2
    return None


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and a_end > b_start


def _kind_label(kind: str) -> str:
    return "Разрыв ленты" if kind == "belt_gap" else "Поломка двигателя конвейера"


def _safe_loads(ev: BreakdownEvent) -> tuple[list[dict[str, Any]], list[int], dict[int, int]]:
    try:
        moves = json.loads(ev.moves_json or "[]")
    except Exception:
        moves = []
    if not isinstance(moves, list):
        moves = []
    try:
        moved_ids = json.loads(ev.moved_allocation_ids_json or "[]")
    except Exception:
        moved_ids = []
    if not isinstance(moved_ids, list):
        moved_ids = []
    moved_ids = [int(x) for x in moved_ids if isinstance(x, (int, float, str)) and str(x).isdigit()]
    try:
        original = json.loads(ev.original_by_allocation_id_json or "{}")
    except Exception:
        original = {}
    if not isinstance(original, dict):
        original = {}
    original_map: dict[int, int] = {}
    for k, v in original.items():
        if str(k).isdigit() and str(v).isdigit():
            original_map[int(k)] = int(v)
    return moves, moved_ids, original_map


def _dump_event_state(ev: BreakdownEvent, moves: list[dict[str, Any]], moved_ids: list[int], original_map: dict[int, int], note: str | None = None) -> None:
    ev.moves_json = json.dumps(moves, ensure_ascii=False)
    ev.moved_allocation_ids_json = json.dumps(sorted(set(int(x) for x in moved_ids)), ensure_ascii=False)
    ev.original_by_allocation_id_json = json.dumps({str(k): int(v) for k, v in original_map.items()}, ensure_ascii=False)
    if note is not None:
        ev.note = note


def _event_to_out(ev: BreakdownEvent) -> BreakdownEventOut:
    moves, _, _ = _safe_loads(ev)
    out_moves: list[BreakdownMoveItem] = []
    for m in moves:
        try:
            out_moves.append(
                BreakdownMoveItem(
                    flight_number=str(m.get("flight_number", "")),
                    from_counters=str(m.get("from_counters", "")),
                    to_counters=str(m.get("to_counters", "")),
                )
            )
        except Exception:
            continue
    return BreakdownEventOut(
        id=ev.id,
        kind=ev.kind,
        kind_label=ev.kind_label,
        broken_resource_id=ev.broken_resource_id,
        broken_counter_name=ev.broken_counter_name,
        broken_island=ev.broken_island,
        target_island=ev.target_island,
        created_at=ev.created_at,
        repaired_at=ev.repaired_at,
        status=ev.status,
        note=ev.note,
        moves=out_moves,
    )


def _choose_nearby_counters(pool: list[Resource], needed: int, preferred_nums: list[int]) -> list[Resource]:
    if needed <= 0:
        return []
    sorted_pool = sorted(pool, key=lambda r: (_counter_num(r.name) or 10**9, r.name))
    if len(sorted_pool) < needed:
        return []
    pref = [n for n in preferred_nums if n is not None] or [(_counter_num(r.name) or 10**9) for r in sorted_pool]

    def dist(n: int) -> int:
        return min(abs(n - p) for p in pref) if pref else 0

    best: tuple[int, int, int, list[Resource]] | None = None
    nums = [(_counter_num(r.name) or 10**9) for r in sorted_pool]
    for i in range(0, len(sorted_pool) - needed + 1):
        win = sorted_pool[i : i + needed]
        wnums = nums[i : i + needed]
        if any(n >= 10**9 for n in wnums):
            continue
        if max(wnums) - min(wnums) != needed - 1:
            continue
        score = (sum(dist(n) for n in wnums), min(wnums), max(wnums), win)
        if best is None or score[:3] < best[:3]:
            best = score
    if best is not None:
        return best[3]
    return sorted(
        sorted_pool,
        key=lambda r: (
            dist((_counter_num(r.name) or 10**9)),
            (_counter_num(r.name) or 10**9),
            r.name,
        ),
    )[:needed]


def _run_reconcile_for_event(db: Session, ev: BreakdownEvent) -> tuple[int, int, int]:
    # Та же шкала, что и у Allocation.start_time/end_time после импорта (см. airport_time.TIME_SHIFT_HOURS).
    now = airport_now_naive()
    resources = db.query(Resource).all()
    by_id = {r.id: r for r in resources}
    target_pool = [
        r for r in resources
        if str(getattr(r, "resource_type", "")) in {"ResourceType.CHECK_IN", "check-in"} and _island_of_resource(r) == ev.target_island
    ]
    all_checkin = [
        a for a in db.query(Allocation).all()
        if str(getattr(by_id.get(a.resource_id), "resource_type", "")) in {"ResourceType.CHECK_IN", "check-in"}
    ]

    moves, moved_ids, original_map = _safe_loads(ev)

    active_on_broken = []
    for a in all_checkin:
        res = by_id.get(a.resource_id)
        if _island_of_resource(res) != ev.broken_island:
            continue
        if now >= a.start_time and now < a.end_time:
            active_on_broken.append(a)

    by_flight: dict[int, list[Allocation]] = {}
    for a in active_on_broken:
        by_flight.setdefault(a.flight_id, []).append(a)

    reserved: dict[int, list[tuple[datetime, datetime]]] = {}

    def is_free(res_id: int, s: datetime, e: datetime, ignore_ids: set[int]) -> bool:
        for a in all_checkin:
            if a.id in ignore_ids:
                continue
            if a.resource_id != res_id:
                continue
            if _overlaps(s, e, a.start_time, a.end_time):
                return False
        for rs, re in reserved.get(res_id, []):
            if _overlaps(s, e, rs, re):
                return False
        return True

    moved_alloc_count = 0
    moved_flights = 0
    failed_flights = 0

    for _, group in by_flight.items():
        sorted_group = sorted(group, key=lambda x: (_counter_num(by_id.get(x.resource_id).name if by_id.get(x.resource_id) else "") or 10**9))
        s = min(x.start_time for x in sorted_group)
        e = max(x.end_time for x in sorted_group)
        need = len(sorted_group)
        sample = sorted_group[0]
        try:
            extra = json.loads(getattr(sample.flight, "extra_data", "") or "{}")
        except Exception:
            extra = {}
        preferred_nums = [
            n for n in [
                _counter_num(x) for x in str(extra.get("predicted_counter_set", "")).split("-")
            ] if n is not None and ((ev.target_island == 1 and n <= 22) or (ev.target_island == 2 and n >= 23))
        ]
        ignore = {x.id for x in sorted_group}
        free = [r for r in target_pool if is_free(r.id, s, e, ignore)]
        chosen = _choose_nearby_counters(free, need, preferred_nums)
        if len(chosen) < need:
            failed_flights += 1
            continue
        moved_flights += 1

        from_counters = "-".join(sorted([(by_id.get(x.resource_id).name if by_id.get(x.resource_id) else "?") for x in sorted_group], key=lambda z: (_counter_num(z) or 10**9)))
        to_counters = "-".join(sorted([x.name for x in chosen], key=lambda z: (_counter_num(z) or 10**9)))
        flight_number = str(getattr(sample.flight, "flight_number", ""))
        moves.append({"flight_number": flight_number, "from_counters": from_counters, "to_counters": to_counters})

        for i in range(len(sorted_group)):
            a = sorted_group[i]
            target = chosen[i]
            if a.id not in original_map:
                original_map[a.id] = a.resource_id
            # Подсветка в UI (жёлтый): фиксируем "домашнюю" стойку как исходную
            # при первом аварийном переносе, аналогично ручному override.
            if getattr(a, "original_resource_id", None) is None:
                a.original_resource_id = original_map[a.id]
            a.resource_id = target.id
            moved_ids.append(a.id)
            moved_alloc_count += 1
            reserved.setdefault(target.id, []).append((s, e))

    _dump_event_state(
        ev,
        moves,
        moved_ids,
        original_map,
        note=(
            f"Часть рейсов не удалось перенести: {failed_flights}."
            if failed_flights > 0
            else "Перераспределение выполнено."
        ),
    )
    db.commit()
    return moved_alloc_count, moved_flights, failed_flights


def _run_repair_for_event(db: Session, ev: BreakdownEvent) -> tuple[int, int, int]:
    resources = db.query(Resource).all()
    by_id = {r.id: r for r in resources}
    all_checkin = [
        a for a in db.query(Allocation).all()
        if str(getattr(by_id.get(a.resource_id), "resource_type", "")) in {"ResourceType.CHECK_IN", "check-in"}
    ]
    home_pool = [
        r for r in resources
        if str(getattr(r, "resource_type", "")) in {"ResourceType.CHECK_IN", "check-in"} and _island_of_resource(r) == ev.broken_island
    ]

    moves, moved_ids, original_map = _safe_loads(ev)
    affected = [a for a in all_checkin if a.id in moved_ids]
    by_flight: dict[int, list[Allocation]] = {}
    for a in affected:
        by_flight.setdefault(a.flight_id, []).append(a)

    reserved: dict[int, list[tuple[datetime, datetime]]] = {}

    def is_free(res_id: int, s: datetime, e: datetime, ignore_ids: set[int]) -> bool:
        for a in all_checkin:
            if a.id in ignore_ids:
                continue
            if a.resource_id != res_id:
                continue
            if _overlaps(s, e, a.start_time, a.end_time):
                return False
        for rs, re in reserved.get(res_id, []):
            if _overlaps(s, e, rs, re):
                return False
        return True

    moved_alloc_count = 0
    moved_flights = 0
    failed_flights = 0

    for _, group in by_flight.items():
        s = min(x.start_time for x in group)
        e = max(x.end_time for x in group)
        need = len(group)
        sorted_group = sorted(group, key=lambda x: (_counter_num(by_id.get(x.resource_id).name if by_id.get(x.resource_id) else "") or 10**9))

        # 1) Сначала пробуем вернуть КАЖДУЮ аллокацию на её исходную стойку (точный возврат).
        ignore = {x.id for x in group}
        exact_targets: list[tuple[Allocation, Resource]] = []
        exact_ok = True
        used_target_ids: set[int] = set()
        for a in sorted_group:
            home_res_id = original_map.get(a.id)
            home_res = by_id.get(home_res_id) if home_res_id is not None else None
            if (
                home_res is None
                or _island_of_resource(home_res) != ev.broken_island
                or home_res.id in used_target_ids
                or not is_free(home_res.id, s, e, ignore)
            ):
                exact_ok = False
                break
            exact_targets.append((a, home_res))
            used_target_ids.add(home_res.id)

        if exact_ok and len(exact_targets) == len(sorted_group):
            moved_flights += 1
            for a, target in exact_targets:
                a.resource_id = target.id
                moved_alloc_count += 1
                reserved.setdefault(target.id, []).append((s, e))
            continue

        # 2) Fallback: если точный возврат невозможен, возвращаем на родной остров рядом.
        preferred_nums = []
        for a in group:
            home_res_id = original_map.get(a.id)
            if home_res_id is None:
                continue
            n = _counter_num(by_id.get(home_res_id).name if by_id.get(home_res_id) else "")
            if n is not None:
                preferred_nums.append(n)
        free = [r for r in home_pool if is_free(r.id, s, e, ignore)]
        chosen = _choose_nearby_counters(free, need, preferred_nums)
        if len(chosen) < need:
            failed_flights += 1
            continue
        moved_flights += 1
        for i in range(len(sorted_group)):
            a = sorted_group[i]
            target = chosen[i]
            a.resource_id = target.id
            moved_alloc_count += 1
            reserved.setdefault(target.id, []).append((s, e))

    ev.status = "repaired"
    ev.repaired_at = utc_now()
    ev.note = (
        f"Починка выполнена частично: {failed_flights} рейс(ов) не удалось вернуть на свой остров."
        if failed_flights > 0
        else "Поломка устранена, рейсы возвращены на свой остров."
    )
    db.commit()
    return moved_alloc_count, moved_flights, failed_flights


@router.get("/history", response_model=list[BreakdownEventOut])
def list_breakdown_history(db: Session = Depends(get_db)):
    rows = db.query(BreakdownEvent).order_by(BreakdownEvent.created_at.desc()).all()
    return [_event_to_out(x) for x in rows]


@router.post("/start", response_model=BreakdownActionOut)
def start_breakdown(body: BreakdownStartIn, db: Session = Depends(get_db)):
    res = db.query(Resource).filter(Resource.id == body.checkin_resource_id).first()
    if not res:
        raise HTTPException(404, "Стойка не найдена")
    island = _island_of_resource(res)
    if island is None:
        raise HTTPException(422, "Выбранный ресурс не относится к стойкам 1-43")
    target = 2 if island == 1 else 1

    ev = BreakdownEvent(
        id=f"bd-{uuid.uuid4().hex[:12]}",
        kind=body.kind,
        kind_label=_kind_label(body.kind),
        broken_resource_id=res.id,
        broken_counter_name=str(res.name),
        broken_island=island,
        target_island=target,
        status="active",
        moves_json="[]",
        moved_allocation_ids_json="[]",
        original_by_allocation_id_json="{}",
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)

    moved_allocs, moved_flights, failed = _run_reconcile_for_event(db, ev)
    db.refresh(ev)
    return BreakdownActionOut(
        ok=True,
        event=_event_to_out(ev),
        moved_allocations=moved_allocs,
        moved_flights=moved_flights,
        failed_flights=failed,
    )


@router.post("/reconcile", response_model=BreakdownReconcileOut)
def reconcile_breakdowns(db: Session = Depends(get_db)):
    active = db.query(BreakdownEvent).filter(BreakdownEvent.status == "active").order_by(BreakdownEvent.created_at.asc()).all()
    total_allocs = 0
    total_flights = 0
    touched = 0
    for ev in active:
        moved_allocs, moved_flights, _ = _run_reconcile_for_event(db, ev)
        if moved_allocs > 0:
            touched += 1
        total_allocs += moved_allocs
        total_flights += moved_flights
    return BreakdownReconcileOut(
        ok=True,
        total_moved_allocations=total_allocs,
        total_moved_flights=total_flights,
        events_touched=touched,
    )


@router.post("/{event_id}/repair", response_model=BreakdownActionOut)
def repair_breakdown(event_id: str = Path(...), db: Session = Depends(get_db)):
    ev = db.query(BreakdownEvent).filter(BreakdownEvent.id == event_id).first()
    if not ev:
        raise HTTPException(404, "Поломка не найдена")
    if ev.status != "active":
        return BreakdownActionOut(ok=True, event=_event_to_out(ev), moved_allocations=0, moved_flights=0, failed_flights=0)
    moved_allocs, moved_flights, failed = _run_repair_for_event(db, ev)
    db.refresh(ev)
    return BreakdownActionOut(
        ok=True,
        event=_event_to_out(ev),
        moved_allocations=moved_allocs,
        moved_flights=moved_flights,
        failed_flights=failed,
    )

