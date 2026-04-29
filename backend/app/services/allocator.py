"""
Автоматическая аллокация ресурсов (greedy interval scheduling + batch для стойки регистрации).

Ключевые требования:
- Динамическое время: если is_delayed==1 и есть estimated_time (EAT) — используем EAT, иначе plan_time.
- Окна:
  Departures:
    - Check-in: T-3:00 до T-0:40
    - Gate:     T-0:40 до T
  Arrivals:
    - Gate:     T до T+0:45
- Batch для check-in: нужно выделить сразу N стоек (pool).
- Исключение: для общих ресурсов (Drop-off) допускаем перекрытия.

Про сложность (для защиты диплома):
Пусть:
  F — количество рейсов
  R — количество ресурсов заданного типа
  A — количество уже существующих аллокаций
Мы строим расписания ресурсов (интервальные списки) за O(A log A) на сортировку,
а далее для каждого рейса делаем поиск доступных ресурсов:
  - gate: перебор ресурсов до нахождения свободного, проверка пересечения O(log k)
  - check-in: подбор пула N стоек (в худшем R * log k, но обычно быстро из-за малых N)

Итого ориентировочно: O(A log A + F * R * log K), где K — среднее число интервалов на ресурс.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from bisect import bisect_left

from sqlalchemy.orm import Session

from app.models.flight import Flight, FlightType
from app.models.resource import Resource, ResourceType
from app.models.allocation import Allocation, AllocationType


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime


def effective_time(flight: Flight) -> datetime | None:
    """
    Выбор базового времени T согласно требованиям:
    - если is_delayed=True и estimated_time задано -> estimated_time
    - иначе plan_time
    - иначе scheduled_departure (legacy)
    """
    if flight.is_delayed and flight.estimated_time:
        return flight.estimated_time
    return flight.plan_time or flight.scheduled_departure


def default_time_window(flight: Flight, resource_type: ResourceType) -> tuple[datetime | None, datetime | None]:
    """
    Возвращает (start, end) для конкретного рейса и типа ресурса.
    """
    t = effective_time(flight)
    if not t:
        return None, None

    if flight.flight_type == FlightType.DEPARTURE:
        if resource_type == ResourceType.CHECK_IN:
            return t - timedelta(hours=3), t - timedelta(minutes=40)
        if resource_type == ResourceType.GATE:
            return t - timedelta(minutes=40), t
        return None, None

    # arrival
    if resource_type == ResourceType.GATE:
        return t, t + timedelta(minutes=45)
    return None, None


def _is_shared(resource: Resource) -> bool:
    specs = resource.specifications or {}
    if specs.get("is_shared") is True:
        return True
    role = (specs.get("role") or "").lower()
    if role in {"drop-off", "dropoff", "common"}:
        return True
    name = (resource.name or "").lower()
    if "drop" in name:
        return True
    return False


class ResourceSchedule:
    """
    Хранит интервалы аллокаций для одного ресурса в отсортированном виде.
    Проверка пересечения выполняется за O(log n) с помощью bisect.

    Мы используем полуинтервалы [start, end), поэтому касание границ не считается конфликтом.
    """

    def __init__(self, shared: bool):
        self.shared = shared
        self._starts: list[datetime] = []
        self._ends: list[datetime] = []

    def add(self, start: datetime, end: datetime):
        # вставка в отсортированное место по start
        i = bisect_left(self._starts, start)
        self._starts.insert(i, start)
        self._ends.insert(i, end)

    def overlaps(self, start: datetime, end: datetime) -> bool:
        if self.shared:
            return False
        i = bisect_left(self._starts, start)
        # Проверяем соседние интервалы: i-1 и i
        for j in (i - 1, i):
            if 0 <= j < len(self._starts):
                s2 = self._starts[j]
                e2 = self._ends[j]
                if start < e2 and end > s2:
                    return True
        return False


def _counter_number(name: str) -> int | None:
    m = re.fullmatch(r"\s*(\d+)\s*", name or "")
    return int(m.group(1)) if m else None


def required_checkin_counters(flight: Flight) -> int:
    """
    Эвристика для N (сколько стоек регистрации нужно рейсу).
    В реальных системах это функция вместимости/ожидаемого потока.

    Для диплома достаточно простой и объяснимой модели:
    - если passengers_count задано: ceil(passengers/60), ограничим [1..4]
    - иначе по типу ВС: wide-body => 4, иначе 2
    """
    if flight.passengers_count and flight.passengers_count > 0:
        n = (flight.passengers_count + 59) // 60
        return max(1, min(4, n))

    aircraft = (flight.aircraft_type or "").upper()
    wide_markers = ["A330", "A350", "A380", "B777", "B787", "B747"]
    if any(m in aircraft for m in wide_markers):
        return 4
    return 2


@dataclass(frozen=True)
class AllocationResult:
    successes: list[dict]
    conflicts: list[dict]
    auto_allocations_created: int


def _build_schedules(db: Session, resources: list[Resource]) -> dict[int, ResourceSchedule]:
    """
    Загружаем существующие аллокации для указанных ресурсов и строим расписания.
    """
    resource_ids = [r.id for r in resources]
    schedules: dict[int, ResourceSchedule] = {r.id: ResourceSchedule(shared=_is_shared(r)) for r in resources}
    if not resource_ids:
        return schedules

    existing = (
        db.query(Allocation)
        .filter(Allocation.resource_id.in_(resource_ids))
        .order_by(Allocation.resource_id, Allocation.start_time)
        .all()
    )
    for a in existing:
        schedules[a.resource_id].add(a.start_time, a.end_time)
    return schedules


def _has_manual_for_type(db: Session, flight_id: int, resource_type: ResourceType) -> bool:
    """
    Если парсер уже создал MANUAL аллокации для ресурса этого типа — AUTO для этого типа не делаем.
    """
    return (
        db.query(Allocation)
        .join(Resource, Resource.id == Allocation.resource_id)
        .filter(
            Allocation.flight_id == flight_id,
            Allocation.allocation_type == AllocationType.MANUAL,
            Resource.resource_type == resource_type,
        )
        .first()
        is not None
    )


def allocate_all(db: Session, *, replace_auto: bool = True) -> AllocationResult:
    """
    Запускает автоматическую аллокацию для всех рейсов в БД.

    replace_auto=True:
      - удаляем предыдущие AUTO аллокации (manual сохраняем),
      - затем пересчитываем.
    """
    if replace_auto:
        db.query(Allocation).filter(Allocation.allocation_type == AllocationType.AUTO).delete()
        db.commit()

    flights = db.query(Flight).order_by(Flight.flight_type, Flight.plan_time).all()
    resources = db.query(Resource).filter(Resource.is_active == True).order_by(Resource.resource_type, Resource.name).all()

    resources_by_type: dict[ResourceType, list[Resource]] = {t: [] for t in ResourceType}
    for r in resources:
        resources_by_type[r.resource_type].append(r)

    schedules_by_type: dict[ResourceType, dict[int, ResourceSchedule]] = {}
    for rtype, rlist in resources_by_type.items():
        schedules_by_type[rtype] = _build_schedules(db, rlist)

    successes: list[dict] = []
    conflicts: list[dict] = []
    auto_created = 0

    for f in flights:
        t = effective_time(f)
        if not t:
            # Невозможно рассчитать окно без времени
            continue

        if f.flight_type == FlightType.DEPARTURE:
            # Check-in (pool)
            if not _has_manual_for_type(db, f.id, ResourceType.CHECK_IN):
                start, end = default_time_window(f, ResourceType.CHECK_IN)
                if start and end:
                    n = required_checkin_counters(f)
                    allocated = _allocate_checkin_pool(
                        db,
                        flight=f,
                        start=start,
                        end=end,
                        required=n,
                        resources=resources_by_type.get(ResourceType.CHECK_IN, []),
                        schedules=schedules_by_type[ResourceType.CHECK_IN],
                    )
                    if allocated is None:
                        conflicts.append(
                            dict(
                                flight_number=f.flight_number,
                                flight_type=f.flight_type.value,
                                resource_type=ResourceType.CHECK_IN,
                                start_time=start,
                                end_time=end,
                                required_count=n,
                                reason="Не удалось найти свободный пул стоек регистрации",
                            )
                        )
                    else:
                        auto_created += len(allocated)
                        successes.append(
                            dict(
                                flight_id=f.id,
                                flight_number=f.flight_number,
                                flight_type=f.flight_type.value,
                                resource_type=ResourceType.CHECK_IN,
                                resource_names=[r.name for r in allocated],
                                start_time=start,
                                end_time=end,
                                allocation_type=AllocationType.AUTO,
                            )
                        )

            # Gate
            if not _has_manual_for_type(db, f.id, ResourceType.GATE):
                start, end = default_time_window(f, ResourceType.GATE)
                if start and end:
                    gate = _allocate_single(
                        db,
                        flight=f,
                        resource_type=ResourceType.GATE,
                        start=start,
                        end=end,
                        resources=resources_by_type.get(ResourceType.GATE, []),
                        schedules=schedules_by_type[ResourceType.GATE],
                    )
                    if gate is None:
                        conflicts.append(
                            dict(
                                flight_number=f.flight_number,
                                flight_type=f.flight_type.value,
                                resource_type=ResourceType.GATE,
                                start_time=start,
                                end_time=end,
                                required_count=1,
                                reason="Нет свободного гейта на требуемый интервал",
                            )
                        )
                    else:
                        auto_created += 1
                        successes.append(
                            dict(
                                flight_id=f.id,
                                flight_number=f.flight_number,
                                flight_type=f.flight_type.value,
                                resource_type=ResourceType.GATE,
                                resource_names=[gate.name],
                                start_time=start,
                                end_time=end,
                                allocation_type=AllocationType.AUTO,
                            )
                        )

        else:
            # Прилёты: только гейт (ленты выдачи багажа в проекте не используются)
            if not _has_manual_for_type(db, f.id, ResourceType.GATE):
                start, end = default_time_window(f, ResourceType.GATE)
                if start and end:
                    gate = _allocate_single(
                        db,
                        flight=f,
                        resource_type=ResourceType.GATE,
                        start=start,
                        end=end,
                        resources=resources_by_type.get(ResourceType.GATE, []),
                        schedules=schedules_by_type[ResourceType.GATE],
                    )
                    if gate is None:
                        conflicts.append(
                            dict(
                                flight_number=f.flight_number,
                                flight_type=f.flight_type.value,
                                resource_type=ResourceType.GATE,
                                start_time=start,
                                end_time=end,
                                required_count=1,
                                reason="Нет свободного гейта для прилёта",
                            )
                        )
                    else:
                        auto_created += 1
                        successes.append(
                            dict(
                                flight_id=f.id,
                                flight_number=f.flight_number,
                                flight_type=f.flight_type.value,
                                resource_type=ResourceType.GATE,
                                resource_names=[gate.name],
                                start_time=start,
                                end_time=end,
                                allocation_type=AllocationType.AUTO,
                            )
                        )

    db.commit()
    return AllocationResult(
        successes=successes,
        conflicts=conflicts,
        auto_allocations_created=auto_created,
    )


def _allocate_single(
    db: Session,
    *,
    flight: Flight,
    resource_type: ResourceType,
    start: datetime,
    end: datetime,
    resources: list[Resource],
    schedules: dict[int, ResourceSchedule],
) -> Resource | None:
    """
    Жадно выбираем первый ресурс без конфликта.
    """
    for r in resources:
        sched = schedules[r.id]
        if not sched.overlaps(start, end):
            db.add(
                Allocation(
                    flight_id=flight.id,
                    resource_id=r.id,
                    start_time=start,
                    end_time=end,
                    allocation_type=AllocationType.AUTO,
                )
            )
            sched.add(start, end)
            return r
    return None


def _allocate_checkin_pool(
    db: Session,
    *,
    flight: Flight,
    start: datetime,
    end: datetime,
    required: int,
    resources: list[Resource],
    schedules: dict[int, ResourceSchedule],
) -> list[Resource] | None:
    """
    Находим пул из `required` свободных стоек регистрации.

    Реализация:
    - сортируем стойки по числовому имени (17,18,19...) чтобы предпочитать “рядом стоящие”
    - затем скользящим окном ищем contiguous-пакет длиной required, где все стойки свободны
    - если contiguous не найден — берём любые required свободных

    Это удовлетворяет «batch allocation» (стоек должно быть несколько одновременно),
    и даёт реалистичное поведение (соседние стойки удобнее).
    """
    counters = []
    for r in resources:
        num = _counter_number(r.name)
        counters.append((num if num is not None else 10**9, r))
    counters.sort(key=lambda x: (x[0], x[1].name))
    ordered = [r for _, r in counters]

    # 1) contiguous попытка
    numeric = [( _counter_number(r.name), r) for r in ordered]
    for i in range(0, len(numeric) - required + 1):
        window = numeric[i : i + required]
        nums = [n for n, _ in window]
        if any(n is None for n in nums):
            continue
        if max(nums) - min(nums) != required - 1:
            continue
        if all(not schedules[r.id].overlaps(start, end) for _, r in window):
            chosen = [r for _, r in window]
            for r in chosen:
                db.add(
                    Allocation(
                        flight_id=flight.id,
                        resource_id=r.id,
                        start_time=start,
                        end_time=end,
                        allocation_type=AllocationType.AUTO,
                    )
                )
                schedules[r.id].add(start, end)
            return chosen

    # 2) любые свободные
    chosen: list[Resource] = []
    for r in ordered:
        if not schedules[r.id].overlaps(start, end):
            chosen.append(r)
            if len(chosen) == required:
                break
    if len(chosen) != required:
        return None

    for r in chosen:
        db.add(
            Allocation(
                flight_id=flight.id,
                resource_id=r.id,
                start_time=start,
                end_time=end,
                allocation_type=AllocationType.AUTO,
            )
        )
        schedules[r.id].add(start, end)
    return chosen

