"""POST /distribution/run — генерация плановых рейсов и назначений по нормам."""

from __future__ import annotations

from collections import defaultdict, Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, date
import glob
import hashlib
import json
import logging
import os
import re
import time

from fastapi import APIRouter, Depends, HTTPException
import numpy as np
import pandas as pd
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.flight import Flight, FlightType, FlightStatus
from app.models.resource import Resource, ResourceType
from app.models.allocation import Allocation, AllocationType
from app.models.checkin_norm import CheckinNorm
from app.models.gate_norm import GateNorm
from app.schemas.distribution import DistributionRunRequest, DistributionRunResponse
from app.services.aircraft_seats_catalog import resolve_seat_capacity
from app.airport_time import TIME_SHIFT_HOURS

router = APIRouter()
logger = logging.getLogger(__name__)

DEFAULT_FORECAST_GLOB = r"C:\Users\Admin\diplom\Выгрузки\*.xls"

# Прогноз: последние выгрузки (по имени файла после сортировки) — «шпаргалка» под актуальное расписание.
FORECAST_RECENT_FILE_COUNT = 2
FORECAST_WEIGHT_RECENT = 0.65
FORECAST_WEIGHT_ALL = 0.35
# Нижний порог p_eff: ниже — рейс не попадает в прогноз вообще (даже через ролл).
FORECAST_MIN_P_EFF = 0.18
# Порог на p_eff: выше — рейс в каждый подходящий день; ниже — детерминированный ролл.
FORECAST_TH_ALWAYS_EFF = 0.31
# Без строк в последних выгрузках: нужны и повторяемость по годам, и достаточная доля дней в срезе.
FORECAST_MIN_P_ALL_WITHOUT_RECENT = 0.18
# Жёстко: без исключений — иначе в Excel остаются строки с p_all 0.06…0.09 за счёт «сильного недавнего».
FORECAST_MIN_P_ALL = 0.18
FORECAST_RULES_VERSION = "2026-03-28-strict_p_all_p_eff_0.18"

# TIME_SHIFT_HOURS: app.airport_time (единая константа для расписания и поломок стоек)


def _forecast_profile_kept(
    p_all: float,
    p_eff: float,
) -> bool:
    if p_eff < FORECAST_MIN_P_EFF:
        return False
    if p_all < FORECAST_MIN_P_ALL:
        return False
    return True


def _parse_day(s: str) -> datetime:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(422, f"Неверная дата (ожидается YYYY-MM-DD): {s}") from e


def _date_only(dt: datetime | None) -> date | None:
    return dt.date() if dt else None


def _norm_active(valid_from: date | None, valid_to: date | None, d: date) -> bool:
    if valid_from and d < valid_from:
        return False
    if valid_to and d > valid_to:
        return False
    return True


def _split_codes(s: str | None) -> set[str]:
    if not s:
        return set()
    return {x.strip().upper() for x in s.split(",") if x.strip()}


def _apply_airline_filter(query, names: list[str]):
    names_n = {_norm_airline(n) for n in names if n.strip()}
    if not names_n:
        return query
    # Для SQLite/кириллицы фильтруем в Python, т.к. lower()/nocase ненадёжны.
    return [row for row in query.all() if _norm_airline(getattr(row, "airline", "")) in names_n]


def _norm_airline(s: str | None) -> str:
    return " ".join((s or "").strip().casefold().split())


def _flight_code(f: Flight) -> str:
    m = re.match(r"^([A-Za-z0-9]{2})", (f.flight_number or "").strip())
    return (m.group(1).upper() if m else "")


def _airport_blob(f: Flight) -> str:
    return " ".join([f.airport or "", f.ru_airport or "", f.en_airport or ""]).upper()


def _is_winter(d: date) -> bool:
    # Зима: последнее воскресенье октября -> последняя суббота марта.
    year = d.year
    oct31 = date(year, 10, 31)
    last_sun_oct = oct31 - timedelta(days=(oct31.weekday() + 1) % 7)
    mar31 = date(year, 3, 31)
    last_sat_mar = mar31 - timedelta(days=(mar31.weekday() - 5) % 7)
    if d >= last_sun_oct:
        return True
    if d <= last_sat_mar:
        return True
    return False


def _season_of(d: date) -> str:
    return "winter" if _is_winter(d) else "summer"


def _minute_of_day(dt_value: datetime | None) -> int:
    if not dt_value:
        return 0
    return dt_value.hour * 60 + dt_value.minute


