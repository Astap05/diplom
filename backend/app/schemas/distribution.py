"""Схемы запроса/ответа для модуля «Распределение» (как на терминале аэропорта)."""

from pydantic import BaseModel, Field


class DistributionRunRequest(BaseModel):
    """Параметры запуска пересчёта (алгоритм можно подключить позже)."""

    date_from: str = Field(..., description="Начало периода YYYY-MM-DD")
    date_to: str = Field(..., description="Конец периода YYYY-MM-DD")
    distribution_type: str = Field(
        default="selected_groups",
        description="selected_groups | all_flights",
    )
    airline_names: list[str] = Field(
        default_factory=list,
        description="Пустой список = все авиакомпании в периоде",
    )
    flight_numbers: list[str] = Field(
        default_factory=list,
        description="Разрешенные рейсы в формате airline_norm|flight_no (если пусто — все рейсы выбранных авиакомпаний)",
    )
    common_checkin_same_counters: bool = Field(default=False)
    consider_slf: bool = Field(default=False)
    forecast_mode: bool = Field(
        default=False,
        description="Если true — запуск вероятностного прогноза будущих рейсов по истории",
    )
    forecast_source_files: list[str] = Field(
        default_factory=list,
        description="Список путей к Excel-файлам для прогноза (если пусто, берется папка Выгрузки)",
    )


class DistributionRunResponse(BaseModel):
    ok: bool
    message: str
    flights_in_period: int
    airlines_considered: int
    manual_allocations_touched: int
    duration_ms: int
    log: list[str]
