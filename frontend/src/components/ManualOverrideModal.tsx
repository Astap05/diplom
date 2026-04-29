"use client";

import { useState, useEffect, useMemo } from "react";
import { api } from "@/lib/api";
import type { AllocationForDashboard, Resource, ModificationInfo, SimilarFlightHistoryItem } from "@/lib/types";

interface ManualOverrideModalProps {
  allocation: AllocationForDashboard | null;
  resources: Resource[];
  onClose: () => void;
  onSave?: (allocationId: number, resourceId: number, startTime: string, endTime: string) => Promise<void> | void;
  readOnly?: boolean;
  modification?: ModificationInfo;
}

function fmt(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function fmtShort(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function asNum(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function asInt(v: unknown): number | null {
  const n = asNum(v);
  if (n === null) return null;
  return Math.max(0, Math.round(n));
}

function pickAircraftType(
  extra: Record<string, unknown>,
  fallback: string | null | undefined
): string | undefined {
  const fromExtra =
    String(
      extra["Полное назв ВС (Рус)"] ??
      extra["Тип ВС (IATA)"] ??
      extra["Тип ВС"] ??
      extra["predicted_aircraft_type"] ??
      ""
    ).trim();
  if (fromExtra) return fromExtra;

  const fb = String(fallback ?? "").trim();
  if (!fb) return undefined;

  const tails = Array.isArray(extra["predicted_aircraft_tails"])
    ? (extra["predicted_aircraft_tails"] as unknown[]).map((x) => String(x ?? "").trim()).filter(Boolean)
    : [];
  if (tails.includes(fb)) return undefined;
  return fb;
}

function formatAircraftTypesStats(extra: Record<string, unknown>): string | undefined {
  const raw = extra["predicted_aircraft_types"];
  if (!Array.isArray(raw) || raw.length === 0) return undefined;
  const parts = raw
    .map((it) => {
      if (!it || typeof it !== "object") return "";
      const obj = it as Record<string, unknown>;
      const t = String(obj["type"] ?? "").trim();
      if (!t) return "";
      const p = Number(obj["share_pct"]);
      if (Number.isFinite(p)) return `${t} (${p.toFixed(1)}%)`;
      return t;
    })
    .filter(Boolean);
  return parts.length ? parts.join(", ") : undefined;
}

const AIRPORT_NAME_BY_CODE: Record<string, string> = {
  MSQ: "Минск",
  AFL: "Москва",
  FDB: "Дубай",
  BRU: "Брюссель",
  UZB: "Ташкент",
  KAR: "Багдад",
  MOW: "Москва",
  SVO: "Москва (Шереметьево)",
  DME: "Москва (Домодедово)",
  VKO: "Москва (Внуково)",
  LED: "Санкт-Петербург",
  AER: "Сочи",
  IST: "Стамбул",
  AYT: "Анталья",
  DXB: "Дубай",
  SHJ: "Шарджа",
  SSH: "Шарм-эль-Шейх",
  HRG: "Хургада",
  TBS: "Тбилиси",
  EVN: "Ереван",
  TAS: "Ташкент",
  TIV: "Тиват",
  GYD: "Баку",
  ALA: "Алматы",
  NQZ: "Астана",
  BJS: "Пекин",
  NOZ: "Новокузнецк",
  BAK: "Баку",
  WAW: "Варшава",
  FRA: "Франкфурт",
  BER: "Берлин",
  PRG: "Прага",
  FCO: "Рим",
  BCN: "Барселона",
  PAR: "Париж",
  LON: "Лондон",
};

function airportDisplay(codeOrName: unknown, fallback?: unknown): string | undefined {
  const raw = String(codeOrName ?? "").trim();
  if (!raw) {
    const fb = String(fallback ?? "").trim();
    return fb || undefined;
  }
  // Если уже полное название, оставляем как есть.
  if (raw.length > 3) return raw;
  const code = raw.toUpperCase();
  if (AIRPORT_NAME_BY_CODE[code]) return AIRPORT_NAME_BY_CODE[code];
  const fb = String(fallback ?? "").trim().toUpperCase();
  if (fb && AIRPORT_NAME_BY_CODE[fb]) return AIRPORT_NAME_BY_CODE[fb];
  return code;
}

function Section({
  title,
  children,
  wide = false,
}: {
  title: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <div className={`mb-1 ${wide ? "md:col-span-2" : ""}`}>
      <h4 className="mb-1.5 border-b border-dispatch-border pb-1 text-xs font-bold uppercase tracking-wider text-blue-400">
        {title}
      </h4>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-sm">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | number | null | undefined }) {
  if (value === null || value === undefined || value === "" || value === "—" || value === "nan" || value === "NaN" || value === "NaT" || value === 0 || value === "0" || value === "0.0") return null;
  const display = typeof value === "number" ? String(value) : value;
  return (
    <div className="col-span-2 flex items-baseline gap-2 py-0.5">
      <span className="min-w-[140px] shrink-0 text-xs text-dispatch-muted">{label}</span>
      <span className="text-xs text-white">{display}</span>
    </div>
  );
}

function RowWide({ label, value }: { label: string; value: string | number | null | undefined }) {
  if (value === null || value === undefined || value === "" || value === "nan") return null;
  return (
    <div className="col-span-2 py-0.5">
      <span className="text-xs text-dispatch-muted">{label}: </span>
      <span className="text-xs text-white">{typeof value === "number" ? String(value) : value}</span>
    </div>
  );
}

function SeatLoadPie({ pax, seats, size = 10 }: { pax: number; seats: number; size?: number }) {
  const safeSeats = Math.max(1, Math.round(seats));
  const safePax = Math.max(0, Math.min(Math.round(pax), safeSeats));
  const free = Math.max(0, safeSeats - safePax);
  const pct = Math.max(0, Math.min(100, (safePax / safeSeats) * 100));
  const gradient = `conic-gradient(#3b82f6 0% ${pct.toFixed(1)}%, rgba(255,255,255,0.14) ${pct.toFixed(1)}% 100%)`;
  return (
    <div className="group relative flex items-center justify-center">
      <div
        className="rounded-full border border-white/30 shadow-[inset_0_1px_2px_rgba(255,255,255,0.2),0_1px_2px_rgba(0,0,0,0.45)]"
        style={{ background: gradient, width: `${size * 4}px`, height: `${size * 4}px` }}
        title={`Пассажиры: ${safePax}; Кресла: ${safeSeats}; Свободно: ${free}; Загрузка: ${pct.toFixed(1)}%`}
        aria-label={`Загрузка ${pct.toFixed(1)} процентов`}
      />
      <div className="pointer-events-none absolute left-full top-1/2 z-20 ml-2 hidden -translate-y-1/2 whitespace-nowrap rounded border border-dispatch-border bg-[#0b1422] px-2 py-1 text-[10px] leading-tight text-white shadow-lg group-hover:block">
        <div>Пассажиры: <span className="text-cyan-300">{safePax}</span></div>
        <div>Кресла: <span className="text-amber-300">{safeSeats}</span></div>
        <div>Свободно: {free}</div>
        <div>Загрузка: {pct.toFixed(1)}%</div>
      </div>
    </div>
  );
}

export default function ManualOverrideModal({
  allocation,
  resources,
  onClose,
  onSave,
  readOnly = false,
  modification,
}: ManualOverrideModalProps) {
  const [selectedResourceId, setSelectedResourceId] = useState<number>(allocation?.resource_id ?? 0);
  const [recentRows, setRecentRows] = useState<SimilarFlightHistoryItem[]>([]);
  const [recentLoading, setRecentLoading] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (allocation) setSelectedResourceId(allocation.resource_id);
  }, [allocation?.id]);

  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!allocation) {
      setRecentRows([]);
      return;
    }
    let cancelled = false;
    setRecentLoading(true);
    api
      .getSimilarFlightHistory({
        flight_number: allocation.flight_number,
        airline: allocation.airline,
        exclude_flight_id: allocation.flight_id,
        reference_plan_time: allocation.plan_time ?? undefined,
        limit: 7,
      })
      .then((rows) => {
        if (!cancelled) setRecentRows(rows);
      })
      .catch(() => {
        if (!cancelled) setRecentRows([]);
      })
      .finally(() => {
        if (!cancelled) setRecentLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [allocation?.flight_id, allocation?.flight_number, allocation?.airline]);

  const extra = useMemo(() => {
    if (!allocation?.extra_data) return null;
    try { return JSON.parse(allocation.extra_data); } catch { return null; }
  }, [allocation?.extra_data]);

  const sameTypeResources = resources.filter((r) => r.resource_type === allocation?.resource_type);
  const unchanged = selectedResourceId === (allocation?.resource_id ?? 0);
  const showRealFields = !readOnly;
  const extraObj = extra ?? {};
  const e = extraObj;
  const aircraftTypeDisplay = pickAircraftType(e, allocation?.aircraft_type);
  const aircraftTypesStats = formatAircraftTypesStats(e);
  const aircraftTypesStatsFromRecent = useMemo(() => {
    if (!recentRows.length) return undefined;
    const counts = new Map<string, number>();
    for (const r of recentRows) {
      const t = String(r.aircraft_type ?? "").trim();
      if (!t) continue;
      counts.set(t, (counts.get(t) ?? 0) + 1);
    }
    const total = Array.from(counts.values()).reduce((a, b) => a + b, 0);
    if (!total) return undefined;
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([t, c]) => `${t} (${((c / total) * 100).toFixed(1)}%)`)
      .join(", ");
  }, [recentRows]);
  const aircraftTypesStatsDisplay = aircraftTypesStatsFromRecent ?? aircraftTypesStats;
  const startMs = new Date((allocation?.start_time ?? "") as string).getTime();
  const endMs = new Date((allocation?.end_time ?? "") as string).getTime();
  const depFactMs = new Date(((e["Дата/Время отпр. факт"] as string | undefined) ?? allocation?.fact_time ?? "") as string).getTime();
  const hasPastDepartureFact = Number.isFinite(depFactMs) && depFactMs <= nowMs;
  const isFuture = !readOnly && Number.isFinite(startMs) && nowMs < startMs;
  const isInWork = !readOnly && Number.isFinite(startMs) && Number.isFinite(endMs) && nowMs >= startMs && nowMs < endMs;
  const isDelayedNow = !readOnly && !!allocation?.is_delayed;
  const isRegistrationFinished = !readOnly && Number.isFinite(endMs) && nowMs >= endMs;
  const canShowRealFacts = showRealFields && isRegistrationFinished && hasPastDepartureFact;
  const canShowPassengerFacts = !showRealFields || isRegistrationFinished;

  const handleSave = () => {
    if (unchanged) return;
    if (!allocation) return;
    onSave?.(allocation.id, selectedResourceId, allocation.start_time, allocation.end_time);
    onClose();
  };

  const hasCargoData = [
    e["Вес багажа"],
    e["Кол-во мест багажа"],
    e["Груз (кг)"],
    e["Почта (кг)"],
    e["Вес ручной клади"],
  ].some((v) => v !== null && v !== undefined && v !== "" && String(v).trim() !== "" && String(v) !== "0" && String(v) !== "0.0");
  const paxForSectionPie =
    asInt(e["Пассаж. всего"] ?? asNum(e["predicted_pax_total"])) ??
    asInt(allocation?.passengers_count ?? null) ??
    null;
  const seatsForSectionPie =
    asInt(e["Кол-во кресел"] ?? e["Кол-во кресел для типа ВС (макс.)"]) ??
    (paxForSectionPie != null ? Math.max(1, paxForSectionPie) : null);

  const rtRaw = (allocation?.resource_type ?? "").trim().toLowerCase().replaceAll("_", "-");
  const rt = rtRaw === "gate" || rtRaw === "gates" ? "gate" : "check-in";

  if (!allocation) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="max-h-[90vh] w-full max-w-4xl overflow-hidden rounded-xl border border-dispatch-border bg-[#0d1728] shadow-2xl"
        onClick={(ev) => ev.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-dispatch-border bg-[#111e31] px-5 py-3">
          <div>
            <h3 className="text-lg font-bold text-white">{allocation.flight_number}</h3>
            <p className="text-xs text-dispatch-muted">{allocation.airline} · {aircraftTypeDisplay ?? "—"}</p>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold ${
                readOnly
                  ? "bg-emerald-500/20 text-emerald-400"
                  : isDelayedNow
                    ? `bg-orange-500/20 text-orange-300 ${isInWork ? "animate-pulse" : ""}`
                    : `bg-emerald-500/20 text-emerald-400 ${isInWork ? "animate-pulse" : ""}`
              }`}
            >
              {readOnly
                ? "ПЛАН"
                : isFuture
                  ? "ПО ПЛАНУ"
                  : isInWork
                    ? `В РАБОТЕ · ${isDelayedNow ? "ЗАДЕРЖКА" : "ПО ПЛАНУ"}`
                    : (isDelayedNow ? "ЗАДЕРЖКА" : "ПО ПЛАНУ")}
            </span>
            <button onClick={onClose} className="ml-2 text-dispatch-muted hover:text-white transition-colors text-lg leading-none">✕</button>
          </div>
        </div>

        {/* Modification banner */}
        {modification && (
          <div className="mx-5 mt-3 rounded-lg border border-yellow-600/50 bg-yellow-500/10 px-4 py-2.5">
            <p className="text-xs font-bold uppercase tracking-wider text-yellow-400 mb-1">Изменено диспетчером</p>
            <p className="text-sm text-yellow-200">
              {modification.oldResourceName} → {allocation.resource_name}
            </p>
          </div>
        )}

        {/* Scrollable body */}
        <div className="overflow-y-auto px-5 py-3 dashboard-scroll" style={{ maxHeight: modification ? "calc(90vh - 190px)" : "calc(90vh - 130px)" }}>

          {rt === "gate" ? (
            /* ===== ВЫХОДЫ НА ПОСАДКУ ===== */
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 md:gap-4">
              <Section title="Рейс">
                <Row label="Номер рейса" value={allocation.flight_number} />
                <Row label="Авиакомпания" value={e["Название АК"] ?? allocation.airline} />
                <Row label="Тип ВС" value={aircraftTypeDisplay} />
              </Section>

              <Section title="Маршрут">
                <Row
                  label="АП назначения"
                  value={airportDisplay(e["АП Прибытия (полное, рус)"], allocation.ru_airport ?? allocation.airport)}
                />
                <Row label="Код (IATA)" value={e["Код АП Прибытия (IATA)"] ?? allocation.airport} />
                <Row label="Терминал" value={e["Терминал"]} />
              </Section>

              <Section title="Время вылета">
                <Row label="Отпр. план" value={fmt(e["Дата/Время отпр. план"] ?? allocation.plan_time)} />
                {canShowRealFacts && <Row label="Отпр. факт" value={fmt(e["Дата/Время отпр. факт"] ?? allocation.fact_time)} />}
                {canShowRealFacts && <Row label="Задержка (мин)" value={e["Время задержки (мин)"]} />}
                {canShowRealFacts && <RowWide label="Причина задержки" value={e["Причина задержки (текст)"]} />}
              </Section>

              <Section title="Ресурсы">
                <Row label="Выход (по расписанию)" value={e["Выходы на посадку"] ?? e["predicted_gate_set"] ?? allocation.resource_name} />
                <Row label="№ Стоянки" value={e["№ Стоянки"]} />
                {modification
                  ? <Row label="Текущий выход" value={`${modification.oldResourceName} → ${allocation.resource_name}`} />
                  : <Row label="Текущий выход" value={allocation.resource_name} />
                }
                <Row label="Интервал (план)" value={`${fmtShort(allocation.plan_start_time ?? allocation.start_time)} – ${fmtShort(allocation.plan_end_time ?? allocation.end_time)}`} />
                {canShowRealFacts && <Row label="Интервал (факт)" value={`${fmtShort(allocation.start_time)} – ${fmtShort(allocation.end_time)}`} />}
              </Section>

              <Section title="Пассажиры">
                {canShowPassengerFacts && <Row label="Пассажиры всего" value={e["Пассаж. всего"] ?? asInt(e["predicted_pax_total"])} />}
                {canShowPassengerFacts && <Row label="Бизнес-класс" value={e["Пассаж. Бизнес"] ?? asInt(e["predicted_pax_biz"])} />}
                {canShowPassengerFacts && <Row label="Эконом-класс" value={e["Пассаж. Эконом"] ?? asInt(e["predicted_pax_econ"])} />}
                {canShowPassengerFacts && <Row label="Инвалиды на борту" value={e["Количество инвалидов на борту"]} />}
                {canShowPassengerFacts && <Row label="Дети без сопровождения" value={e["Количество детей без сопровождения"]} />}
              </Section>
            </div>
          ) : (
            /* ===== СТОЙКИ РЕГИСТРАЦИИ (полная информация) ===== */
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 md:gap-4">
              <Section title="Основная информация">
                <Row label="Номер рейса" value={allocation.flight_number} />
                <Row label="ID рейса (XML)" value={allocation.external_flight_id} />
                <Row label="Авиакомпания" value={e["Название АК"] ?? allocation.airline} />
                <Row label="Код АК IATA" value={e["Код АК IATA"]} />
                <Row label="Код АК ICAO" value={e["Код АК ICAO"]} />
                <Row label="Тип ВС" value={aircraftTypeDisplay} />
                <Row label="Тип ВС (IATA)" value={e["Тип ВС (IATA)"]} />
                <Row label="Вид движения" value={e["Вид движения"]} />
                <Row label="Вид рейса" value={e["Вид рейса"]} />
                <Row label="Вид направления" value={e["Вид направления"]} />
                <Row label="Признак рейса" value={e["Признак рейса"]} />
                <Row label="Тип рейса" value={e["Тип рейса"]} />
              </Section>

              <Section title="Маршрут">
                <Row label="АП Отправления" value={airportDisplay(e["АП Отправления (полное, рус)"], "Минск")} />
                <Row label="Код вылета (IATA)" value={e["Код АП вылета (IATA)"] ?? "MSQ"} />
                <Row
                  label="АП Прибытия"
                  value={airportDisplay(e["АП Прибытия (полное, рус)"], allocation.ru_airport ?? allocation.airport)}
                />
                <Row label="Код прибытия (IATA)" value={e["Код АП Прибытия (IATA)"] ?? allocation.airport} />
                <RowWide
                  label="Маршрут"
                  value={
                    e["Маршрут (полн.)"] ??
                    `Минск → ${airportDisplay(allocation.ru_airport ?? allocation.airport, allocation.airport) ?? "—"}`
                  }
                />
                <Row label="Страна отправления" value={e["Страна отправления"]} />
                <Row label="Страна прибытия" value={e["Страна прибытия"]} />
                <Row label="Терминал" value={e["Терминал"]} />
              </Section>

              <Section title="Время">
                <Row label="Отпр. план" value={fmt(e["Дата/Время отпр. план"] ?? allocation.plan_time)} />
                {canShowRealFacts && <Row label="Отпр. факт" value={fmt(e["Дата/Время отпр. факт"] ?? allocation.fact_time)} />}
                <Row label="Приб. план" value={fmt(e["Дата/Время приб. план"])} />
                {canShowRealFacts && <Row label="Приб. факт" value={fmt(e["Дата/Время приб. факт"])} />}
                {canShowRealFacts && <Row label="Взлёт" value={fmt(e["Дата/Время взлета"])} />}
                {canShowRealFacts && <Row label="Посадка" value={fmt(e["Дата/Время посадки"])} />}
                {canShowRealFacts && <Row label="Ожидаемое прибытие" value={fmt(e["Время ожидаемого прибытия"])} />}
                <Row label="Время в полёте (план)" value={fmt(e["Время в полете план"])} />
                {canShowRealFacts && <Row label="Задержка (мин)" value={e["Время задержки (мин)"]} />}
                {canShowRealFacts && <Row label="Задержка" value={e["Время задержки (ч:мм) (отн)"]} />}
                {canShowRealFacts && <Row label="Код задержки" value={e["Код задержки"]} />}
                {canShowRealFacts && <RowWide label="Причина задержки" value={e["Причина задержки (текст)"]} />}
                {canShowRealFacts && <Row label="Пунктуальность" value={e["Пунктуальность "] === true ? "Да" : e["Пунктуальность "] === false ? "Нет" : undefined} />}
              </Section>

              <Section title="Ресурсы аэропорта">
                <Row label="Стойки (по расписанию)" value={e["Стойки регистрации"] ?? e["predicted_counter_set"]} />
                <Row label="Выходы на посадку" value={e["Выходы на посадку"]} />
                <Row label="№ Стоянки" value={e["№ Стоянки"]} />
                {modification
                  ? <Row label="Текущий ресурс" value={`${modification.oldResourceName} → ${allocation.resource_name}`} />
                  : <Row label="Текущий ресурс" value={`${allocation.resource_name} (${allocation.resource_type})`} />
                }
                <Row label="Интервал (план)" value={`${fmtShort(allocation.plan_start_time ?? allocation.start_time)} – ${fmtShort(allocation.plan_end_time ?? allocation.end_time)}`} />
                {canShowRealFacts && <Row label="Интервал (факт)" value={`${fmtShort(allocation.start_time)} – ${fmtShort(allocation.end_time)}`} />}
              </Section>

              <div className="mb-1">
                <h4 className="mb-1.5 border-b border-dispatch-border pb-1 text-xs font-bold uppercase tracking-wider text-blue-400">
                  Пассажиры и загрузка
                </h4>
                <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-3">
                  <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-sm">
                    {canShowPassengerFacts && (
                      <Row
                        label="Пассажиры всего"
                        value={showRealFields ? asInt(e["Пассаж. всего"] ?? asNum(e["predicted_pax_total"])) : (e["Пассаж. всего"] ?? asNum(e["predicted_pax_total"]))}
                      />
                    )}
                    {canShowPassengerFacts && (
                      <Row
                        label="Бизнес-класс"
                        value={showRealFields ? asInt(e["Пассаж. Бизнес"] ?? asNum(e["predicted_pax_biz"])) : (e["Пассаж. Бизнес"] ?? asNum(e["predicted_pax_biz"]))}
                      />
                    )}
                    {canShowPassengerFacts && <Row label="Комфорт-класс" value={e["Пассаж. Комфорт"]} />}
                    {canShowPassengerFacts && (
                      <Row
                        label="Эконом-класс"
                        value={showRealFields ? asInt(e["Пассаж. Эконом"] ?? asNum(e["predicted_pax_econ"])) : (e["Пассаж. Эконом"] ?? asNum(e["predicted_pax_econ"]))}
                      />
                    )}
                    {canShowPassengerFacts && <Row label="Транзит" value={e["Пассаж. транзит всего"]} />}
                    {canShowPassengerFacts && <Row label="Кол-во кресел" value={e["Кол-во кресел"]} />}
                    {canShowPassengerFacts && <Row label="Занятые кресла" value={e["Занятые кресла"]} />}
                    {canShowPassengerFacts && <Row label="Загрузка (%)" value={e["Процент загрузки кресел"] ? `${e["Процент загрузки кресел"]}%` : undefined} />}
                    {canShowPassengerFacts && <Row label="Проданные билеты" value={e["Проданные билеты Всего"]} />}
                  </div>
                  {canShowPassengerFacts && paxForSectionPie != null && seatsForSectionPie != null && (
                    <div className="flex items-center justify-center pr-1">
                      <SeatLoadPie pax={paxForSectionPie} seats={seatsForSectionPie} size={14} />
                    </div>
                  )}
                </div>
              </div>

              {hasCargoData && (
                <Section title="Багаж и груз">
                  <Row label="Вес багажа (кг)" value={e["Вес багажа"]} />
                  <Row label="Кол-во мест багажа" value={e["Кол-во мест багажа"]} />
                  <Row label="Груз (кг)" value={e["Груз (кг)"]} />
                  <Row label="Почта (кг)" value={e["Почта (кг)"]} />
                  <Row label="Вес ручной клади" value={e["Вес ручной клади"]} />
                </Section>
              )}

              <Section title="Воздушное судно">
                <Row label="Тип ВС" value={aircraftTypeDisplay} />
                <RowWide label="Типы ВС (история, %)" value={aircraftTypesStatsDisplay} />
                <Row label="Тип ВС (лат)" value={e["Полное назв ВС (Лат)"]} />
                <Row label="Макс. взлётная масса" value={e["Максимальная взлетная масса"]} />
                {showRealFields && <Row label="Факт. взлётная масса" value={e["Фактическая взлетная масса"]} />}
                <Row label="Кол-во кресел (макс.)" value={e["Кол-во кресел для типа ВС (макс.)"]} />
              </Section>

              {(e["Обслуживающая компания"] || e["Плательщик"] || e["Примечание"]) && (
                <Section title="Дополнительно" wide>
                  <RowWide label="Обслуживающая компания" value={e["Обслуживающая компания"]} />
                  <RowWide label="Плательщик" value={e["Плательщик"]} />
                  <RowWide label="Примечание" value={e["Примечание"]} />
                  <Row label="Инвалиды на борту" value={e["Количество инвалидов на борту"]} />
                  <Row label="Дети без сопровождения" value={e["Количество детей без сопровождения"]} />
                  <Row label="Duty Free" value={e["Обслуживание товаров Duty Free"]} />
                </Section>
              )}
            </div>
          )}

          <div className="mt-4 rounded-lg border border-blue-500/40 bg-blue-950/25 p-3">
            <div className="mb-2 flex items-center justify-between">
              <h4 className="text-xs font-bold uppercase tracking-wider text-blue-300">
                Последние рейсы
              </h4>
              {recentLoading && <span className="text-[11px] text-blue-200/80">Загрузка...</span>}
            </div>
            {recentRows.length === 0 ? (
              <p className="text-xs text-dispatch-muted">
                Нет истории по этому рейсу.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-blue-500/30 text-blue-200">
                      <th className="px-2 py-1 text-left font-semibold">Дата рейса</th>
                      <th className="px-2 py-1 text-left font-semibold">Тип ВС</th>
                      <th className="px-2 py-1 text-left font-semibold">Время регистрации</th>
                      <th className="px-2 py-1 text-left font-semibold">Занятые стойки</th>
                      <th className="px-2 py-1 text-left font-semibold">Пассажиры</th>
                      <th className="px-2 py-1 text-left font-semibold">Диаграмма</th>
                      <th className="px-2 py-1 text-left font-semibold">Кресла</th>
                      <th className="px-2 py-1 text-left font-semibold">Статус</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentRows.map((r, idx) => (
                      <tr key={`${r.date}-${idx}`} className="border-b border-dispatch-border/40 text-white/95">
                        <td className="px-2 py-1.5">{r.date}</td>
                        <td className="px-2 py-1.5">{r.aircraft_type}</td>
                        <td className="px-2 py-1.5">{r.checkin_interval}</td>
                        <td className="px-2 py-1.5">{r.counters}</td>
                        <td className="px-2 py-1.5">{r.pax_total}</td>
                        <td className="px-2 py-1.5"><SeatLoadPie pax={r.pax_total} seats={r.seats_total} /></td>
                        <td className="px-2 py-1.5">{r.seats_total}</td>
                        <td className={`px-2 py-1.5 font-semibold ${r.status === "Задержка" ? "text-orange-300" : "text-emerald-300"}`}>
                          {r.status}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Resource change (hidden in read-only / plan mode) */}
          {!readOnly && (
            <div className="mt-3 rounded-lg border border-dispatch-border bg-[#111e31] p-3">
              <label className="mb-1.5 block text-xs font-semibold text-blue-400 uppercase tracking-wider">
                Изменить ресурс
              </label>
              <select
                className="w-full rounded border border-dispatch-border bg-dispatch-bg px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                value={selectedResourceId}
                onChange={(ev) => setSelectedResourceId(Number(ev.target.value))}
              >
                {sameTypeResources.map((r) => (
                  <option key={r.id} value={r.id}>{r.name}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 border-t border-dispatch-border bg-[#111e31] px-5 py-3">
          <button type="button" onClick={onClose} className="rounded-lg border border-dispatch-border px-4 py-2 text-sm text-white hover:bg-dispatch-border transition-colors">
            Закрыть
          </button>
          {!readOnly && (
            <button
              type="button"
              onClick={handleSave}
              disabled={unchanged}
              className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Сохранить
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
