"""
Типовая пассажировместимость по коду IATA и названию ВС (как в выгрузках аэропорта).
Используется для отображения «Кол-во кресел» и ограничения пассажиров сверху.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

# Код IATA (колонка «Тип ВС (IATA)») -> типовое макс. число мест (по факту выгрузок / справочнику).
SEATS_BY_IATA: dict[str, int] = {
    "E95": 189,
    "738": 189,
    "320": 210,
    "733": 189,
    "7M8": 189,
    "E7W": 76,
    "332": 405,
    "SU9": 103,
    "321": 210,
    "CR2": 50,
    "E90": 110,
    "32N": 170,
    "32Q": 196,
    "333": 440,
    "763": 264,
    "737": 131,
    "73G": 149,
    "E75": 76,
    "319": 132,
    "7M9": 172,
    "752": 184,
    "359": 440,
    "77W": 402,
    "788": 246,
}

# Подстроки в полном названии (нижний регистр) -> места.
SEATS_BY_NAME_SUBSTR: list[tuple[str, int]] = [
    ("superjet", 103),
    ("сухой", 103),
    ("ssj", 103),
    ("емб195", 189),
    ("e195", 189),
    ("б737-8", 189),
    ("b737-8", 189),
    ("737 макс 8", 189),
    ("737 max 8", 189),
    ("7m8", 189),
    ("а-320", 210),
    ("a-320", 210),
    ("a320", 210),
    ("эйрбас а320", 210),
    ("а-321", 210),
    ("a-321", 210),
    ("a321", 210),
    ("б737-3", 189),
    ("b737-3", 189),
    ("б767", 264),
    ("b767", 264),
    ("а330-3", 440),
    ("a330-3", 440),
    ("а330-2", 405),
    ("a330-2", 405),
    ("а350", 440),
    ("a350", 440),
    ("b777", 402),
    ("787-8", 246),
    ("дримлайнер", 246),
    ("емб175", 76),
    ("емб190", 110),
    ("црй", 50),
    ("crj", 50),
    ("б757", 184),
    ("b757", 184),
    ("б737-7", 149),
    ("b737-7", 149),
    ("б-737", 131),
    ("b-737", 131),
    ("макс 9", 172),
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


def _float_from(extra: dict[str, Any], keys: list[str]) -> float | None:
    for k in keys:
        if k not in extra:
            continue
        try:
            v = float(extra[k])
            if not math.isnan(v) and v >= 0:
                return v
        except (TypeError, ValueError):
            continue
    return None


def _seats_from_airbus_style_code(raw: str) -> int | None:
    """A-320 / А-320 / A 320 → код 320 в SEATS_BY_IATA (латиница и кириллическая «А»)."""
    t = re.sub(r"\s+", "", (raw or "").strip().upper())
    m = re.match(r"^[AА][-]?(\d{3})$", t)
    if not m:
        return None
    code = m.group(1)
    return SEATS_BY_IATA.get(code)


def resolve_seat_capacity(aircraft_type: str, extra: dict[str, Any] | None) -> int | None:
    """
    Возвращает типовую вместимость для типа ВС или None, если не удалось сопоставить.
    """
    extra = extra if isinstance(extra, dict) else {}

    s = _seats_from_airbus_style_code(aircraft_type)
    if s is not None:
        return s

    iata = str(extra.get("Тип ВС (IATA)") or "").strip().upper()
    if iata and iata in SEATS_BY_IATA:
        return SEATS_BY_IATA[iata]

    # predicted_aircraft_types: [{"type": "...", "pct": ...}, ...]
    pat = extra.get("predicted_aircraft_types")
    if isinstance(pat, list):
        for item in pat:
            if not isinstance(item, dict):
                continue
            t = str(item.get("type") or "").strip().upper()
            if len(t) <= 4 and t in SEATS_BY_IATA:
                return SEATS_BY_IATA[t]

    for key in ("predicted_aircraft_type",):
        t = str(extra.get(key) or "").strip().upper()
        if len(t) <= 4 and t in SEATS_BY_IATA:
            return SEATS_BY_IATA[t]
        s = _seats_from_airbus_style_code(t)
        if s is not None:
            return s

    combined = _norm(f"{aircraft_type} {extra.get('Полное назв ВС (Рус)', '')}")
    for sub, seats in SEATS_BY_NAME_SUBSTR:
        if sub in combined:
            return seats

    at = _norm(aircraft_type)
    for sub, seats in SEATS_BY_NAME_SUBSTR:
        if sub in at:
            return seats

    return None


def enrich_passenger_load_fields(extra: dict[str, Any], aircraft_type: str) -> dict[str, Any]:
    """
    Выставляет реалистичное число кресел по типу ВС и не даёт пассажирам превысить это число.
    """
    out = dict(extra)
    canon = resolve_seat_capacity(aircraft_type, out)

    raw_seats = _float_from(out, ["Кол-во кресел", "Кол-во кресел для типа ВС (макс.)"])
    pax_main = _float_from(out, ["Пассаж. всего", "predicted_pax_total"])

    if canon is not None:
        seats_i = int(canon)
    elif raw_seats is not None and 1 <= raw_seats <= 900:
        seats_i = int(round(raw_seats))
    elif pax_main is not None:
        seats_i = max(1, min(900, int(math.ceil(float(pax_main)))))
    else:
        seats_i = 180

    out["Кол-во кресел"] = seats_i
    out["Кол-во кресел для типа ВС (макс.)"] = seats_i

    def _clamp_pax_key(key: str) -> int | None:
        if key not in out:
            return None
        try:
            p = float(out[key])
        except (TypeError, ValueError):
            return None
        return int(max(0, min(round(p), seats_i)))

    pax_i: int | None = None
    if "Пассаж. всего" in out:
        v = _clamp_pax_key("Пассаж. всего")
        if v is not None:
            out["Пассаж. всего"] = v
            pax_i = v
    if "predicted_pax_total" in out:
        v = _clamp_pax_key("predicted_pax_total")
        if v is not None:
            out["predicted_pax_total"] = float(v)
            pax_i = v if pax_i is None else pax_i

    if pax_i is None and pax_main is not None:
        pax_i = int(max(0, min(round(float(pax_main)), seats_i)))

    if pax_i is not None:
        biz_raw = _float_from(out, ["Пассаж. Бизнес", "predicted_pax_biz"])
        if biz_raw is not None:
            biz_i = int(max(0, min(round(float(biz_raw)), pax_i)))
            out["Пассаж. Бизнес"] = biz_i
            if "predicted_pax_biz" in out:
                out["predicted_pax_biz"] = float(biz_i)
            out["Пассаж. Эконом"] = max(0, pax_i - biz_i)
            if "predicted_pax_econ" in out:
                out["predicted_pax_econ"] = float(max(0, pax_i - biz_i))

    return out


def enrich_extra_json(extra_data: str | None, aircraft_type: str) -> str | None:
    if not extra_data or not str(extra_data).strip():
        return extra_data
    try:
        raw = json.loads(extra_data)
    except Exception:
        return extra_data
    if not isinstance(raw, dict):
        return extra_data
    merged = enrich_passenger_load_fields(raw, aircraft_type or "")
    return json.dumps(merged, ensure_ascii=False)