def _stable_unit_rand(key: str) -> float:
    # Стабильный "рандом" в [0..1): одинаковый key => одинаковый результат.
    h = hashlib.md5(key.encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _parse_counter_set(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and np.isnan(v):
        return ""
    s = str(v).strip()
    if not s:
        return ""
    nums = sorted(set(int(x) for x in re.findall(r"\d+", s)))
    return "-".join(str(x) for x in nums)


def _parse_named_resource_set(v: object) -> str:
    """
    Нормализация набора именованных ресурсов (например, выходов на посадку):
    "B2, E10A" -> "B2-E10A"
    """
    if v is None:
        return ""
    if isinstance(v, float) and np.isnan(v):
        return ""
    s = str(v).strip()
    if not s:
        return ""
    tokens = re.findall(r"[A-Za-zА-Яа-я]\d+[A-Za-zА-Яа-я]?", s.upper())
    if not tokens:
        return ""
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return "-".join(out)


def _counter_n_from_set(s: str) -> int:
    if not s:
        return 0
    return len([x for x in s.split("-") if x])


def _find_col(cols: list[str], needle_sub: str) -> str | None:
    n = needle_sub.lower()
    for c in cols:
        if n in str(c).lower():
            return c
    return None


def _pick_dep_plan_col(df: pd.DataFrame) -> str | None:
    cols = [str(c) for c in df.columns]
    for n in ["Дата/Время отпр. план", "отпр. план", "вылет план"]:
        c = _find_col(cols, n)
        if c is not None:
            return c
    return None


def _detect_route_cols(df: pd.DataFrame) -> tuple[str | None, str | None]:
    cols = [str(c) for c in df.columns]
    # Приоритет: полные человекочитаемые названия аэропортов из выгрузки.
    c_from = (
        _find_col(cols, "АП Отправления (полное, рус)")
        or _find_col(cols, "Аэропорт отправления")
        or _find_col(cols, "АП отправления")
    )
    c_to = (
        _find_col(cols, "АП Прибытия (полное, рус)")
        or _find_col(cols, "Аэропорт назначения")
        or _find_col(cols, "АП прибытия")
    )
    if c_from and c_to and c_from != c_to:
        return c_from, c_to
    # fallback iata-like columns
    scores: list[tuple[float, float, str]] = []
    for c in cols:
        s = df[c].astype(str).str.strip()
        p_iata = s.str.match(r"^[A-Z]{3}$", na=False).mean()
        if p_iata > 0.5:
            p_msq = (s == "MSQ").mean()
            scores.append((float(p_iata), float(p_msq), c))
    if len(scores) < 2:
        return None, None
    c_from = sorted(scores, key=lambda x: x[1], reverse=True)[0][2]
    rest = [x for x in scores if x[2] != c_from]
    c_to = sorted(rest, key=lambda x: x[1])[0][2] if rest else None
    return c_from, c_to


def _extract_history_rows_from_excel(path: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=0)
    cols = [str(c) for c in raw.columns]

    airline_col = _find_col(cols, "Название АК")
    flight_col = _find_col(cols, "Номер рейса")
    counters_col = _find_col(cols, "Стойки регистрации")
    gates_col = _find_col(cols, "Выходы на посадку")
    pax_total_col = _find_col(cols, "Пассаж. всего")
    pax_biz_col = _find_col(cols, "Пассаж. Бизнес")
    dep_plan_col = _pick_dep_plan_col(raw)
    route_from_col, route_to_col = _detect_route_cols(raw)
    aircraft_col = _find_col(cols, "борт")
    aircraft_type_col = (
        _find_col(cols, "Полное назв ВС (Рус)")
        or _find_col(cols, "Тип ВС (IATA)")
        or _find_col(cols, "Тип ВС")
    )

    if any(x is None for x in [airline_col, flight_col, counters_col, pax_total_col, pax_biz_col, dep_plan_col, route_from_col, route_to_col]):
        return pd.DataFrame()

    df = pd.DataFrame()
    df["airline"] = raw[airline_col].astype(str).str.strip()
    df["flight_no"] = raw[flight_col].astype(str).str.strip()
    df["route_from"] = raw[route_from_col].astype(str).str.strip()
    df["route_to"] = raw[route_to_col].astype(str).str.strip()
    df["direction"] = df["route_from"] + "->" + df["route_to"]
    df["dep_plan_dt"] = pd.to_datetime(raw[dep_plan_col], errors="coerce")
    df["counter_set"] = raw[counters_col].astype(str).apply(_parse_counter_set)
    df["counter_n"] = df["counter_set"].apply(_counter_n_from_set)
    if gates_col is not None:
        df["gate_set"] = raw[gates_col].apply(_parse_named_resource_set)
    else:
        df["gate_set"] = ""
    df["pax_total"] = pd.to_numeric(raw[pax_total_col], errors="coerce")
    df["pax_biz"] = pd.to_numeric(raw[pax_biz_col], errors="coerce")
    df["pax_econ"] = df["pax_total"] - df["pax_biz"]
    df["aircraft_tail"] = raw[aircraft_col].astype(str).str.strip() if aircraft_col else ""
    df["aircraft_type"] = raw[aircraft_type_col].astype(str).str.strip() if aircraft_type_col else ""

    mask = (
        df["dep_plan_dt"].notna()
        & df["counter_set"].ne("")
        & df["pax_total"].notna()
        & df["pax_total"].gt(0)
        & df["direction"].str.contains("->", na=False)
    )
    df = df.loc[mask].copy()
    if len(df) == 0:
        return df
    df["dep_date"] = df["dep_plan_dt"].dt.date
    df["weekday"] = df["dep_plan_dt"].dt.weekday
    df["season"] = df["dep_date"].apply(_season_of)
    df["minute_of_day"] = df["dep_plan_dt"].dt.hour * 60 + df["dep_plan_dt"].dt.minute
    df["airline_norm"] = df["airline"].str.casefold().str.strip()
    df["source_file"] = os.path.basename(path)
    return df


@dataclass
class IntervalSet:
    intervals: list[tuple[datetime, datetime]]

    def overlaps(self, start: datetime, end: datetime) -> bool:
        for s, e in self.intervals:
            if start < e and end > s:
                return True
        return False

    def add(self, start: datetime, end: datetime) -> None:
        self.intervals.append((start, end))


def _counter_num(name: str) -> int:
    m = re.match(r"^\s*(\d+)\s*$", name or "")
    return int(m.group(1)) if m else 10**9


def _pick_checkin_norm(f: Flight, norms: list[CheckinNorm]) -> CheckinNorm | None:
    fd = _date_only(f.plan_time) or _date_only(f.estimated_time)
    if not fd:
        return None
    code = _flight_code(f)
    airport_blob = _airport_blob(f)
    acft = (f.aircraft_type or "").upper()

    candidates: list[tuple[int, int, CheckinNorm]] = []
    for n in norms:
        if not n.is_active or not _norm_active(n.valid_from, n.valid_to, fd):
            continue
        score = 0
        airline_codes = _split_codes(n.airline_codes)
        if airline_codes:
            if code not in airline_codes:
                continue
            score += 4
        if n.airport_codes:
            airports = _split_codes(n.airport_codes)
            if not any(a in airport_blob for a in airports):
                continue
            score += 2
        if n.aircraft_type_code:
            if n.aircraft_type_code.upper() not in acft:
                continue
            score += 1
        candidates.append((score, n.priority, n))

    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[0], x[1], x[2].id))
    return candidates[0][2]


def _pick_gate_norm(f: Flight, norms: list[GateNorm]) -> GateNorm | None:
    fd = _date_only(f.plan_time) or _date_only(f.estimated_time)
    if not fd:
        return None
    code = _flight_code(f)
    acft = (f.aircraft_type or "").upper()

    candidates: list[tuple[int, int, GateNorm]] = []
    for n in norms:
        if not n.is_active or not _norm_active(n.valid_from, n.valid_to, fd):
            continue
        score = 0
        airline_codes = _split_codes(n.airline_codes)
        if airline_codes:
            if code not in airline_codes:
                continue
            score += 3
        if n.aircraft_type_code:
            if n.aircraft_type_code.upper() not in acft:
                continue
            score += 1
        candidates.append((score, n.priority, n))

    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[0], x[1], x[2].id))
    return candidates[0][2]


def _shift_to_date(base: datetime, target: date) -> datetime:
    shifted = datetime(
        target.year,
        target.month,
        target.day,
        base.hour,
        base.minute,
        base.second,
        base.microsecond,
    )
    # Приводим шаблонное время к нужному часовому поясу (например, UTC+3).
    return shifted + timedelta(hours=TIME_SHIFT_HOURS)


def _shift_extra_data(extra_data: str | None, src_dt: datetime | None, target_day: date) -> str | None:
    """
    Переносит дату внутри extra_data для полей-дат, оставляя содержимое по аналогии с историей.
    """
    if not extra_data:
        return None
    try:
        obj = json.loads(extra_data)
    except Exception:
        return extra_data
    if not isinstance(obj, dict):
        return extra_data

    src_date = src_dt.date() if src_dt else None
    date_like_words = ("дата", "time", "время")

    for k, v in list(obj.items()):
        if not isinstance(v, str):
            continue
        lk = str(k).lower()
        if not any(w in lk for w in date_like_words):
            continue
        # Пытаемся распарсить ISO, который из Excel-сериализации мы обычно и храним.
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            continue
        shifted = _shift_to_date(dt, target_day)
        # Если в исходнике было время, сохраняем datetime, иначе date.
        if "T" in v or " " in v:
            obj[k] = shifted.isoformat()
        else:
            obj[k] = shifted.date().isoformat()

    # Технические метки генерации
    obj["generated_by"] = "distribution_run"
    obj["generated_for_date"] = target_day.isoformat()
    if src_date:
        obj["template_source_date"] = src_date.isoformat()
    return json.dumps(obj, ensure_ascii=False)


