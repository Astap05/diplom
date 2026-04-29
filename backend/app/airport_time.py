"""
Единая шкала времени для расписания в БД.

Allocation.start_time / end_time после импорта и распределения хранятся как naive datetime,
чьи часы/минуты соответствуют «времени аэропорта» (после TIME_SHIFT из Excel/прогноза).
Сравнение с datetime.utcnow() без сдвига давало сдвиг на TIME_SHIFT_HOURS и ломало поломки/таймлайн.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Синхронно с логикой POST /distribution/run (раньше distribution.TIME_SHIFT_HOURS).
TIME_SHIFT_HOURS = 3


def airport_now_naive() -> datetime:
    """
    «Сейчас» в той же шкале, что и интервалы аллокаций после генерации (naive, без tzinfo).
    """
    return datetime.utcnow() + timedelta(hours=TIME_SHIFT_HOURS)


def utc_now() -> datetime:
    """Момент реального UTC (aware) — для меток событий, отдаваемых в JSON с Z/+00:00."""
    return datetime.now(timezone.utc)
