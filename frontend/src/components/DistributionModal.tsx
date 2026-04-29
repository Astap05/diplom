"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { AllocationForDashboard, DistributionRunResponse } from "@/lib/types";

const DISTRIBUTION_FILTERS_KEY = "rms_distribution_filters_v1";

function formatDateInput(d: Date) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function addDays(d: Date, n: number) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

function normAirline(s: string) {
  return s.trim().toLowerCase().split(/\s+/).join(" ");
}

interface DistributionModalProps {
  open: boolean;
  onClose: () => void;
  /** Дата дашборда — подставляется в «с / по». */
  referenceDate: Date;
  allocations: AllocationForDashboard[];
  useMock: boolean;
  onApplied?: () => Promise<void> | void;
}

export default function DistributionModal({
  open,
  onClose,
  referenceDate,
  allocations,
  useMock,
  onApplied,
}: DistributionModalProps) {
  const [dateFrom, setDateFrom] = useState(() => formatDateInput(referenceDate));
  const [dateTo, setDateTo] = useState(() => formatDateInput(addDays(referenceDate, 6)));
  const [distributionType, setDistributionType] = useState<"selected_groups" | "all_flights">(
    "selected_groups"
  );
  const [commonCheckin, setCommonCheckin] = useState(false);
  const [considerSlf, setConsiderSlf] = useState(false);
  const forecastMode = true;
  const [selectedAirlines, setSelectedAirlines] = useState<Set<string>>(new Set());
  const [selectedFlights, setSelectedFlights] = useState<Record<string, Set<string>>>({});
  const [expandedAirlines, setExpandedAirlines] = useState<Set<string>>(new Set());
  const [airlinesAll, setAirlinesAll] = useState<string[]>([]);
  const [flightsByAirline, setFlightsByAirline] = useState<Record<string, string[]>>({});
  const [result, setResult] = useState<DistributionRunResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const airlinesFromAllocations = useMemo(() => {
    const s = new Set<string>();
    for (const a of allocations) {
      const n = (a.airline ?? "").trim();
      if (n) s.add(n);
    }
    return Array.from(s).sort((x, y) => x.localeCompare(y, "ru"));
  }, [allocations]);

  const airlinesSorted = useMemo(
    () => (airlinesAll.length ? airlinesAll : airlinesFromAllocations),
    [airlinesAll, airlinesFromAllocations]
  );

  useEffect(() => {
    if (!open) return;
    setDateFrom(formatDateInput(referenceDate));
    setDateTo(formatDateInput(addDays(referenceDate, 6)));
    setError(null);
  }, [open, referenceDate]);

  useEffect(() => {
    if (!open || useMock) return;
    let cancelled = false;
    const loadAirlines = async () => {
      try {
        const opts = await api.getForecastAirlineFlights();
        if (cancelled) return;
        const cleaned = opts.map((x) => x.airline.trim()).filter(Boolean).sort((a, b) => a.localeCompare(b, "ru"));
        const flightsMap: Record<string, string[]> = {};
        for (const o of opts) flightsMap[o.airline] = o.flights;
        setAirlinesAll(cleaned);
        setFlightsByAirline(flightsMap);

        let persisted: { selectedAirlines?: string[]; selectedFlights?: Record<string, string[]> } = {};
        try {
          persisted = JSON.parse(localStorage.getItem(DISTRIBUTION_FILTERS_KEY) || "{}");
        } catch {
          persisted = {};
        }

        const hasStoredAirlines = Array.isArray(persisted.selectedAirlines);
        const selectedFromStore = new Set((persisted.selectedAirlines ?? []).filter((n) => cleaned.includes(n)));
        const airlinesToUse = hasStoredAirlines ? selectedFromStore : new Set(cleaned);
        setSelectedAirlines(airlinesToUse);

        const nextFlights: Record<string, Set<string>> = {};
        for (const name of cleaned) {
          const allFlights = flightsMap[name] ?? [];
          const hasStoredFlightsForAirline = !!persisted.selectedFlights && Object.prototype.hasOwnProperty.call(persisted.selectedFlights, name);
          const fromStore = new Set((persisted.selectedFlights?.[name] ?? []).filter((f) => allFlights.includes(f)));
          nextFlights[name] = hasStoredFlightsForAirline ? fromStore : new Set(allFlights);
        }
        setSelectedFlights(nextFlights);
      } catch {
        if (!cancelled) {
          setAirlinesAll([]);
          setFlightsByAirline({});
        }
      }
    };
    void loadAirlines();
    return () => {
      cancelled = true;
    };
  }, [open, useMock]);

  useEffect(() => {
    if (!open) return;
    try {
      const payload = {
        selectedAirlines: Array.from(selectedAirlines),
        selectedFlights: Object.fromEntries(
          Object.entries(selectedFlights).map(([k, v]) => [k, Array.from(v)])
        ),
      };
      localStorage.setItem(DISTRIBUTION_FILTERS_KEY, JSON.stringify(payload));
    } catch {
      // ignore storage issues
    }
  }, [open, selectedAirlines, selectedFlights]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const toggleAirline = useCallback((name: string) => {
    setSelectedAirlines((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }, []);

  const selectAllAirlines = useCallback(() => {
    setSelectedAirlines(new Set(airlinesSorted));
  }, [airlinesSorted]);

  const clearAirlines = useCallback(() => {
    setSelectedAirlines(new Set());
  }, []);

  const toggleAirlineExpand = useCallback((name: string) => {
    setExpandedAirlines((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }, []);

  const toggleFlight = useCallback((airline: string, flightNo: string) => {
    setSelectedFlights((prev) => {
      const next = { ...prev };
      const set = new Set(next[airline] ?? []);
      if (set.has(flightNo)) set.delete(flightNo);
      else set.add(flightNo);
      next[airline] = set;
      return next;
    });
  }, []);

  const run = useCallback(async () => {
    setError(null);
    if (forecastMode && selectedAirlines.size === 0) {
      setError("Снимите исключение хотя бы с одной авиакомпании: для прогноза нужен минимум один перевозчик.");
      return;
    }
    if (!forecastMode && distributionType === "selected_groups" && selectedAirlines.size === 0) {
      setError("Выберите хотя бы одну авиакомпанию или переключите тип на «Все рейсы периода».");
      return;
    }

    const effectiveDistributionType: "selected_groups" | "all_flights" = forecastMode
      ? "all_flights"
      : distributionType;
    const selectedFlightKeys = Array.from(selectedAirlines).flatMap((airline) => {
      const nums = flightsByAirline[airline] ?? [];
      const sel = selectedFlights[airline] ?? new Set(nums);
      return nums.filter((n) => sel.has(n)).map((n) => `${normAirline(airline)}|${n}`);
    });
    const body = {
      date_from: dateFrom,
      date_to: dateTo,
      distribution_type: effectiveDistributionType,
      airline_names:
        forecastMode
          ? Array.from(selectedAirlines).sort((a, b) => a.localeCompare(b, "ru"))
          : effectiveDistributionType === "selected_groups"
          ? Array.from(selectedAirlines).sort((a, b) => a.localeCompare(b, "ru"))
          : [],
      flight_numbers: selectedFlightKeys,
      common_checkin_same_counters: commonCheckin,
      consider_slf: considerSlf,
      forecast_mode: forecastMode,
    };

    setBusy(true);
    setResult(null);
    try {
      if (useMock) {
        const considered = forecastMode
          ? selectedAirlines.size
          : distributionType === "all_flights"
            ? airlinesSorted.length
            : selectedAirlines.size;
        const mock: DistributionRunResponse = {
          ok: true,
          message: "Режим мок: запрос к API не отправлялся.",
          flights_in_period: allocations.length,
          airlines_considered: considered,
          manual_allocations_touched: allocations.length,
          duration_ms: 8,
          log: [
            `[Мок] Период: ${dateFrom} — ${dateTo}.`,
            `[Мок] Тип: ${distributionType}.`,
            `Аллокаций в текущем наборе данных: ${allocations.length}.`,
            `Учтено авиакомпаний (по выбору): ${considered}.`,
            ...(commonCheckin ? ["Опция «Общая регистрация на тех же стойках»: вкл."] : []),
            ...(considerSlf ? ["Опция «Учитывать SLF»: вкл."] : []),
            ...(forecastMode ? ["Режим прогноза по истории: вкл."] : []),
            "Подключите NEXT_PUBLIC_USE_MOCK=false и бэкенд для реальной статистики по БД.",
          ],
        };
        setResult(mock);
      } else {
        const res = await api.runDistribution(body);
        setResult(res);
        if (res.ok) {
          await onApplied?.();
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка запроса");
    } finally {
      setBusy(false);
    }
  }, [
    allocations.length,
    airlinesSorted.length,
    commonCheckin,
    considerSlf,
    forecastMode,
    flightsByAirline,
    dateFrom,
    dateTo,
    distributionType,
    selectedAirlines,
    selectedFlights,
    useMock,
    onApplied,
  ]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/65 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="distribution-modal-title"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-lg border border-dispatch-border bg-[#0d1728] shadow-2xl">
        <div className="flex items-center justify-between border-b border-dispatch-border bg-[#111e31] px-4 py-3">
          <h2 id="distribution-modal-title" className="text-lg font-semibold text-white">
            Распределение
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-dispatch-border px-3 py-1 text-sm text-dispatch-muted hover:bg-white/10 hover:text-white"
          >
            Закрыть
          </button>
        </div>

        <div className="flex flex-wrap items-end gap-3 border-b border-dispatch-border/80 bg-[#111e31]/80 px-4 py-3">
          <button
            type="button"
            onClick={() => void run()}
            disabled={busy}
            className="flex items-center gap-2 rounded-md bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-600 disabled:cursor-wait disabled:opacity-60"
          >
            <span aria-hidden>▶</span>
            {busy ? "Выполняется…" : "Старт"}
          </button>
          <label className="flex flex-col gap-0.5 text-xs text-dispatch-muted">
            <span>С</span>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="rounded border border-dispatch-border bg-dispatch-bg px-2 py-1.5 text-sm text-white"
            />
          </label>
          <label className="flex flex-col gap-0.5 text-xs text-dispatch-muted">
            <span>По</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="rounded border border-dispatch-border bg-dispatch-bg px-2 py-1.5 text-sm text-white"
            />
          </label>
          <label className="flex min-w-[200px] flex-col gap-0.5 text-xs text-dispatch-muted">
            <span>Тип распределения</span>
            <select
              value={distributionType}
              onChange={(e) =>
                setDistributionType(e.target.value as "selected_groups" | "all_flights")
              }
              className="rounded border border-dispatch-border bg-dispatch-bg px-2 py-1.5 text-sm text-white"
            >
              <option value="selected_groups">Выбранные группы</option>
              <option value="all_flights">Все рейсы периода</option>
            </select>
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-xs text-gray-300">
            <input
              type="checkbox"
              checked={commonCheckin}
              onChange={(e) => setCommonCheckin(e.target.checked)}
              className="rounded border-dispatch-border"
            />
            Общая регистрация на тех же стойках
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-xs text-gray-300">
            <input
              type="checkbox"
              checked={considerSlf}
              onChange={(e) => setConsiderSlf(e.target.checked)}
              className="rounded border-dispatch-border"
            />
            Учитывать SLF
          </label>
        </div>

        {error && (
          <div className="mx-4 mt-2 rounded border border-red-500/50 bg-red-950/40 px-3 py-2 text-sm text-red-200">
            {error}
          </div>
        )}

        <div className="flex min-h-0 flex-1 gap-2 overflow-hidden p-3">
          <aside className="flex w-56 shrink-0 flex-col gap-2 rounded border border-dispatch-border/60 bg-[#111e31]/90 p-3 text-xs">
            <div className="font-bold uppercase tracking-wide text-blue-400">Сценарий</div>
            <div>
              <div className="text-dispatch-muted">План</div>
              <div className="text-white">MasterPlan (импорт / дашборд)</div>
            </div>
            <div>
              <div className="text-dispatch-muted">Создан</div>
              <div className="text-white">{new Date().toLocaleString("ru-RU")}</div>
            </div>
            <div>
              <div className="text-dispatch-muted">Пользователь</div>
              <div className="text-white">Диспетчер</div>
            </div>
            <p className="mt-2 leading-relaxed text-dispatch-muted">
              Полный пересчёт слотов алгоритмом можно подключить к POST{" "}
              <code className="text-[10px] text-blue-300">/distribution/run</code>.
            </p>
          </aside>

          <section className="flex min-w-0 flex-1 flex-col overflow-hidden rounded border border-dispatch-border/60 bg-[#0a1424]">
            <div className="flex items-center justify-between border-b border-dispatch-border/60 px-2 py-1.5">
              <span className="text-xs font-semibold text-gray-300">Сервисные группы (авиакомпании)</span>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={selectAllAirlines}
                  className="text-xs text-blue-400 hover:underline"
                >
                  Все
                </button>
                <button
                  type="button"
                  onClick={clearAirlines}
                  className="text-xs text-blue-400 hover:underline"
                >
                  Снять
                </button>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-auto">
              <table className="w-full border-collapse text-left text-xs">
                <thead className="sticky top-0 z-[1] bg-[#111e31]">
                  <tr className="border-b border-dispatch-border text-dispatch-muted">
                    <th className="w-10 px-2 py-2"> </th>
                    <th className="px-2 py-2">Авиакомпания</th>
                    <th className="w-36 px-2 py-2">Рейсы</th>
                  </tr>
                </thead>
                <tbody>
                  {airlinesSorted.length === 0 ? (
                    <tr>
                      <td colSpan={3} className="px-3 py-6 text-center text-dispatch-muted">
                        Нет данных об авиакомпаниях в текущих аллокациях. Загрузите день в дашборде.
                      </td>
                    </tr>
                  ) : (
                    airlinesSorted.map((name) => (
                      <Fragment key={name}>
                        <tr className="border-b border-dispatch-border/40 hover:bg-white/[0.03]">
                          <td className="px-2 py-1.5">
                            <input
                              type="checkbox"
                              checked={selectedAirlines.has(name)}
                              onChange={() => toggleAirline(name)}
                              disabled={distributionType === "all_flights"}
                              aria-label={`Включить ${name}`}
                            />
                          </td>
                          <td className="px-2 py-1.5 text-white">{name}</td>
                          <td className="px-2 py-1.5">
                            <button
                              type="button"
                              onClick={() => toggleAirlineExpand(name)}
                              className="rounded border border-dispatch-border px-2 py-1 text-[11px] text-blue-300 hover:bg-white/10"
                            >
                              {expandedAirlines.has(name) ? "Скрыть" : "Рейсы"}
                            </button>
                          </td>
                        </tr>
                        {expandedAirlines.has(name) && (
                          <tr className="border-b border-dispatch-border/30 bg-[#0f1a2a]">
                            <td />
                            <td colSpan={2} className="px-2 py-2">
                              <div className="flex max-h-28 flex-wrap gap-3 overflow-auto text-[11px] text-gray-300">
                                {(flightsByAirline[name] ?? []).map((fn) => (
                                  <label key={`${name}-${fn}`} className="inline-flex items-center gap-1.5">
                                    <input
                                      type="checkbox"
                                      checked={(selectedFlights[name] ?? new Set()).has(fn)}
                                      onChange={() => toggleFlight(name, fn)}
                                      disabled={!selectedAirlines.has(name)}
                                    />
                                    <span>{fn}</span>
                                  </label>
                                ))}
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="flex w-72 shrink-0 flex-col overflow-hidden rounded border border-dispatch-border/60 bg-[#0a1424]">
            <div className="border-b border-dispatch-border/60 px-2 py-1.5 text-xs font-semibold text-gray-300">
              Результат
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-2">
              {!result ? (
                <p className="text-xs text-dispatch-muted">Нажмите «Старт», чтобы выполнить анализ периода.</p>
              ) : (
                <div className="space-y-2 text-xs">
                  <p className="font-medium text-emerald-400">{result.message}</p>
                  <ul className="space-y-1 text-dispatch-muted">
                    <li>Рейсов в периоде: {result.flights_in_period}</li>
                    <li>Авиакомпаний (уник.): {result.airlines_considered}</li>
                    <li>Ручных аллокаций: {result.manual_allocations_touched}</li>
                    <li>Время: {result.duration_ms} мс</li>
                  </ul>
                  <pre className="mt-2 whitespace-pre-wrap break-words rounded border border-dispatch-border/50 bg-black/30 p-2 font-mono text-[11px] text-gray-300">
                    {result.log.join("\n")}
                  </pre>
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