def _alloc_interval_for_flight(
    f: Flight,
    checkin_norms: list[CheckinNorm],
    gate_norms: list[GateNorm],
) -> dict[str, tuple[datetime, datetime, int, bool]]:
    def _extract_pax_biz_value() -> float | None:
        """
        Берём оценку business-pax из extra_data:
        - forecast_mode: `predicted_pax_biz`
        - import_excel: колонка из Excel `Пассаж. Бизнес` (ключ с русскими символами)
        """
        if not f.extra_data:
            return None
        try:
            obj = json.loads(f.extra_data)
        except Exception:
            return None
        if not isinstance(obj, dict):
            return None

        if "predicted_pax_biz" in obj:
            try:
                return float(obj.get("predicted_pax_biz") or 0)
            except Exception:
                return None

        # Поиск по ключам, содержащим "бизнес" / "business"
        for k, v in obj.items():
            if not isinstance(k, str):
                continue
            kl = k.casefold()
            if "бизнес" not in kl and "business" not in kl:
                continue
            try:
                if isinstance(v, (int, float)) and v is not None:
                    return float(v)
                return float(str(v).replace(",", "."))
            except Exception:
                continue
        return None

    out: dict[str, tuple[datetime, datetime, int, bool]] = {}
    t = f.plan_time or f.estimated_time
    if not t:
        return out

    if f.flight_type == FlightType.DEPARTURE:
        cn = _pick_checkin_norm(f, checkin_norms)
        open_min = cn.open_before_dep_min if cn else 120
        close_min = cn.close_before_dep_min if cn else 40
        cnt = cn.counters_count if cn else 2
        pax_biz = _extract_pax_biz_value()
        # Бизнес-стойка считаем "нужной" только если у рейса реально есть business-пассажиры.
        # Если оценку pax_biz достать не удалось — поведение оставляем как раньше (по нормативу).
        has_biz = bool(
            cn
            and cn.has_business_counter
            and cn.business_counters_count > 0
            and (pax_biz is None or pax_biz > 0)
        )
        out["checkin"] = (t - timedelta(minutes=open_min), t - timedelta(minutes=close_min), max(1, cnt), has_biz)

        gn = _pick_gate_norm(f, gate_norms)
        g_open = gn.open_before_dep_min if gn else 40
        g_close = gn.close_before_dep_min if gn else 15
        g_cnt = gn.gates_count if gn else 1
        out["gate"] = (t - timedelta(minutes=g_open), t - timedelta(minutes=g_close), max(1, g_cnt), False)
    else:
        gn = _pick_gate_norm(f, gate_norms)
        # Для прилёта интерпретируем как после факта: начало/окончание от plan/estimate
        g_start = gn.open_before_dep_min if gn else 0
        g_end = gn.close_before_dep_min if gn else 45
        g_cnt = gn.gates_count if gn else 1
        out["gate"] = (t + timedelta(minutes=g_start), t + timedelta(minutes=max(g_start + 1, g_end)), max(1, g_cnt), False)

    return out


def _choose_resources(
    resources: list[Resource],
    schedules: dict[int, IntervalSet],
    resource_loads: dict[int, int],
    start: datetime,
    end: datetime,
    required: int,
) -> list[Resource]:
    # Балансируем распределение: сначала менее загруженные ресурсы.
    ordered = sorted(resources, key=lambda r: (resource_loads.get(r.id, 0), _counter_num(r.name), r.name))
    free = [r for r in ordered if not schedules[r.id].overlaps(start, end)]
    if len(free) < required:
        return []

    nums = [_counter_num(r.name) for r in free]
    for i in range(0, len(free) - required + 1):
        win = free[i : i + required]
        win_nums = nums[i : i + required]
        if all(n < 10**9 for n in win_nums) and max(win_nums) - min(win_nums) == required - 1:
            return win
    return free[:required]


def _choose_resources_near_reference(
    resources: list[Resource],
    schedules: dict[int, IntervalSet],
    resource_loads: dict[int, int],
    start: datetime,
    end: datetime,
    required: int,
    reference_nums: list[int],
) -> list[Resource]:
    """
    Выбор стоек для добора с приоритетом близости к типовому набору рейса.
    Сначала пытаемся найти непрерывное окно с минимальной "дистанцией" до reference_nums,
    затем fallback на одиночный выбор по близости.
    """
    free = [r for r in resources if not schedules[r.id].overlaps(start, end)]
    if len(free) < required:
        return []

    refs = [n for n in reference_nums if n < 10**9]

    def dist_to_refs(n: int) -> int:
        if n >= 10**9:
            return 10**6
        if not refs:
            return 0
        return min(abs(n - x) for x in refs)

    # 1) Ищем компактное непрерывное окно рядом с reference.
    ordered_by_num = sorted(free, key=lambda r: (_counter_num(r.name), resource_loads.get(r.id, 0), r.name))
    nums = [_counter_num(r.name) for r in ordered_by_num]
    best_win: tuple[int, int, int, list[Resource]] | None = None
    for i in range(0, len(ordered_by_num) - required + 1):
        win = ordered_by_num[i : i + required]
        win_nums = nums[i : i + required]
        if not all(n < 10**9 for n in win_nums):
            continue
        if max(win_nums) - min(win_nums) != required - 1:
            continue
        dist_sum = sum(dist_to_refs(n) for n in win_nums)
        load_sum = sum(resource_loads.get(r.id, 0) for r in win)
        tie_num = min(win_nums)
        score = (dist_sum, load_sum, tie_num, win)
        if best_win is None or score[:3] < best_win[:3]:
            best_win = score
    if best_win is not None:
        return best_win[3]

    # 2) Если непрерывного окна рядом нет — берём самые близкие свободные.
    ordered = sorted(
        free,
        key=lambda r: (dist_to_refs(_counter_num(r.name)), resource_loads.get(r.id, 0), _counter_num(r.name), r.name),
    )
    return ordered[:required]


@router.get("/forecast-options")
def forecast_options(
    db: Session = Depends(get_db),
):
    """
    Возвращает список АК и номеров рейсов из текущих выгрузок.
    Используется в модалке распределения для точечного исключения рейсов.
    """
    if os.path.isdir(os.path.dirname(DEFAULT_FORECAST_GLOB)):
        source_files = sorted(glob.glob(DEFAULT_FORECAST_GLOB))
    else:
        source_files = []
    if not source_files:
        return []

    frames: list[pd.DataFrame] = []
    for p in source_files:
        try:
            fr = _extract_history_rows_from_excel(p)
        except Exception:
            fr = pd.DataFrame()
        if len(fr):
            frames.append(fr)
    if not frames:
        return []

    history_df = pd.concat(frames, ignore_index=True)
    if len(history_df) == 0:
        return []

    grouped = history_df.groupby("airline_norm", dropna=False)
    out: list[dict[str, object]] = []
    for airline_norm, g in grouped:
        an = str(airline_norm or "").strip()
        if not an:
            continue
        airline_mode = Counter(g["airline"].astype(str).tolist()).most_common(1)[0][0]
        flights = sorted({str(x).strip() for x in g["flight_no"].astype(str).tolist() if str(x).strip()})
        if not flights:
            continue
        out.append(
            {
                "airline": str(airline_mode),
                "airline_norm": an,
                "flights": flights,
            }
        )
    out.sort(key=lambda x: str(x["airline"]).casefold())
    return out


