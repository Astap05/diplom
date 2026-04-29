"""
Парсер реальных XML-дампов аэропорта (arrival/departure).

Цели:
- распарсить `<BLOCK>` в Flight сущности
- распарсить назначенные ресурсы из XML (numbers_reg, numbers_gate)
- объединить CodeShare рейсы в один "физический" рейс, чтобы не плодить дубликаты в БД

Технологии: xml.etree.ElementTree (stdlib).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.flight import Flight, FlightType
from app.models.resource import Resource, ResourceType
from app.models.allocation import Allocation, AllocationType
from app.services.utils import clean_text, parse_ddmm_hhmm, parse_ddmmyyyy_hhmmss, split_codeshares, normalize_codeshares


@dataclass(frozen=True)
class ParseStats:
    parsed_flights: int
    parsed_resources: int
    created_manual_allocations: int


def _resolve_path(path_value: str) -> Path:
    """
    Пытаемся найти XML по нескольким вариантам путей:
    - абсолютный путь
    - относительно текущей рабочей директории (обычно backend/)
    - относительно родителя (workspace root), если XML лежит рядом с backend/
    """
    p = Path(path_value)
    if p.is_absolute() and p.exists():
        return p
    # relative to cwd
    p1 = Path.cwd() / path_value
    if p1.exists():
        return p1
    # relative to workspace root (../)
    p2 = Path.cwd().parent / path_value
    if p2.exists():
        return p2
    return p  # пусть дальше упадёт с понятной ошибкой


def _root_now_year(root: ET.Element) -> int:
    """
    Берём год из `<FLIGHT_LIST now="YYYY-MM-DDTHH:MM:SS.sss">`.
    """
    now_val = root.attrib.get("now")
    if not now_val:
        return datetime.utcnow().year
    try:
        dt = datetime.fromisoformat(now_val)
        return dt.year
    except Exception:
        return datetime.utcnow().year


def _iter_blocks(root: ET.Element) -> Iterable[ET.Element]:
    # Формат в ваших данных: <FLIGHT_LIST><BLOCK>...</BLOCK><BLOCK>...</BLOCK>...</FLIGHT_LIST>
    return root.findall(".//BLOCK")


def _get_text(block: ET.Element, tag: str) -> str | None:
    el = block.find(tag)
    return clean_text(el.text if el is not None else None)


def _extract_departure_resources(block: ET.Element) -> tuple[list[str], list[str]]:
    """
    Для departure XML:
    - numbers_reg/item@caption => стойки регистрации
    - numbers_gate/item@caption => выходы на посадку
    """
    regs: list[str] = []
    gates: list[str] = []
    nr = block.find("numbers_reg")
    if nr is not None:
        for item in nr.findall(".//item"):
            cap = clean_text(item.attrib.get("caption"))
            if cap:
                regs.append(cap)
    ng = block.find("numbers_gate")
    if ng is not None:
        for item in ng.findall(".//item"):
            cap = clean_text(item.attrib.get("caption"))
            if cap:
                gates.append(cap)
    return regs, gates


def _extract_arrival_gate(block: ET.Element) -> str | None:
    """Для arrival XML: номер/название гейта (часто число)."""
    return _get_text(block, "gate")


def _find_existing_flight(
    db: Session,
    flight_number: str,
    flight_type: FlightType,
    plan_time: datetime | None,
) -> Flight | None:
    """
    Upsert-ключ на уровне проекта (упрощённо):
    - flight_number + flight_type + plan_time.

    В production лучше хранить внешний flight_id, но в требованиях диплома его нет в схеме.
    """
    q = db.query(Flight).filter(
        Flight.flight_number == flight_number,
        Flight.flight_type == flight_type,
    )
    if plan_time is None:
        q = q.filter(Flight.plan_time.is_(None))
    else:
        q = q.filter(Flight.plan_time == plan_time)
    return q.first()


def _get_or_create_resource(
    db: Session,
    *,
    resource_type: ResourceType,
    name: str,
    zone: str | None = None,
    specifications: dict | None = None,
) -> tuple[Resource, bool]:
    existing = (
        db.query(Resource)
        .filter(Resource.resource_type == resource_type, Resource.name == name)
        .first()
    )
    if existing:
        # мягкое обновление зоны/спецификаций
        if zone and not existing.zone:
            existing.zone = zone
        if specifications:
            existing.specifications = {**(existing.specifications or {}), **specifications}
        return existing, False

    r = Resource(
        resource_type=resource_type,
        name=name,
        zone=zone,
        is_active=True,
        specifications=specifications or {},
    )
    db.add(r)
    db.flush()  # получить id без коммита
    return r, True


def parse_and_upsert_from_xml(
    db: Session,
    *,
    arrival_xml_path: str | None = None,
    departure_xml_path: str | None = None,
) -> ParseStats:
    """
    Основной вход: читает arrival + departure XML, обновляет Flights/Resources,
    создаёт MANUAL-аллокации для тех ресурсов, которые уже назначены в XML.

    Временные окна MANUAL-аллокаций берём по тем же правилам, что и для AUTO,
    чтобы визуализация была сопоставима.
    """
    settings = get_settings()
    arrival_path = _resolve_path(arrival_xml_path or settings.ARRIVAL_XML_PATH)
    departure_path = _resolve_path(departure_xml_path or settings.DEPARTURE_XML_PATH)

    if not arrival_path.exists():
        raise FileNotFoundError(f"Arrival XML не найден: {arrival_path}")
    if not departure_path.exists():
        raise FileNotFoundError(f"Departure XML не найден: {departure_path}")

    parsed_flights = 0
    parsed_resources = 0
    created_manual_allocations = 0

    # Важно для повторных запусков allocate:
    # MANUAL-аллокации у нас сейчас отражают назначения из XML-дампа.
    # Поэтому перед новой загрузкой делаем импорт идемпотентным — очищаем старые MANUAL,
    # иначе при каждом запуске будут накапливаться одинаковые записи и UI покажет “дубли”.
    db.query(Allocation).filter(Allocation.allocation_type == AllocationType.MANUAL).delete(synchronize_session=False)
    db.flush()

    # Сначала читаем оба XML, чтобы построить alias->primary map по CodeShare
    alias_to_primary: dict[str, str] = {}
    codes_for_primary: dict[str, set[str]] = {}

    def scan_aliases(root: ET.Element):
        for block in _iter_blocks(root):
            primary = _get_text(block, "flight")
            if not primary:
                continue
            cs = split_codeshares(_get_text(block, "CodeShare"))
            if cs:
                codes_for_primary.setdefault(primary, set()).update(cs)
                for alias in cs:
                    alias_to_primary.setdefault(alias, primary)

    arrival_root = ET.parse(arrival_path).getroot()
    departure_root = ET.parse(departure_path).getroot()
    scan_aliases(arrival_root)
    scan_aliases(departure_root)

    # Дальше — реальная загрузка
    def process(root: ET.Element, flight_type: FlightType):
        nonlocal parsed_flights, parsed_resources, created_manual_allocations
        year = _root_now_year(root)

        for block in _iter_blocks(root):
            raw_flight_number = _get_text(block, "flight")
            if not raw_flight_number:
                continue
            flight_number = alias_to_primary.get(raw_flight_number, raw_flight_number)

            plan_time = parse_ddmm_hhmm(_get_text(block, "plan"), reference_year=year)
            eat_time = parse_ddmm_hhmm(_get_text(block, "EAT"), reference_year=year)
            fact_time = parse_ddmm_hhmm(_get_text(block, "fact"), reference_year=year)
            delayed_to = parse_ddmmyyyy_hhmmss(_get_text(block, "DelayedTo"))
            is_delayed = _get_text(block, "isDelayed")
            delayed_flag = bool(is_delayed and is_delayed.strip() == "1")
            is_cancelled = bool((_get_text(block, "isCanseled") or "").strip() == "1")

            airline = _get_text(block, "airline") or "UNKNOWN"
            aircraft = _get_text(block, "aircraft") or "UNKNOWN"
            status_raw = _get_text(block, "status") or None
            status_tablo = _get_text(block, "status_tablo") or None
            status_tablo_en = _get_text(block, "status_tablo_en") or None

            airport = _get_text(block, "airport") or None
            ru_airport = _get_text(block, "ru_airport") or None
            en_airport = _get_text(block, "en_airport") or None

            external_flight_id = _get_text(block, "flight_id") or None

            # Собираем codeshares: те, что в CodeShare + если блок сам был alias
            cs_codes = set(split_codeshares(_get_text(block, "CodeShare")))
            if raw_flight_number != flight_number:
                cs_codes.add(raw_flight_number)
            cs_codes.update(codes_for_primary.get(flight_number, set()))
            code_shares_str = normalize_codeshares(flight_number, sorted(cs_codes))

            existing = _find_existing_flight(db, flight_number, flight_type, plan_time)
            if existing is None:
                f = Flight(
                    flight_number=flight_number,
                    airline=airline,
                    aircraft_type=aircraft,
                    scheduled_departure=plan_time,
                    external_flight_id=external_flight_id,
                    plan_time=plan_time,
                    estimated_time=eat_time,
                    fact_time=fact_time,
                    delayed_to=delayed_to,
                    is_delayed=delayed_flag,
                    is_cancelled=is_cancelled,
                    flight_type=flight_type,
                    code_shares=code_shares_str,
                    airport=airport,
                    ru_airport=ru_airport,
                    en_airport=en_airport,
                    status_raw=status_raw,
                    status_tablo=status_tablo,
                    status_tablo_en=status_tablo_en,
                    # status: в XML статус в RU; в дипломной схеме — enum, поэтому пока оставляем scheduled.
                    passengers_count=0,
                )
                db.add(f)
                db.flush()
                flight = f
            else:
                existing.airline = airline
                existing.aircraft_type = aircraft
                existing.scheduled_departure = existing.scheduled_departure or plan_time
                existing.external_flight_id = external_flight_id or existing.external_flight_id
                existing.plan_time = plan_time
                existing.estimated_time = eat_time
                existing.fact_time = fact_time
                existing.delayed_to = delayed_to
                existing.is_delayed = delayed_flag
                existing.is_cancelled = is_cancelled
                existing.flight_type = flight_type
                existing.code_shares = code_shares_str
                existing.airport = airport
                existing.ru_airport = ru_airport
                existing.en_airport = en_airport
                existing.status_raw = status_raw
                existing.status_tablo = status_tablo
                existing.status_tablo_en = status_tablo_en
                flight = existing

            parsed_flights += 1

            # Ресурсы и MANUAL allocations из XML
            if flight_type == FlightType.DEPARTURE:
                regs, gates = _extract_departure_resources(block)

                # check-in counters
                for rname in regs:
                    specs = {}
                    # Правило из требований: стойка "21" — общий Drop-off, допускает пересечения.
                    if rname.strip() == "21":
                        specs = {"is_shared": True, "role": "drop-off"}
                    res, created = _get_or_create_resource(
                        db,
                        resource_type=ResourceType.CHECK_IN,
                        name=rname,
                        specifications=specs,
                    )
                    parsed_resources += 1 if created else 0

                    # manual allocation (окно для check-in считаем по plan/EAT)
                    start, end = _default_time_window(flight, ResourceType.CHECK_IN)
                    if start and end:
                        # защита от дублей внутри одного запуска (на случай повторов в XML)
                        exists = (
                            db.query(Allocation.id)
                            .filter(
                                Allocation.flight_id == flight.id,
                                Allocation.resource_id == res.id,
                                Allocation.start_time == start,
                                Allocation.end_time == end,
                                Allocation.allocation_type == AllocationType.MANUAL,
                            )
                            .first()
                        )
                        if not exists:
                            db.add(
                                Allocation(
                                    flight_id=flight.id,
                                    resource_id=res.id,
                                    start_time=start,
                                    end_time=end,
                                    allocation_type=AllocationType.MANUAL,
                                )
                            )
                            created_manual_allocations += 1

                # gate(s)
                for gname in gates:
                    res, created = _get_or_create_resource(
                        db,
                        resource_type=ResourceType.GATE,
                        name=gname,
                    )
                    parsed_resources += 1 if created else 0
                    start, end = _default_time_window(flight, ResourceType.GATE)
                    if start and end:
                        exists = (
                            db.query(Allocation.id)
                            .filter(
                                Allocation.flight_id == flight.id,
                                Allocation.resource_id == res.id,
                                Allocation.start_time == start,
                                Allocation.end_time == end,
                                Allocation.allocation_type == AllocationType.MANUAL,
                            )
                            .first()
                        )
                        if not exists:
                            db.add(
                                Allocation(
                                    flight_id=flight.id,
                                    resource_id=res.id,
                                    start_time=start,
                                    end_time=end,
                                    allocation_type=AllocationType.MANUAL,
                                )
                            )
                            created_manual_allocations += 1

            else:
                gate = _extract_arrival_gate(block)
                if gate:
                    res, created = _get_or_create_resource(
                        db,
                        resource_type=ResourceType.GATE,
                        name=gate,
                    )
                    parsed_resources += 1 if created else 0
                    start, end = _default_time_window(flight, ResourceType.GATE)
                    if start and end:
                        exists = (
                            db.query(Allocation.id)
                            .filter(
                                Allocation.flight_id == flight.id,
                                Allocation.resource_id == res.id,
                                Allocation.start_time == start,
                                Allocation.end_time == end,
                                Allocation.allocation_type == AllocationType.MANUAL,
                            )
                            .first()
                        )
                        if not exists:
                            db.add(
                                Allocation(
                                    flight_id=flight.id,
                                    resource_id=res.id,
                                    start_time=start,
                                    end_time=end,
                                    allocation_type=AllocationType.MANUAL,
                                )
                            )
                            created_manual_allocations += 1

    # Импорт внутри файла, чтобы избежать циклов (xml_parser -> allocator).
    from app.services.allocator import default_time_window as _default_time_window

    process(departure_root, FlightType.DEPARTURE)
    process(arrival_root, FlightType.ARRIVAL)

    # Важно: коммит делаем один раз — так быстрее и транзакционно.
    db.commit()
    return ParseStats(
        parsed_flights=parsed_flights,
        parsed_resources=parsed_resources,
        created_manual_allocations=created_manual_allocations,
    )

