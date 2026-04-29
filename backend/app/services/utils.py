"""
Вспомогательные функции для парсинга XML и расчётов.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re


_WS_RE = re.compile(r"\s+")


def clean_text(value: str | None) -> str | None:
    """Нормализует пробелы и обрезает строку."""
    if value is None:
        return None
    v = _WS_RE.sub(" ", value).strip()
    return v if v else None


def parse_ddmm_hhmm(value: str | None, *, reference_year: int) -> datetime | None:
    """
    Парсит время из XML в формате `DD.MM HH:MM` (без года).

    В реальных дампах `<plan>` и `<EAT>` приходят именно так, поэтому год берём из контекста:
    - атрибут `now` у корневого элемента `<FLIGHT_LIST now="YYYY-MM-DDTHH:MM:SS.sss">`

    Если значение пустое — возвращаем None.
    """
    value = clean_text(value)
    if not value:
        return None

    # Примеры из XML: "17.03 00:50", "18.03 10:31"
    try:
        day_s, month_s = value.split(" ", 1)[0].split(".", 1)
        time_s = value.split(" ", 1)[1]
        hour_s, min_s = time_s.split(":", 1)
        return datetime(
            year=reference_year,
            month=int(month_s),
            day=int(day_s),
            hour=int(hour_s),
            minute=int(min_s),
        )
    except Exception:
        # На защите диплома полезно иметь fail-safe: не падаем на одном плохом значении.
        return None


def parse_ddmmyyyy_hhmmss(value: str | None) -> datetime | None:
    """
    Парсит время из XML в формате `DD.MM.YYYY HH:MM:SS`.
    Пример: "16.03.2026 19:15:00" (DelayedTo).
    """
    value = clean_text(value)
    if not value:
        return None
    try:
        date_s, time_s = value.split(" ", 1)
        day_s, month_s, year_s = date_s.split(".", 2)
        hour_s, min_s, sec_s = time_s.split(":", 2)
        return datetime(
            year=int(year_s),
            month=int(month_s),
            day=int(day_s),
            hour=int(hour_s),
            minute=int(min_s),
            second=int(sec_s),
        )
    except Exception:
        return None


def split_codeshares(value: str | None) -> list[str]:
    """
    Разбирает CodeShare строку.

    Примеры из XML:
    - пусто: <CodeShare/>
    - один: <CodeShare>UT4982</CodeShare>
    - список: <CodeShare>N47942, WZ5942, UT4942</CodeShare>
    """
    value = clean_text(value)
    if not value:
        return []
    parts = [clean_text(p) for p in re.split(r"[,\s]+", value) if clean_text(p)]
    # Убираем дубликаты, сохраняя порядок
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def normalize_codeshares(primary: str, codes: list[str]) -> str | None:
    """
    Собирает code_shares в одну строку для хранения в Flights.code_shares.
    Убирает primary из списка, если он вдруг попал туда.
    """
    seen: set[str] = set([primary])
    out: list[str] = []
    for c in codes:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return ";".join(out) if out else None