@router.post("/run", response_model=DistributionRunResponse)
def run_distribution(body: DistributionRunRequest, db: Session = Depends(get_db)):
    if body.forecast_mode:
        return _run_forecast_distribution(body, db)

    t0 = time.perf_counter()

    d0 = _parse_day(body.date_from)
    d1 = _parse_day(body.date_to)
    if d1 < d0:
        raise HTTPException(422, "date_to раньше date_from")

    names = [n.strip() for n in body.airline_names if n.strip()]

    # Важно: при TIME_SHIFT_HOURS время plan_time может "перетечь" через полночь,
    # а UI фильтрует аллокации по start_time (в пределах выбранного дня).
    # Поэтому, чтобы при повторных запусках не накапливались дубликаты одинаковых
    # окон (особенно заметно на стойке 21), расширяем пересчёт на ±1 день.
    buffer_days = 1 if TIME_SHIFT_HOURS else 0
    start_ext = d0.date() - timedelta(days=buffer_days)
    end_ext = d1.date() + timedelta(days=buffer_days)
    if end_ext < start_ext:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return DistributionRunResponse(
            ok=True,
            message="Выбранный период пуст.",
            flights_in_period=0,
            airlines_considered=0,
            manual_allocations_touched=0,
            duration_ms=duration_ms,
            log=[
                f"Запрошено: {d0.date()} — {d1.date()}.",
            ],
        )

    # Для построения истории/шаблонов берём последний известный plan_time в БД.
    max_plan = db.query(func.max(Flight.plan_time)).scalar()
    if max_plan is None:
        raise HTTPException(422, "В БД нет рейсов с plan_time")

    # История для генерации: последние 8 недель до max_plan.
    source_start = datetime.combine(max_plan.date() - timedelta(days=56), datetime.min.time())
    source_end = datetime.combine(max_plan.date() + timedelta(days=1), datetime.min.time())

    source_q = (
        db.query(Flight)
        .filter(Flight.plan_time >= source_start, Flight.plan_time < source_end)
        .order_by(Flight.plan_time)
    )
    source_flights_all = source_q.all()
    selected_norm = {_norm_airline(n) for n in names if n.strip()}
    source_flights = source_flights_all
    if body.distribution_type == "selected_groups" and selected_norm:
        source_flights = [f for f in source_flights_all if _norm_airline(f.airline) in selected_norm]
        if not source_flights:
            # fallback без 422
            source_flights = source_flights_all

    # Группируем историю по календарной дате.
    source_by_day: dict[date, list[Flight]] = defaultdict(list)
    for f in source_flights:
        if f.plan_time:
            source_by_day[f.plan_time.date()].append(f)

    if not source_by_day:
        raise HTTPException(422, "Нет исторических рейсов для генерации")

    # Удаляем ранее автосгенерированные рейсы в целевом окне (чтобы новое распределение действительно обновляло картину).
    generated_prev = db.query(Flight).filter(
        Flight.plan_time >= datetime.combine(start_ext, datetime.min.time()),
        Flight.plan_time < datetime.combine(end_ext + timedelta(days=1), datetime.min.time()),
        Flight.extra_data.isnot(None),
    ).all()
    deleted_prev = 0
    for gf in generated_prev:
        try:
            payload = json.loads(gf.extra_data or "{}")
        except Exception:
            payload = {}
        if payload.get("generated_by") == "distribution_run":
            db.delete(gf)
            deleted_prev += 1
    if deleted_prev > 0:
        db.flush()

    existing_in_target = db.query(Flight).filter(
        Flight.plan_time >= datetime.combine(start_ext, datetime.min.time()),
        Flight.plan_time < datetime.combine(end_ext + timedelta(days=1), datetime.min.time()),
    ).all()
    if body.distribution_type == "selected_groups" and selected_norm:
        existing_in_target = [f for f in existing_in_target if _norm_airline(f.airline) in selected_norm]

    existing_keys = set()
    for f in existing_in_target:
        if not f.plan_time:
            continue
        existing_keys.add((f.flight_number, f.airline, f.flight_type.value, f.plan_time.date()))

    created_flights: list[Flight] = []
    day = start_ext
    while day <= end_ext:
        # Для каждого дня берём не один, а несколько референс-дней той же недели,
        # чтобы плотность была ближе к реальным данным и набор рейсов был разнообразнее.
        weekday = day.weekday()
        same_weekday_days = sorted(
            [d for d in source_by_day.keys() if d.weekday() == weekday and d <= max_plan.date()],
            reverse=True,
        )
        ref_days = same_weekday_days[:3] if same_weekday_days else [max(source_by_day.keys())]

        merged: list[Flight] = []
        for rd in ref_days:
            merged.extend(source_by_day.get(rd, []))

        merged.sort(key=lambda f: f.plan_time or f.estimated_time or datetime.min)
        unique_templates: dict[tuple[str, str, str, int, int], Flight] = {}
        for t in merged:
            bt = t.plan_time or t.estimated_time
            if not bt:
                continue
            key = (
                t.flight_number,
                t.airline,
                t.flight_type.value,
                bt.hour,
                bt.minute,
            )
            if key not in unique_templates:
                unique_templates[key] = t

        day_template = list(unique_templates.values())
        if same_weekday_days:
            max_day_size = max(len(source_by_day[d]) for d in same_weekday_days[:4])
        else:
            max_day_size = len(day_template)
        target_size = max(1, min(len(day_template), int(max_day_size * 1.35)))
        day_template = day_template[:target_size]

        for t in day_template:
            base_t = t.plan_time or t.estimated_time
            if not base_t:
                continue
            new_plan = _shift_to_date(base_t, day)
            # Уникальность проверяем по реальной дате планового времени (после TIME_SHIFT_HOURS),
            # чтобы при переносе времени через полночь не создавать дубликаты рейсов.
            k = (t.flight_number, t.airline, t.flight_type.value, new_plan.date())
            if k in existing_keys:
                continue
            # Для будущего периода в "реальной" не переносим факт/задержки.
            new_est = new_plan
            new_fact = None
            nf = Flight(
                flight_number=t.flight_number,
                airline=t.airline,
                aircraft_type=t.aircraft_type,
                scheduled_departure=new_plan,
                external_flight_id=None,
                plan_time=new_plan,
                estimated_time=new_est,
                fact_time=new_fact,
                delayed_to=None,
                is_delayed=False,
                is_cancelled=False,
                airport=t.airport,
                ru_airport=t.ru_airport,
                en_airport=t.en_airport,
                status_raw=None,
                status_tablo="ПО РАСПИСАНИЮ",
                status_tablo_en="ON SCHEDULE",
                flight_type=t.flight_type,
                code_shares=t.code_shares,
                status=FlightStatus.SCHEDULED,
                passengers_count=t.passengers_count,
                extra_data=_shift_extra_data(t.extra_data, base_t, day)
                or json.dumps({
                    "generated_by": "distribution_run",
                    "template_flight_id": t.id,
                    "generated_for_date": day.isoformat(),
                }, ensure_ascii=False),
            )
            db.add(nf)
            created_flights.append(nf)
            existing_keys.add(k)
        day += timedelta(days=1)

    db.flush()

    # Ресурсы и расписания в окне расширения
    rs_checkin = db.query(Resource).filter(Resource.is_active == True, Resource.resource_type == ResourceType.CHECK_IN).all()
    rs_gate = db.query(Resource).filter(Resource.is_active == True, Resource.resource_type == ResourceType.GATE).all()

    schedules_checkin = {r.id: IntervalSet([]) for r in rs_checkin}
    schedules_gate = {r.id: IntervalSet([]) for r in rs_gate}
    loads_checkin = {r.id: 0 for r in rs_checkin}
    loads_gate = {r.id: 0 for r in rs_gate}

    range_start_dt = datetime.combine(start_ext, datetime.min.time())
    range_end_dt = datetime.combine(end_ext + timedelta(days=1), datetime.min.time())

    existing_allocs = db.query(Allocation).join(Resource, Allocation.resource_id == Resource.id).filter(
        Allocation.start_time < range_end_dt,
        Allocation.end_time > range_start_dt,
    ).all()
    for a in existing_allocs:
        if a.resource_id in schedules_checkin:
            schedules_checkin[a.resource_id].add(a.start_time, a.end_time)
            loads_checkin[a.resource_id] = loads_checkin.get(a.resource_id, 0) + 1
        elif a.resource_id in schedules_gate:
            schedules_gate[a.resource_id].add(a.start_time, a.end_time)
            loads_gate[a.resource_id] = loads_gate.get(a.resource_id, 0) + 1

    checkin_norms = db.query(CheckinNorm).all()
    gate_norms = db.query(GateNorm).all()

    created_allocs = 0
    conflicts = 0
    belavia_business_hits = 0

    belavia_names = {"БЕЛАВИА", "BELAVIA"}
    counter21 = next((r for r in rs_checkin if (r.name or "").strip() == "21"), None)

    # Сложные сначала: большие пассажиры/длиннее окна
    created_flights.sort(key=lambda f: (f.plan_time or f.estimated_time, -(f.passengers_count or 0)))

    for f in created_flights:
        intervals = _alloc_interval_for_flight(f, checkin_norms, gate_norms)

        if "checkin" in intervals:
            s, e, need, has_biz = intervals["checkin"]
            selected: list[Resource] = []

            # Белавиа определяется по авиакомпании, а не по префиксу номера рейса.
            # Иначе любые рейсы вида B2xxx ошибочно попадают в бизнес-правило для стойки 21.
            is_belavia = (f.airline or "").strip().upper() in belavia_names
            if has_biz and is_belavia and counter21 is not None:
                # Бизнес-стойка 21 работает в shared-режиме: допускаем параллельное обслуживание.
                selected.append(counter21)
                belavia_business_hits += 1
                regular_need = max(0, need - 1)
            else:
                regular_need = need

            if regular_need > 0:
                regular_pool = [r for r in rs_checkin if counter21 is None or r.id != counter21.id]
                chosen = _choose_resources(regular_pool, schedules_checkin, loads_checkin, s, e, regular_need)
                if not chosen:
                    conflicts += 1
                else:
                    selected.extend(chosen)

            for r in selected:
                db.add(Allocation(
                    flight_id=f.id,
                    resource_id=r.id,
                    start_time=s,
                    end_time=e,
                    plan_start_time=s,
                    plan_end_time=e,
                    allocation_type=AllocationType.MANUAL,
                ))
                created_allocs += 1
                # Всегда фиксируем занятость ресурса по интервалу.
                schedules_checkin[r.id].add(s, e)
                loads_checkin[r.id] = loads_checkin.get(r.id, 0) + 1

        if "gate" in intervals:
            s, e, need, _ = intervals["gate"]
            chosen = _choose_resources(rs_gate, schedules_gate, loads_gate, s, e, need)
            if not chosen:
                conflicts += 1
            for r in chosen:
                db.add(Allocation(
                    flight_id=f.id,
                    resource_id=r.id,
                    start_time=s,
                    end_time=e,
                    plan_start_time=s,
                    plan_end_time=e,
                    allocation_type=AllocationType.MANUAL,
                ))
                created_allocs += 1
                schedules_gate[r.id].add(s, e)
                loads_gate[r.id] = loads_gate.get(r.id, 0) + 1

    db.commit()

    duration_ms = int((time.perf_counter() - t0) * 1000)

    in_period_items = db.query(Flight).filter(
        Flight.plan_time >= datetime.combine(start_ext, datetime.min.time()),
        Flight.plan_time < datetime.combine(end_ext + timedelta(days=1), datetime.min.time()),
    ).all()
    if body.distribution_type == "selected_groups" and names:
        selected_norm = {_norm_airline(n) for n in names if n.strip()}
        in_period_items = [f for f in in_period_items if _norm_airline(f.airline) in selected_norm]

    flights_in_period = len(in_period_items)
    airlines_considered = len({_norm_airline(f.airline) for f in in_period_items if f.airline})

    return DistributionRunResponse(
        ok=True,
        message="Плановое продление и распределение выполнено. Существующие рейсы не изменялись.",
        flights_in_period=flights_in_period,
        airlines_considered=airlines_considered,
        manual_allocations_touched=created_allocs,
        duration_ms=duration_ms,
        log=[
            f"Последняя дата в БД до запуска: {max_plan.date()}.",
            f"Сгенерирован диапазон: {start_ext} — {end_ext}.",
            f"Удалено ранее сгенерированных рейсов в окне: {deleted_prev}.",
            f"Создано новых рейсов: {len(created_flights)}.",
            "Дневная генерация: объединены шаблоны из нескольких исторических дней (повышенная плотность).",
            f"Создано плановых MANUAL-аллокаций: {created_allocs}.",
            f"Конфликтов при назначении: {conflicts}.",
            f"Белавиа: использована бизнес-стойка 21 (shared): {belavia_business_hits} раз.",
            (
                "Внимание: по выбранным авиакомпаниям не найдено шаблонов, "
                "использован общий пул исторических рейсов."
                if body.distribution_type == "selected_groups" and selected_norm and not [f for f in source_flights_all if _norm_airline(f.airline) in selected_norm]
                else "Шаблоны по выбранным авиакомпаниям применены."
            ),
            "Существующие рейсы и их аллокации не изменялись.",
        ],
    )


def _run_forecast_distribution(body: DistributionRunRequest, db: Session) -> DistributionRunResponse:
    """
    File-based прогноз:
    - читаем указанные Excel-файлы (или папку Выгрузки),
    - строим профили рейсов по weekday+season,
    - создаем плановые рейсы и аллокации (плановые) в проекте.
    """
    t0 = time.perf_counter()
    d0 = _parse_day(body.date_from)
    d1 = _parse_day(body.date_to)
    if d1 < d0:
        raise HTTPException(422, "date_to раньше date_from")

    buffer_days = 1 if TIME_SHIFT_HOURS else 0
    target_start = d0.date() - timedelta(days=buffer_days)
    target_end = d1.date() + timedelta(days=buffer_days)
    requested_start = d0.date()
    requested_end = d1.date()
    if target_end < target_start:
        raise HTTPException(422, "Период прогноза выходит за лимит")

    # Выбор файлов источника
    if body.forecast_source_files:
        source_files = [p for p in body.forecast_source_files if p and os.path.exists(p)]
    else:
        source_files = sorted(glob.glob(DEFAULT_FORECAST_GLOB))
    if not source_files:
        raise HTTPException(422, "Не найдены файлы источника для прогноза (forecast_source_files/Выгрузки)")

    frames: list[pd.DataFrame] = []
    for p in source_files:
        try:
            fr = _extract_history_rows_from_excel(p)
        except Exception:
            fr = pd.DataFrame()
        if len(fr):
            frames.append(fr)
    if not frames:
        raise HTTPException(422, "Из переданных файлов не удалось извлечь данные по вылетам")
    history_df = pd.concat(frames, ignore_index=True)

    recent_basenames = {os.path.basename(p) for p in sorted(source_files)[-FORECAST_RECENT_FILE_COUNT :]}
    history_df["is_recent"] = history_df["source_file"].isin(recent_basenames)

    # В forecast_mode airline_names трактуем как список РАЗРЕШЁННЫХ авиакомпаний.
    # Неотмеченные в UI считаются исключёнными из прогнозирования.
    names = [n.strip() for n in body.airline_names if n.strip()]
    selected_norm = {_norm_airline(n) for n in names if n.strip()}
    if selected_norm:
        history_df = history_df[history_df["airline_norm"].isin(selected_norm)].copy()
        if len(history_df) == 0:
            raise HTTPException(422, "После исключения авиакомпаний не осталось данных для прогноза")
    selected_flights = {x.strip() for x in (body.flight_numbers or []) if x and x.strip()}
    if selected_flights:
        key_series = history_df["airline_norm"].astype(str) + "|" + history_df["flight_no"].astype(str)
        history_df = history_df[key_series.isin(selected_flights)].copy()
        if len(history_df) == 0:
            raise HTTPException(422, "После исключения номеров рейсов не осталось данных для прогноза")

    # Анти-расхождение направлений:
    # если один и тот же номер рейса у АК исторически встречался на разных маршрутах,
    # в прогнозе оставляем только актуальный маршрут из последних выгрузок.
    # Это убирает ситуации вроде "B2783 и в BRU, и в IST одновременно".
    pair_cols = ["airline_norm", "flight_no"]
    dir_cols = pair_cols + ["direction"]
    dir_recent = (
        history_df[history_df["is_recent"]]
        .groupby(dir_cols, dropna=False)
        .agg(
            n_recent=("direction", "size"),
            last_dep_recent=("dep_plan_dt", "max"),
        )
        .reset_index()
    )
    if len(dir_recent) > 0:
        dir_recent = dir_recent.sort_values(
            by=pair_cols + ["n_recent", "last_dep_recent", "direction"],
            ascending=[True, True, False, False, True],
            kind="mergesort",
        )
        latest_dir = (
            dir_recent.groupby(pair_cols, dropna=False)
            .head(1)[pair_cols + ["direction"]]
            .rename(columns={"direction": "direction_keep"})
        )
        before_rows = len(history_df)
        before_dirs = int(history_df.groupby(pair_cols, dropna=False)["direction"].nunique().gt(1).sum())
        history_df = history_df.merge(latest_dir, on=pair_cols, how="left")
        history_df = history_df[
            (history_df["direction_keep"].isna()) | (history_df["direction"] == history_df["direction_keep"])
        ].copy()
        if "direction_keep" in history_df.columns:
            history_df.drop(columns=["direction_keep"], inplace=True)
        after_rows = len(history_df)
        after_dirs = int(history_df.groupby(pair_cols, dropna=False)["direction"].nunique().gt(1).sum())
        logger.info(
            "forecast_mode route cleanup: rows %s->%s, multi-direction keys %s->%s",
            before_rows,
            after_rows,
            before_dirs,
            after_dirs,
        )

    # Профили по ключу: airline+flight+direction+weekday+season
    grouped = history_df.groupby(["airline_norm", "flight_no", "direction", "weekday", "season"], dropna=False)
    profiles: list[dict[str, object]] = []
    for key, g in grouped:
        airline_norm, flight_no, direction, weekday, season = key
        support = int(len(g))
        slice_df = history_df[(history_df["weekday"] == weekday) & (history_df["season"] == season)]
        total_days = max(1, int(slice_df["dep_date"].nunique()))
        active_days = int(g["dep_date"].nunique())
        occur_prob_all = float(active_days / total_days)

        slice_recent = slice_df[slice_df["is_recent"]]
        total_days_recent = max(0, int(slice_recent["dep_date"].nunique()))
        g_recent = g[g["is_recent"]]
        active_days_recent = int(g_recent["dep_date"].nunique())
        occur_prob_recent = (
            float(active_days_recent / total_days_recent) if total_days_recent > 0 else 0.0
        )

        years_hit = int(g["dep_date"].apply(lambda d: d.year).nunique())
        # Одноразовые «всплески» в старых годах без следов в последних выгрузках — не тащим в плотный прогноз.
        if active_days_recent < 1:
            if years_hit <= 1:
                continue
            if occur_prob_all < FORECAST_MIN_P_ALL_WITHOUT_RECENT:
                continue

        if total_days_recent > 0:
            occur_prob_effective = float(
                FORECAST_WEIGHT_RECENT * occur_prob_recent + FORECAST_WEIGHT_ALL * occur_prob_all
            )
        else:
            occur_prob_effective = float(occur_prob_all)

        if not _forecast_profile_kept(occur_prob_all, occur_prob_effective):
            continue

        airline_mode = Counter(g["airline"].tolist()).most_common(1)[0][0]

        # Топ-частотные наборы стоек (для выбора на сайте в forecast_mode).
        counter_ranked = Counter(g["counter_set"].tolist()).most_common(5)
        counter_mode = counter_ranked[0][0] if counter_ranked else ""
        counter_ranked_sets = [s for s, _ in counter_ranked if s]
        gate_mode = Counter(g["gate_set"].tolist()).most_common(1)[0][0] if len(g) else ""

        tails = sorted(
            set([x for x in g["aircraft_tail"].astype(str).tolist() if x and x.lower() != "nan"])
        )
        type_counts = Counter(
            [
                x.strip()
                for x in g["aircraft_type"].astype(str).tolist()
                if x and x.strip() and x.strip().lower() != "nan"
            ]
        )
        aircraft_type_mode = type_counts.most_common(1)[0][0] if type_counts else ""
        aircraft_types_stats = [
            {
                "type": t,
                "count": int(c),
                "share_pct": round((float(c) / float(sum(type_counts.values()))) * 100.0, 1),
            }
            for t, c in type_counts.most_common()
        ] if type_counts else []
        minute_pred = int(np.median(g["minute_of_day"].astype(int)))
        pax_total = float(g["pax_total"].mean())
        pax_biz = float(g["pax_biz"].mean())
        pax_econ = float(g["pax_econ"].mean())
        counter_n_avg = float(g["counter_n"].mean())

        profiles.append(
            {
                "airline_norm": airline_norm,
                "airline": airline_mode,
                "flight_no": str(flight_no),
                "direction": str(direction),
                "weekday": int(weekday),
                "season": str(season),
                "support": support,
                "occur_prob_all": occur_prob_all,
                "occur_prob_recent": occur_prob_recent,
                "occur_prob_effective": occur_prob_effective,
                "active_days_recent": active_days_recent,
                "years_hit": years_hit,
                "minute_pred": minute_pred,
                "counter_set": counter_mode,
                "counter_set_ranked": counter_ranked_sets,
                "gate_set": gate_mode,
                "counter_n_avg": counter_n_avg,
                "pax_total": pax_total,
                "pax_econ": pax_econ,
                "pax_biz": pax_biz,
                "aircraft_type": aircraft_type_mode,
                "aircraft_types_stats": aircraft_types_stats,
                "tails": tails,
            }
        )
    if not profiles:
        raise HTTPException(422, "Недостаточно повторяемых паттернов для прогноза по файлам")

    # Удаляем прошлые прогнозные рейсы в окне.
    generated_prev = db.query(Flight).filter(
        Flight.plan_time >= datetime.combine(requested_start, datetime.min.time()),
        Flight.plan_time < datetime.combine(requested_end + timedelta(days=1), datetime.min.time()),
        Flight.extra_data.isnot(None),
    ).all()
    deleted_prev = 0
    for gf in generated_prev:
        try:
            payload = json.loads(gf.extra_data or "{}")
        except Exception:
            payload = {}
        if payload.get("generated_by") == "forecast_run":
            db.delete(gf)
            deleted_prev += 1
    if deleted_prev:
        db.flush()

    # В forecast_mode хотим картину "как в XML": только прогноз из файлов.
    # Поэтому очищаем в окне старые ПЛАНОВЫЕ (не реальные) рейсы и их аллокации,
    # даже если они были созданы другим сценарием.
    # Реальные (с fact_time) не трогаем.
    stale_plan_flights = db.query(Flight).filter(
        Flight.plan_time >= datetime.combine(requested_start, datetime.min.time()),
        Flight.plan_time < datetime.combine(requested_end + timedelta(days=1), datetime.min.time()),
        Flight.fact_time.is_(None),
    ).all()
    stale_ids = [f.id for f in stale_plan_flights]
    deleted_stale = 0
    if stale_ids:
        db.query(Allocation).filter(Allocation.flight_id.in_(stale_ids)).delete(synchronize_session=False)
        deleted_stale = db.query(Flight).filter(Flight.id.in_(stale_ids)).delete(synchronize_session=False)
        db.flush()

    # В forecast_mode галочки (selected_groups/airline_names) должны НЕ влиять на генерацию.
    # Поэтому existing используем целиком (для всех авиакомпаний), чтобы корректно
    # отлавливать дубликаты прогнозных рейсов в заданном окне.
    # Для совпадения с XML не вычитаем рейсы из already-existing в БД:
    # дедупликация делается только внутри текущего прогнозного расчёта.
    existing_keys: set[tuple[str, str, str, date]] = set()

    created_flights: list[Flight] = []
    # Как в XML: генерируем строго в запрошенном диапазоне [date_from..date_to].
    day = d0.date()
    while day <= d1.date():
        wd = day.weekday()
        season = _season_of(day)
        day_profiles = [p for p in profiles if p["weekday"] == wd and p["season"] == season]
        # Как в XML-скрипте: если в одном слоте совпали
        # (дата после сдвига + время + airline_norm + номер),
        # оставляем наиболее вероятный профиль.
        best_by_slot: dict[tuple[date, str, str, str], tuple[dict[str, object], datetime, float, float, float, int]] = {}
        for p in day_profiles:
            # p_eff: сильнее вес последних выгрузок (см. FORECAST_*), плюс отсев «только один год в прошлом».
            prob = max(0.0, min(1.0, float(p["occur_prob_effective"])))
            if prob <= 0.0:
                continue
            if prob < FORECAST_MIN_P_EFF:
                continue
            if prob < FORECAST_TH_ALWAYS_EFF:
                roll_key = f"{p['airline_norm']}|{p['flight_no']}|{p['direction']}|{day.isoformat()}"
                if _stable_unit_rand(roll_key) > prob:
                    continue

            minute = int(p["minute_pred"])
            hh = max(0, min(23, minute // 60))
            mm = max(0, min(59, minute % 60))
            plan_dt = datetime.combine(day, datetime.min.time()).replace(hour=hh, minute=mm)
            # Переводим плановое время в целевой часовой пояс (например, UTC+3).
            plan_dt = plan_dt + timedelta(hours=TIME_SHIFT_HOURS)

            slot_key = (
                plan_dt.date(),
                plan_dt.strftime("%H:%M"),
                str(p["airline_norm"]),
                str(p["flight_no"]),
            )
            rank = (
                prob,
                float(p["occur_prob_all"]),
                float(p["occur_prob_recent"]),
                int(p["support"]),
            )
            cur = best_by_slot.get(slot_key)
            if cur is None or rank > (cur[2], cur[3], cur[4], cur[5]):
                best_by_slot[slot_key] = (
                    p,
                    plan_dt,
                    prob,
                    float(p["occur_prob_all"]),
                    float(p["occur_prob_recent"]),
                    int(p["support"]),
                )

        for _, pick in best_by_slot.items():
            p, plan_dt, prob, _p_all, _p_recent, _support = pick
            # Уникальность рейса проверяем по фактической дате после сдвига.
            ek = (
                str(p["flight_no"]),
                str(p["airline_norm"]),
                FlightType.DEPARTURE.value,
                plan_dt.date(),
            )
            if ek in existing_keys:
                continue

            direction = str(p["direction"])
            parts = direction.split("->")
            to_code = parts[1] if len(parts) > 1 else direction

            pax_total = max(0.0, float(p["pax_total"]))
            pax_econ = max(0.0, float(p["pax_econ"]))
            pax_biz = max(0.0, float(p["pax_biz"]))
            _ac = str(p.get("aircraft_type") or "")
            _seats_cap = resolve_seat_capacity(
                _ac,
                {
                    "predicted_aircraft_types": p.get("aircraft_types_stats") or [],
                    "predicted_aircraft_type": _ac,
                },
            )
            if _seats_cap is None:
                _seats_cap_i = max(1, min(900, int(np.ceil(pax_total)) if pax_total > 0 else 180))
            else:
                _seats_cap_i = int(_seats_cap)
            pax_total = min(pax_total, float(_seats_cap_i))
            pax_biz = min(pax_biz, pax_total)
            pax_econ = max(0.0, pax_total - pax_biz)

            counter_set = str(p["counter_set"] or "")
            counters_current = _counter_n_from_set(counter_set)
            if counters_current <= 0:
                counters_current = max(1, int(round(float(p["counter_n_avg"]))))

            # Нормативная модель по ТЗ:
            # эконом 15 мин/чел при 50 чел/стойка, бизнес отдельное окно 5 мин/чел.
            load_per_counter = pax_total / max(1, counters_current)
            econ_min_per_pax = max(3.0, 15.0 * (load_per_counter / 50.0))
            if pax_biz > 0:
                biz_min_per_pax = max(2.0, 5.0 * ((pax_biz / 1.0) / 50.0))
            else:
                biz_min_per_pax = 0.0
            reg_dur_min = max(econ_min_per_pax, biz_min_per_pax)
            counters_required = int(np.ceil(pax_total / 50.0)) if pax_total > 0 else 1
            counters_extra_needed = max(0, counters_required - counters_current)

            remarks: list[str] = []
            if counters_extra_needed > 0:
                remarks.append(
                    f"Для соблюдения нормативов не хватает стоек: +{counters_extra_needed} "
                    f"(нужно ~{counters_required}, в типовом наборе {counters_current})."
                )

            nf = Flight(
                flight_number=str(p["flight_no"]),
                airline=str(p["airline"]),
                aircraft_type=(str(p.get("aircraft_type") or "") or "UNKNOWN"),
                scheduled_departure=plan_dt,
                external_flight_id=None,
                plan_time=plan_dt,
                estimated_time=plan_dt,
                fact_time=None,
                delayed_to=None,
                is_delayed=False,
                is_cancelled=False,
                airport=to_code,
                ru_airport=to_code,
                en_airport=to_code,
                status_raw=None,
                status_tablo="ПО РАСПИСАНИЮ",
                status_tablo_en="ON SCHEDULE",
                flight_type=FlightType.DEPARTURE,
                code_shares=None,
                status=FlightStatus.SCHEDULED,
                passengers_count=int(round(pax_total)),
                extra_data=json.dumps(
                    {
                        "generated_by": "forecast_run",
                        "generated_for_date": plan_dt.date().isoformat(),
                        "forecast_basis": {
                            "weekday": wd,
                            "season": season,
                            "support": int(p["support"]),
                            "occur_prob_all": float(p["occur_prob_all"]),
                            "occur_prob_recent": float(p["occur_prob_recent"]),
                            "occur_prob_effective": float(p["occur_prob_effective"]),
                            "active_days_recent": int(p["active_days_recent"]),
                            "years_hit": int(p["years_hit"]),
                            "recent_files": sorted(recent_basenames),
                            "source_files_count": len(source_files),
                        },
                        "predicted_direction": direction,
                        "predicted_counter_set": counter_set,
                        "predicted_counter_set_ranked": p.get("counter_set_ranked") or [counter_set],
                        "predicted_gate_set": str(p.get("gate_set") or ""),
                        "predicted_counter_n": counters_current,
                        "predicted_pax_total": round(pax_total, 2),
                        "predicted_pax_econ": round(pax_econ, 2),
                        "predicted_pax_biz": round(pax_biz, 2),
                        "predicted_reg_duration_min": round(reg_dur_min, 2),
                        "predicted_econ_min_per_pax": round(econ_min_per_pax, 3),
                        "predicted_biz_min_per_pax": round(biz_min_per_pax, 3),
                        "predicted_remarks": " ".join(remarks),
                        "predicted_aircraft_tails": p["tails"],
                        "predicted_aircraft_type": str(p.get("aircraft_type") or ""),
                        "predicted_aircraft_types": p.get("aircraft_types_stats") or [],
                        "Кол-во кресел": _seats_cap_i,
                        "Кол-во кресел для типа ВС (макс.)": _seats_cap_i,
                    },
                    ensure_ascii=False,
                ),
            )
            db.add(nf)
            created_flights.append(nf)
            existing_keys.add(ek)
        day += timedelta(days=1)

    db.flush()

    # Аллокации в плановые:
    rs_checkin = db.query(Resource).filter(Resource.is_active == True, Resource.resource_type == ResourceType.CHECK_IN).all()
    rs_gate = db.query(Resource).filter(Resource.is_active == True, Resource.resource_type == ResourceType.GATE).all()

    schedules_checkin = {r.id: IntervalSet([]) for r in rs_checkin}
    schedules_gate = {r.id: IntervalSet([]) for r in rs_gate}
    loads_checkin = {r.id: 0 for r in rs_checkin}
    loads_gate = {r.id: 0 for r in rs_gate}

    range_start_dt = datetime.combine(target_start, datetime.min.time())
    range_end_dt = datetime.combine(target_end + timedelta(days=1), datetime.min.time())
    existing_allocs = db.query(Allocation).join(Resource, Allocation.resource_id == Resource.id).filter(
        Allocation.start_time < range_end_dt,
        Allocation.end_time > range_start_dt,
    ).all()
    for a in existing_allocs:
        if a.resource_id in schedules_checkin:
            schedules_checkin[a.resource_id].add(a.start_time, a.end_time)
            loads_checkin[a.resource_id] = loads_checkin.get(a.resource_id, 0) + 1
        elif a.resource_id in schedules_gate:
            schedules_gate[a.resource_id].add(a.start_time, a.end_time)
            loads_gate[a.resource_id] = loads_gate.get(a.resource_id, 0) + 1

    checkin_norms = db.query(CheckinNorm).all()
    gate_norms = db.query(GateNorm).all()

    created_allocs = 0
    conflicts = 0
    created_flights.sort(key=lambda f: (f.plan_time or datetime.min, -(f.passengers_count or 0)))
    belavia_names = {"БЕЛАВИА", "BELAVIA"}

    for f in created_flights:
        intervals = _alloc_interval_for_flight(f, checkin_norms, gate_norms)
        if "checkin" in intervals:
            s, e, need, has_biz = intervals["checkin"]
            selected: list[Resource] = []
            # Для прогноза check-in стараемся использовать типовой набор стоек из профиля.
            predicted_set = ""
            try:
                payload = json.loads(f.extra_data or "{}")
                predicted_set = str(payload.get("predicted_counter_set") or "")
            except Exception:
                predicted_set = ""

            if predicted_set:
                nums_by_name = {str((r.name or "")).strip(): r for r in rs_checkin}
                nums = [x for x in str(predicted_set).split("-") if x]
                target = [nums_by_name[n] for n in nums if n in nums_by_name]

                if len(target) != len(nums):
                    conflicts += 1

                is_belavia = (f.airline or "").strip().upper() in belavia_names
                # Берём из типового набора только реально нужное число стоек (need),
                # не раздувая аллокацию до полного predicted_set.
                chosen_pred_all = [
                    r
                    for r in target
                    if (
                        ((r.name or "").strip() == "21" and has_biz and is_belavia)
                        or not schedules_checkin[r.id].overlaps(s, e)
                    )
                ]
                if len(chosen_pred_all) < len(target):
                    conflicts += 1

                selected = []
                if need > 0:
                    if has_biz and is_belavia:
                        c21 = next((r for r in chosen_pred_all if (r.name or "").strip() == "21"), None)
                        if c21 is not None:
                            selected.append(c21)
                    for r in chosen_pred_all:
                        if len(selected) >= need:
                            break
                        if any(x.id == r.id for x in selected):
                            continue
                        selected.append(r)

                # Если вообще не удалось занять ни одну типовую стойку — делаем fallback
                # на произвольный набор под need, чтобы рейс не остался без check-in.
                if not selected:
                    chosen = _choose_resources(
                        rs_checkin, schedules_checkin, loads_checkin, s, e, need
                    )
                    if chosen:
                        selected = chosen
                elif len(selected) < need:
                    # Добираем недостающие стойки из общего пула.
                    missing = need - len(selected)
                    selected_ids = {r.id for r in selected}
                    pool = [r for r in rs_checkin if r.id not in selected_ids]
                    ref_nums = [_counter_num(r.name) for r in target]
                    # Для добора держимся рядом с типовым набором, чтобы не получать разброс вроде "2-19-21".
                    chosen_more = _choose_resources_near_reference(
                        pool, schedules_checkin, loads_checkin, s, e, missing, ref_nums
                    )
                    if chosen_more:
                        selected.extend(chosen_more)
            else:
                chosen = _choose_resources(rs_checkin, schedules_checkin, loads_checkin, s, e, need)
                if not chosen:
                    conflicts += 1
                else:
                    selected = chosen

            for r in selected:
                db.add(
                    Allocation(
                        flight_id=f.id,
                        resource_id=r.id,
                        start_time=s,
                        end_time=e,
                        plan_start_time=s,
                        plan_end_time=e,
                        allocation_type=AllocationType.MANUAL,
                    )
                )
                created_allocs += 1
                schedules_checkin[r.id].add(s, e)
                loads_checkin[r.id] = loads_checkin.get(r.id, 0) + 1

        if "gate" in intervals:
            s, e, need, _ = intervals["gate"]
            chosen: list[Resource] = []
            predicted_gate_set = ""
            try:
                payload = json.loads(f.extra_data or "{}")
                predicted_gate_set = str(payload.get("predicted_gate_set") or "")
            except Exception:
                predicted_gate_set = ""

            if predicted_gate_set:
                by_name = {str((r.name or "")).strip().upper(): r for r in rs_gate}
                names = [x for x in predicted_gate_set.split("-") if x]
                target = [by_name[n.upper()] for n in names if n.upper() in by_name]
                if len(target) != len(names):
                    conflicts += 1
                chosen_pred = [r for r in target if not schedules_gate[r.id].overlaps(s, e)]
                if len(chosen_pred) < len(target):
                    conflicts += 1
                chosen = chosen_pred
                if not chosen:
                    chosen = _choose_resources(rs_gate, schedules_gate, loads_gate, s, e, need)
            else:
                chosen = _choose_resources(rs_gate, schedules_gate, loads_gate, s, e, need)

            if not chosen:
                conflicts += 1
            for r in chosen:
                db.add(
                    Allocation(
                        flight_id=f.id,
                        resource_id=r.id,
                        start_time=s,
                        end_time=e,
                        plan_start_time=s,
                        plan_end_time=e,
                        allocation_type=AllocationType.MANUAL,
                    )
                )
                created_allocs += 1
                schedules_gate[r.id].add(s, e)
                loads_gate[r.id] = loads_gate.get(r.id, 0) + 1

    db.commit()
    duration_ms = int((time.perf_counter() - t0) * 1000)

    in_period_items = db.query(Flight).filter(
        Flight.plan_time >= datetime.combine(requested_start, datetime.min.time()),
        Flight.plan_time < datetime.combine(requested_end + timedelta(days=1), datetime.min.time()),
    ).all()

    flights_in_period = len(in_period_items)
    airlines_considered = len({_norm_airline(f.airline) for f in in_period_items if f.airline})

    return DistributionRunResponse(
        ok=True,
        message="Вероятностный прогноз из файлов выполнен и добавлен в плановые.",
        flights_in_period=flights_in_period,
        airlines_considered=airlines_considered,
        manual_allocations_touched=created_allocs,
        duration_ms=duration_ms,
        log=[
            f"Период: {d0.date()} — {d1.date()} | правила: {FORECAST_RULES_VERSION}",
            f"Источник: {len(source_files)} файлов, профилей: {len(profiles)}",
            (
                f"Фильтр АК: разрешено {len(selected_norm)}"
                if selected_norm
                else "Фильтр АК: без ограничений"
            ),
            "Перезапись: только выбранный диапазон дат",
            f"Удалено старых рейсов: forecast={deleted_prev}, плановых={deleted_stale}",
            f"Создано: рейсов={len(created_flights)}, аллокаций={created_allocs}",
            f"Конфликты ресурсов: {conflicts}",
            f"Итог в периоде: рейсов={flights_in_period}, авиакомпаний={airlines_considered}, время={duration_ms} мс",
        ],
    )
