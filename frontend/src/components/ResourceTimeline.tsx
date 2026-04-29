"use client";

import { useMemo, useRef, useEffect, useLayoutEffect, useCallback, useState, memo } from "react";
import type { Resource, AllocationForDashboard, ModificationInfo } from "@/lib/types";
import CheckinLoadChart, {
  CHECKIN_LOAD_CHART_PAD,
  computeCheckinLoadSegments,
} from "@/components/CheckinLoadChart";

interface ResourceTimelineProps {
  resources: Resource[];
  allocations: AllocationForDashboard[];
  selectedDate: Date;
  /** День, который сейчас в фокусе по горизонтальному скроллу (для внешних фильтров). */
  onVisibleDayChange?: (date: Date) => void;
  onItemClick?: (allocation: AllocationForDashboard) => void;
  conflictIds?: Set<number>;
  modifications?: Map<number, ModificationInfo>;
  viewMode?: "plan" | "real";
  /** График суммарной загруженности стоек (только для вкладки «Стойки»). */
  showCheckinLoadChart?: boolean;
}

const RESOURCE_TYPE_ORDER: Record<string, number> = {
  "check-in": 0,
  gate: 1,
};

const BAR_COLORS: Record<string, string> = {
  "item-normal": "#3b82f6",
  "item-delayed": "#f59e0b",
  "item-working": "#22c55e",
  "item-conflict": "#ef4444",
  "item-cancelled": "#94a3b8",
  "item-modified": "#fade2c",
};

const LABEL_W = 120;
/** Высота SVG графика загруженности; подпись оси — сверху в той же строке. */
const LOAD_CHART_H = 176;
const LOAD_CHART_TITLE_H = 48;
const LOAD_CHART_ROW_H = LOAD_CHART_TITLE_H + LOAD_CHART_H;
/** Полоса с кнопкой сворачивания над графиком. */
const LOAD_CHART_TOOLBAR_H = 38;
const ROW_H = 82;
const EXPANDED_ROW_H = 72;
const MIN_PX_PER_HOUR = 30;
const MAX_PX_PER_HOUR = 3000;
const DEFAULT_PX_PER_HOUR = 80;
const VIEWPORT_BUFFER = 200; // px buffer on each side for smoother scrolling

function resourceLabel(resourceType: string, name: string) {
  if (resourceType === "check-in") return `Стойка ${name}`;
  if (resourceType === "gate") return `Выход ${name}`;
  return name;
}

function numericName(name: string): number | null {
  const m = (name || "").trim().match(/^(\d+)$/);
  return m ? Number(m[1]) : null;
}

function hhmm(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

function shortText(value: string | null | undefined, max = 20) {
  const v = (value ?? "").trim();
  if (!v) return "—";
  return v.length > max ? `${v.slice(0, max - 1)}…` : v;
}

/** Ручное изменение ресурса: из API (после перезагрузки) или из карты (legacy/моки). */
export function getAllocationModification(
  a: AllocationForDashboard,
  fallback?: Map<number, ModificationInfo>
): ModificationInfo | undefined {
  if (
    a.original_resource_id != null &&
    a.original_resource_id !== a.resource_id &&
    a.original_resource_name
  ) {
    return {
      oldResourceName: a.original_resource_name,
      newResourceName: a.resource_name,
      oldResourceType: a.original_resource_type ?? a.resource_type,
    };
  }
  return fallback?.get(a.id);
}

function effectiveStart(a: AllocationForDashboard, mode: "plan" | "real"): string {
  if (mode === "plan" && a.plan_start_time) return a.plan_start_time;
  return a.start_time;
}

function effectiveEnd(a: AllocationForDashboard, mode: "plan" | "real"): string {
  if (mode === "plan" && a.plan_end_time) return a.plan_end_time;
  return a.end_time;
}

function floorHour(t: number) {
  const d = new Date(t);
  d.setMinutes(0, 0, 0);
  return d.getTime();
}

function ceilHour(t: number) {
  const d = new Date(t);
  if (d.getMinutes() === 0 && d.getSeconds() === 0 && d.getMilliseconds() === 0) return t;
  d.setMinutes(0, 0, 0);
  d.setHours(d.getHours() + 1);
  return d.getTime();
}

function localDateKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function layoutRows(items: AllocationForDashboard[], mode: "plan" | "real" = "real"): AllocationForDashboard[][] {
  const rows: { end: number; items: AllocationForDashboard[] }[] = [];
  const sorted = [...items].sort(
    (a, b) => new Date(effectiveStart(a, mode)).getTime() - new Date(effectiveStart(b, mode)).getTime()
  );
  for (const item of sorted) {
    const s = new Date(effectiveStart(item, mode)).getTime();
    let placed = false;
    for (const row of rows) {
      if (s >= row.end) {
        row.items.push(item);
        row.end = new Date(effectiveEnd(item, mode)).getTime();
        placed = true;
        break;
      }
    }
    if (!placed) {
      rows.push({ end: new Date(effectiveEnd(item, mode)).getTime(), items: [item] });
    }
  }
  return rows.map((r) => r.items);
}

// Pre-compute numeric timestamps for each allocation (avoids repeated new Date() in render)
interface AllocMeta {
  alloc: AllocationForDashboard;
  startMs: number;
  endMs: number;
}

const AllocationBlock = memo(function AllocationBlock({
  a,
  topPx,
  heightPx,
  leftPx,
  widthPx,
  mod,
  isConflict,
  onItemClick,
  viewMode = "real",
  nowMs,
}: {
  a: AllocationForDashboard;
  topPx: number;
  heightPx: number;
  leftPx: number;
  widthPx: number;
  mod: ModificationInfo | undefined;
  isConflict: boolean;
  onItemClick?: (a: AllocationForDashboard) => void;
  viewMode?: "plan" | "real";
  nowMs: number;
}) {
  const isPlan = viewMode === "plan";
  const sMs = new Date(effectiveStart(a, viewMode)).getTime();
  const baseEndMs = new Date(effectiveEnd(a, viewMode)).getTime();
  const delayedToMs = !isPlan && a.delayed_to ? new Date(a.delayed_to).getTime() : NaN;
  const eMs = Number.isFinite(delayedToMs) ? Math.max(baseEndMs, delayedToMs) : baseEndMs;
  const isFutureReal = !isPlan && nowMs < sMs;
  const isInWork = !isPlan && nowMs >= sMs && nowMs < eMs;
  const visibleDelayed = !isPlan && !isFutureReal && a.is_delayed;

  let cls = "item-normal";
  if (!isPlan) {
    if (mod) cls = "item-modified";
    else if (isInWork && visibleDelayed) cls = "item-delayed";
    else if (isInWork) cls = "item-working";
    else if (isConflict) cls = "item-conflict";
    else if (visibleDelayed) cls = "item-delayed";
    if (a.is_cancelled) cls = "item-cancelled";
  }

  const dispStart = isPlan ? (a.plan_start_time ?? a.start_time) : a.start_time;
  const dispEnd = isPlan ? (a.plan_end_time ?? a.end_time) : a.end_time;
  const slotTime = `${hhmm(dispStart)}–${hhmm(dispEnd)}`;
  const airport = shortText(a.ru_airport ?? a.airport, 18);

  const changeLabel = !isPlan && mod
    ? `${resourceLabel(mod.oldResourceType, mod.oldResourceName)} → ${resourceLabel(a.resource_type, a.resource_name)}`
    : null;

  let title: string;
  if (isPlan) {
    title = [
      `${a.flight_number} · ${a.airline}`,
      `Слот: ${slotTime}`,
      `План ${hhmm(a.plan_time)}`,
      airport !== "—" ? `Направление: ${airport}` : null,
      a.aircraft_type ? `ВС: ${a.aircraft_type}` : null,
      a.code_shares ? `Codeshares: ${a.code_shares}` : null,
    ].filter(Boolean).join("\n");
  } else {
    const planOrEat = visibleDelayed ? `EAT ${hhmm(a.estimated_time)}` : `План ${hhmm(a.plan_time)}`;
    const status = isInWork
      ? "В РАБОТЕ"
      : a.is_cancelled
        ? "ОТМЕНЁН"
        : shortText(a.status_tablo ?? a.status_raw, 16);
    title = [
      `${a.flight_number} · ${a.airline}`,
      `Слот: ${slotTime}`,
      planOrEat,
      a.fact_time ? `Факт: ${hhmm(a.fact_time)}` : null,
      a.delayed_to ? `Перенос: ${hhmm(a.delayed_to)}` : null,
      airport !== "—" ? `Направление: ${airport}` : null,
      status !== "—" ? `Статус: ${status}` : null,
      changeLabel ? `Изменение: ${changeLabel}` : null,
      a.code_shares ? `Codeshares: ${a.code_shares}` : null,
    ].filter(Boolean).join("\n");
  }

  return (
    <button
      type="button"
      title={title}
      onClick={() => onItemClick?.(a)}
      className={`absolute rounded px-1.5 py-0.5 text-left text-[10px] leading-[1.2] overflow-hidden hover:brightness-110 transition-[filter] ${
        isInWork ? "animate-pulse" : ""
      }`}
      style={{
        left: leftPx,
        width: widthPx,
        top: topPx,
        height: heightPx,
        backgroundColor: BAR_COLORS[cls],
        border: !isPlan && mod ? "2px solid #d4c400" : "1px solid rgba(0,0,0,0.25)",
        color: !isPlan && mod ? "#422006" : "#0b1220",
      }}
    >
      {!isPlan && mod && (
        <div className="truncate font-bold text-[9px]" style={{ color: "#92400e" }}>
          {changeLabel}
        </div>
      )}
      <div className="flex items-center justify-between gap-1">
        <span className="truncate font-bold text-[11px]">{a.flight_number}</span>
        <span className="truncate text-[9px] opacity-80">{slotTime}</span>
      </div>
      {isPlan ? (
        <>
          <div className="truncate">{shortText(a.airline, 20)} · План {hhmm(a.plan_time)}</div>
          <div className="truncate">{airport}</div>
        </>
      ) : (
        <>
          <div className="truncate">
            {shortText(a.airline, 20)} · {visibleDelayed ? `EAT ${hhmm(a.estimated_time)}` : `План ${hhmm(a.plan_time)}`}
          </div>
          {!mod && <div className="truncate">{airport}</div>}
          <div className="flex items-center justify-between gap-1">
            <span className="truncate opacity-90">
              {isInWork ? "В РАБОТЕ" : (a.is_cancelled ? "ОТМЕНЁН" : shortText(a.status_tablo ?? a.status_raw, 16))}
            </span>
            {isInWork && !mod && <span className="text-[9px] font-semibold text-emerald-900">В РАБОТЕ</span>}
            {visibleDelayed && !mod && <span className="text-[9px] font-semibold text-red-900">ЗАДЕРЖКА</span>}
            {a.is_cancelled && <span className="text-[9px] font-semibold text-red-900">ОТМЕНА</span>}
          </div>
        </>
      )}
    </button>
  );
});

export default function ResourceTimeline({
  resources,
  allocations,
  selectedDate,
  onVisibleDayChange,
  onItemClick,
  conflictIds = new Set(),
  modifications = new Map(),
  viewMode = "real",
  showCheckinLoadChart = false,
}: ResourceTimelineProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);
  const draggedEnough = useRef(false);
  const suppressClickUntil = useRef(0);
  const dragStartX = useRef(0);
  const scrollStartX = useRef(0);
  const [pxPerHour, setPxPerHour] = useState(DEFAULT_PX_PER_HOUR);
  const [focusedResourceId, setFocusedResourceId] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  // Viewport tracking for horizontal culling
  const [viewportLeft, setViewportLeft] = useState(0);
  const [viewportRight, setViewportRight] = useState(2000);
  /** Для полосы графика загруженности под диаграммой (вне вертикального скролла). */
  const [timelineScrollLeft, setTimelineScrollLeft] = useState(0);
  /** Показ графика загруженности (вкладка стоек). */
  const [checkinLoadChartOpen, setCheckinLoadChartOpen] = useState(true);
  const rafRef = useRef(0);
  const lastVisibleDayKeyRef = useRef<string>("");

  const sortedResources = useMemo(
    () =>
      [...resources].sort((a, b) => {
        const ta = RESOURCE_TYPE_ORDER[a.resource_type] ?? 99;
        const tb = RESOURCE_TYPE_ORDER[b.resource_type] ?? 99;
        if (ta !== tb) return ta - tb;
        const an = numericName(a.name);
        const bn = numericName(b.name);
        if (an != null && bn != null) return an - bn;
        if (an != null) return -1;
        if (bn != null) return 1;
        return a.name.localeCompare(b.name, "ru", { numeric: true, sensitivity: "base" });
      }),
    [resources]
  );
  const isGateView = useMemo(
    () => sortedResources.length > 0 && sortedResources.every((r) => r.resource_type === "gate"),
    [sortedResources]
  );
  const isFocusedView = focusedResourceId != null;
  // Для выходов делаем такой же визуальный "вес" карточек, как на стойках,
  // чтобы при одинаковом масштабе блоки не выглядели вертикальными иголками.
  // В подробном режиме для выходов держим умеренную ширину:
  // достаточно читаемо и без прежнего сильного наложения.
  const minBlockWidth = isFocusedView
    ? (isGateView ? 44 : 18)
    : (isGateView ? 95 : 18);

  const deduped = useMemo(() => {
    const seen = new Set<string>();
    const out: AllocationForDashboard[] = [];
    for (const a of allocations) {
      const key = `${a.flight_id}:${a.resource_id}:${effectiveStart(a, viewMode)}:${effectiveEnd(a, viewMode)}:${a.allocation_type}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(a);
    }
    return out;
  }, [allocations, viewMode]);

  const range = useMemo(() => {
    const starts = deduped
      .map((a) => new Date(effectiveStart(a, viewMode)).getTime())
      .filter((x) => !Number.isNaN(x));
    const ends = deduped
      .map((a) => new Date(effectiveEnd(a, viewMode)).getTime())
      .filter((x) => !Number.isNaN(x));

    // Выбранный день из календаря всегда должен быть в шкале,
    // даже если на него нет рейсов (иначе экран "прыгает" на соседнюю дату с данными).
    const dayStart = new Date(selectedDate);
    dayStart.setHours(0, 0, 0, 0);
    const dayEnd = new Date(dayStart);
    dayEnd.setDate(dayEnd.getDate() + 1);

    const minCandidates = starts.length ? starts : [];
    const maxCandidates = ends.length ? ends : [];
    minCandidates.push(dayStart.getTime());
    maxCandidates.push(dayEnd.getTime());

    const min = floorHour(Math.min(...minCandidates));
    const max = ceilHour(Math.max(...maxCandidates));
    return { min, max, span: Math.max(1, max - min) };
  }, [deduped, viewMode, selectedDate]);

  const checkinLoad = useMemo(() => {
    if (!showCheckinLoadChart || !range) {
      return { segments: [] as { tStart: number; tEnd: number; count: number }[], yMax: 8 };
    }
    const { segments, maxCount } = computeCheckinLoadSegments(
      deduped,
      viewMode,
      range.min,
      range.max
    );
    const cap = Math.max(sortedResources.length, maxCount, 1);
    const yMax = Math.max(8, Math.ceil(cap / 2) * 2);
    return { segments, yMax };
  }, [showCheckinLoadChart, range, deduped, viewMode, sortedResources.length]);

  const loadChartYTicks = useMemo(() => {
    const { yMax } = checkinLoad;
    const step = yMax <= 16 ? 2 : 4;
    const ticks: number[] = [];
    for (let v = 0; v <= yMax; v += step) ticks.push(v);
    return ticks;
  }, [checkinLoad]);

  const allocMetas = useMemo<Map<number, AllocMeta[]>>(() => {
    const map = new Map<number, AllocMeta[]>();
    for (const a of deduped) {
      const arr = map.get(a.resource_id) ?? [];
      arr.push({
        alloc: a,
        startMs: new Date(effectiveStart(a, viewMode)).getTime(),
        endMs: new Date(effectiveEnd(a, viewMode)).getTime(),
      });
      map.set(a.resource_id, arr);
    }
    map.forEach((arr) => {
      arr.sort((x, y) => x.startMs - y.startMs);
    });
    return map;
  }, [deduped, viewMode]);

  const totalHours = range ? Math.ceil(range.span / 3_600_000) : 24;
  const canvasWidth = Math.max(totalHours * pxPerHour, 800);

  const emitVisibleDay = useCallback((el: HTMLDivElement) => {
    if (!range || !onVisibleDayChange) return;
    const visibleTimelineLeft = Math.max(0, el.scrollLeft - LABEL_W);
    const visibleTimelineWidth = Math.max(1, el.clientWidth - LABEL_W);
    const x = Math.max(0, Math.min(canvasWidth, visibleTimelineLeft + visibleTimelineWidth * 0.5));
    const fraction = canvasWidth > 0 ? x / canvasWidth : 0;
    const t = range.min + fraction * range.span;
    const d = new Date(t);
    const day = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 12, 0, 0, 0);
    const key = localDateKey(day);
    if (key !== lastVisibleDayKeyRef.current) {
      lastVisibleDayKeyRef.current = key;
      onVisibleDayChange(day);
    }
  }, [range, canvasWidth, onVisibleDayChange]);

  // Update viewport on scroll
  const updateViewport = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setTimelineScrollLeft(el.scrollLeft);
    const l = el.scrollLeft - LABEL_W - VIEWPORT_BUFFER;
    const r = el.scrollLeft + el.clientWidth + VIEWPORT_BUFFER;
    setViewportLeft(l);
    setViewportRight(r);
    emitVisibleDay(el);
  }, [emitVisibleDay]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(updateViewport);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    updateViewport();
    return () => {
      el.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(rafRef.current);
    };
  }, [updateViewport, range, focusedResourceId]);

  // Also update viewport after zoom changes canvas width
  useEffect(() => {
    updateViewport();
  }, [canvasWidth, updateViewport]);

  // Filter visible allocations for a resource
  const getVisibleItems = useCallback(
    (resourceId: number): AllocMeta[] => {
      if (!range) return [];
      const items = allocMetas.get(resourceId) ?? [];
      return items.filter((m) => {
        const leftPx = ((m.startMs - range.min) / range.span) * canvasWidth;
        const widthPx = Math.max(minBlockWidth, ((m.endMs - m.startMs) / range.span) * canvasWidth);
        const rightPx = leftPx + widthPx;
        return rightPx >= viewportLeft && leftPx <= viewportRight;
      });
    },
    [range, canvasWidth, viewportLeft, viewportRight, allocMetas, minBlockWidth]
  );

  const hourTicks = useMemo(() => {
    if (!range) return [];
    const HOUR = 3_600_000;
    const out: { leftPx: number; label: string; isDay: boolean }[] = [];
    for (let t = range.min; t <= range.max; t += HOUR) {
      const leftPx = ((t - range.min) / range.span) * canvasWidth;
      // Only include ticks visible in viewport (with some buffer)
      if (leftPx < viewportLeft - 100 || leftPx > viewportRight + 100) continue;
      const d = new Date(t);
      const h = d.getHours();
      const isDay = h === 0;
      out.push({
        leftPx,
        label: isDay
          ? d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" })
          : `${String(h).padStart(2, "0")}:00`,
        isDay,
      });
    }
    return out;
  }, [range, canvasWidth, viewportLeft, viewportRight]);

  const pendingScrollDateRef = useRef<string | null>(null);
  const pendingClearTimerRef = useRef<number | null>(null);
  const lastAppliedDateKeyRef = useRef<string>("");
  /** Сохранённый горизонтальный скролл при переходе overview ↔ одна стойка (тот же range/canvas). */
  const pendingHorizontalScrollRef = useRef<number | null>(null);

  const scrollToDate = useCallback(
    (date: Date) => {
      const el = scrollRef.current;
      if (!el || !range) return;
      const dayStart = new Date(date);
      dayStart.setHours(0, 0, 0, 0);
      const fraction = (dayStart.getTime() - range.min) / range.span;
      el.scrollLeft = Math.max(0, fraction * canvasWidth);
    },
    [range, canvasWidth]
  );

  // Отмечаем скролл только при реальной смене календарной даты.
  useEffect(() => {
    const k = localDateKey(selectedDate);
    if (k !== lastAppliedDateKeyRef.current) {
      pendingScrollDateRef.current = k;
      if (pendingClearTimerRef.current != null) {
        window.clearTimeout(pendingClearTimerRef.current);
        pendingClearTimerRef.current = null;
      }
    }
  }, [selectedDate]);

  // Выполняем скролл только когда уже готов range для текущей даты.
  // Это устраняет прыжки на 2-3 дня и не ломает ручной скролл вбок.
  useEffect(() => {
    if (!range) return;
    const dateKey = localDateKey(selectedDate);
    if (pendingScrollDateRef.current !== dateKey) return;
    scrollToDate(selectedDate);
    lastAppliedDateKeyRef.current = dateKey;
    // Даём короткое окно на догрузку/пересчёт range после смены даты:
    // если range поменяется ещё раз, скролл повторится и точно попадёт в нужный день.
    if (pendingClearTimerRef.current != null) window.clearTimeout(pendingClearTimerRef.current);
    pendingClearTimerRef.current = window.setTimeout(() => {
      pendingScrollDateRef.current = null;
      pendingClearTimerRef.current = null;
    }, 700);
  }, [range, selectedDate, scrollToDate]);

  useEffect(() => {
    return () => {
      if (pendingClearTimerRef.current != null) {
        window.clearTimeout(pendingClearTimerRef.current);
      }
    };
  }, []);

  const captureHorizontalScroll = useCallback(() => {
    const el = scrollRef.current;
    pendingHorizontalScrollRef.current = el != null ? el.scrollLeft : null;
  }, []);

  // После смены режима (общий вид / одна стойка) новый scroll-контейнер с scrollLeft=0 — восстанавливаем позицию просмотра.
  useLayoutEffect(() => {
    const v = pendingHorizontalScrollRef.current;
    if (v == null) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollLeft = v;
    pendingHorizontalScrollRef.current = null;
    updateViewport();
  }, [focusedResourceId, canvasWidth, range.min, range.span, updateViewport]);

  // Drag-to-pan
  const hasRange = !!range;
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return;
      if ((e.target as HTMLElement).closest("[data-label-col]")) return;
      isDragging.current = true;
      draggedEnough.current = false;
      dragStartX.current = e.clientX;
      scrollStartX.current = el.scrollLeft;
      el.style.cursor = "grabbing";
      el.style.userSelect = "none";
      e.preventDefault();
    };
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      e.preventDefault();
      const dx = e.clientX - dragStartX.current;
      if (Math.abs(dx) > 4) draggedEnough.current = true;
      el.scrollLeft = scrollStartX.current - dx;
    };
    const onMouseUp = () => {
      if (!isDragging.current) return;
      isDragging.current = false;
      el.style.cursor = "grab";
      el.style.userSelect = "";
      if (draggedEnough.current) {
        // Блокируем клик по карточке сразу после drag, чтобы не открывалась модалка.
        suppressClickUntil.current = Date.now() + 120;
      }
    };
    const onClickCapture = (e: MouseEvent) => {
      if (Date.now() < suppressClickUntil.current) {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    el.style.cursor = "grab";
    el.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    el.addEventListener("click", onClickCapture, true);
    return () => {
      el.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      el.removeEventListener("click", onClickCapture, true);
    };
    // resources.length: при первом рендере часто [] и ref ещё нет — без этого после загрузки ресурсов эффект не перезапускается и drag не цепляется.
  }, [focusedResourceId, hasRange, resources.length]);

  // Wheel: labels → vertical scroll, diagram → zoom
  const zoomAnchorRef = useRef<{ fraction: number; offsetFromLeft: number } | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !range) return;
    const onWheel = (e: WheelEvent) => {
      const target = e.target as HTMLElement;
      // Обычное колесо: вертикальный скролл контейнера.
      // Горизонталь — только drag мышью.
      if (!e.ctrlKey) {
        e.preventDefault();
        el.scrollTop += e.deltaY;
        if (!target.closest("[data-label-col]") && Math.abs(e.deltaX) > 0) {
          el.scrollLeft += e.deltaX;
        }
        return;
      }

      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const cursorOffsetFromLeft = e.clientX - rect.left;
      const cursorXInContent = cursorOffsetFromLeft + el.scrollLeft - LABEL_W;
      const oldCanvas = canvasWidth;
      const fraction = oldCanvas > 0 ? cursorXInContent / oldCanvas : 0;
      const step = 1.35;
      const factor = e.deltaY > 0 ? 1 / step : step;
      const next = Math.min(MAX_PX_PER_HOUR, Math.max(MIN_PX_PER_HOUR, pxPerHour * factor));
      zoomAnchorRef.current = { fraction, offsetFromLeft: cursorOffsetFromLeft - LABEL_W };
      setPxPerHour(next);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [range, pxPerHour, canvasWidth, focusedResourceId]);

  useEffect(() => {
    const anchor = zoomAnchorRef.current;
    const el = scrollRef.current;
    if (!anchor || !el) return;
    el.scrollLeft = Math.max(0, anchor.fraction * canvasWidth - anchor.offsetFromLeft);
    zoomAnchorRef.current = null;
  }, [pxPerHour, canvasWidth]);

  // Focused resource data
  const focusedResource = focusedResourceId != null
    ? sortedResources.find((r) => r.id === focusedResourceId) ?? null
    : null;
  const focusedItems = focusedResourceId != null
    ? (allocMetas.get(focusedResourceId) ?? []).map((m) => m.alloc)
    : [];
  const focusedRows = useMemo(() => layoutRows(focusedItems, viewMode), [focusedItems, viewMode]);

  // Render helpers
  function renderVisibleBlocks(
    metas: AllocMeta[],
    topPx: number,
    heightPx: number,
    rng: NonNullable<typeof range>
  ) {
    return metas.map((m) => {
      const leftPx = ((m.startMs - rng.min) / rng.span) * canvasWidth;
      const widthPx = Math.max(minBlockWidth, ((m.endMs - m.startMs) / rng.span) * canvasWidth);
      return (
        <AllocationBlock
          key={m.alloc.id}
          a={m.alloc}
          topPx={topPx}
          heightPx={heightPx}
          leftPx={leftPx}
          widthPx={widthPx}
          mod={getAllocationModification(m.alloc, modifications)}
          isConflict={conflictIds.has(m.alloc.id)}
          onItemClick={onItemClick}
          viewMode={viewMode}
          nowMs={nowMs}
        />
      );
    });
  }

  function renderGridLines() {
    return hourTicks.map((t, i) => (
      <div
        key={`g${i}`}
        className="absolute top-0 h-full border-l pointer-events-none"
        style={{
          left: t.leftPx,
          borderColor: t.isDay ? "rgba(96,165,250,0.35)" : "rgba(45,58,77,0.5)",
        }}
      />
    ));
  }

  function renderNowLine() {
    if (!range) return null;
    const x = ((nowMs - range.min) / range.span) * canvasWidth;
    if (x < 0 || x > canvasWidth) return null;
    return (
      <div
        className="absolute top-0 h-full pointer-events-none z-20"
        style={{ left: x }}
      >
        <div className="h-full border-l-2 border-red-500" />
      </div>
    );
  }

  function renderTimeHeader() {
    return (
      <div
        className="sticky top-0 z-30 flex border-b border-dispatch-border"
        style={{ height: 28, width: LABEL_W + canvasWidth }}
      >
        <div
          className="sticky left-0 z-40 border-r border-dispatch-border bg-[#111e31]"
          style={{ width: LABEL_W, minWidth: LABEL_W }}
          data-label-col=""
        />
        <div className="relative bg-[#111e31]/95" style={{ width: canvasWidth }}>
          {hourTicks.map((t, i) => (
            <span
              key={i}
              className={`absolute top-1 -translate-x-1/2 whitespace-nowrap select-none ${
                t.isDay ? "text-[11px] font-bold text-blue-300" : "text-[10px] text-dispatch-muted"
              }`}
              style={{ left: t.leftPx }}
            >
              {t.label}
            </span>
          ))}
        </div>
      </div>
    );
  }

  if (resources.length === 0) {
    return (
      <div className="flex h-full min-h-[200px] items-center justify-center rounded border border-dispatch-border bg-dispatch-surface text-dispatch-muted">
        Нет ресурсов для отображения.
      </div>
    );
  }
  if (!range) {
    return (
      <div className="flex h-full min-h-[200px] items-center justify-center rounded border border-dispatch-border bg-dispatch-surface text-dispatch-muted">
        Нет аллокаций для выбранного набора ресурсов.
      </div>
    );
  }

  // ======== EXPANDED (focused) view ========
  if (focusedResource) {
    return (
      <div className="h-full w-full timeline-wrap flex flex-col">
        <div className="h-full flex flex-col rounded border border-dispatch-border bg-[#0d1728] overflow-hidden">
          <div className="flex items-center gap-2 border-b border-dispatch-border bg-[#111e31] px-3 py-1.5 shrink-0">
            <button
              type="button"
              onClick={() => {
                captureHorizontalScroll();
                setFocusedResourceId(null);
              }}
              className="rounded bg-dispatch-border px-2.5 py-1 text-xs text-gray-200 hover:bg-dispatch-muted/40 transition-colors"
            >
              ← Назад
            </button>
            <span className="text-sm font-semibold text-white">
              {resourceLabel(focusedResource.resource_type, focusedResource.name)}
            </span>
            <span className="text-xs text-dispatch-muted">
              ({focusedItems.length} рейсов, {focusedRows.length} рядов)
            </span>
          </div>
          <div
            ref={scrollRef}
            className="dashboard-scroll overflow-x-auto overflow-y-auto flex-1"
          >
            <div style={{ width: LABEL_W + canvasWidth, minWidth: "100%" }}>
              {renderTimeHeader()}
              {focusedRows.map((rowItems, rowIdx) => {
                const rowMetas = rowItems
                  .map((a) => {
                    const s = new Date(effectiveStart(a, viewMode)).getTime();
                    const e = new Date(effectiveEnd(a, viewMode)).getTime();
                    const leftPx = ((s - range.min) / range.span) * canvasWidth;
                    const widthPx = Math.max(minBlockWidth, ((e - s) / range.span) * canvasWidth);
                    if (leftPx + widthPx < viewportLeft || leftPx > viewportRight) return null;
                    return { alloc: a, startMs: s, endMs: e } as AllocMeta;
                  })
                  .filter(Boolean) as AllocMeta[];

                return (
                  <div
                    key={rowIdx}
                    className="flex border-b border-dispatch-border/70"
                    style={{ height: EXPANDED_ROW_H }}
                  >
                    <div
                      data-label-col=""
                      className="sticky left-0 z-10 flex items-center border-r border-dispatch-border bg-[#111e31] px-2 text-xs text-dispatch-muted select-none"
                      style={{ width: LABEL_W, minWidth: LABEL_W }}
                    >
                      {rowIdx === 0 ? resourceLabel(focusedResource.resource_type, focusedResource.name) : ""}
                    </div>
                    <div className="relative" style={{ width: canvasWidth }}>
                      {renderGridLines()}
                      {renderNowLine()}
                      {renderVisibleBlocks(rowMetas, 3, EXPANDED_ROW_H - 6, range)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ======== NORMAL (overview) view ========
  const loadChartCanvasOffset = Math.max(0, timelineScrollLeft - LABEL_W);

  return (
    <div className="h-full w-full timeline-wrap">
      <div className="flex h-full min-h-0 flex-col rounded border border-dispatch-border bg-[#0d1728] overflow-hidden">
        <div
          ref={scrollRef}
          className="dashboard-scroll min-h-0 flex-1 overflow-x-auto overflow-y-auto"
        >
          <div style={{ width: LABEL_W + canvasWidth, minWidth: "100%" }}>
            {renderTimeHeader()}
            {sortedResources.map((r) => {
              const visibleMetas = getVisibleItems(r.id);
              return (
                <div
                  key={r.id}
                  className="flex border-b border-dispatch-border/70"
                  style={{ height: ROW_H }}
                >
                  <div
                    data-label-col=""
                    className="sticky left-0 z-10 flex items-center border-r border-dispatch-border bg-[#111e31] px-2 text-xs text-gray-200 select-none cursor-pointer hover:bg-[#1a2d44] transition-colors"
                    style={{ width: LABEL_W, minWidth: LABEL_W }}
                    onClick={() => {
                      captureHorizontalScroll();
                      setFocusedResourceId(r.id);
                    }}
                    title="Нажми для подробного просмотра"
                  >
                    {resourceLabel(r.resource_type, r.name)}
                  </div>
                  <div className="relative" style={{ width: canvasWidth }}>
                    {renderGridLines()}
                    {renderNowLine()}
                    {renderVisibleBlocks(visibleMetas, 3, ROW_H - 6, range)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        {showCheckinLoadChart && (
          <div className="flex shrink-0 flex-col border-t border-dispatch-border bg-[#0d1728]">
            <div
              className="flex shrink-0 items-center justify-between gap-2 border-b border-dispatch-border/80 bg-[#111e31] px-3"
              style={{ height: LOAD_CHART_TOOLBAR_H }}
            >
              <span className="text-xs font-medium text-gray-300">
                График загруженности стоек
              </span>
              <button
                type="button"
                onClick={() => setCheckinLoadChartOpen((o) => !o)}
                className="shrink-0 rounded-md border border-dispatch-border/80 bg-[#0d1728] px-2.5 py-1 text-xs font-medium text-blue-300 transition-colors hover:bg-[#1a2d44] hover:text-blue-200"
                aria-expanded={checkinLoadChartOpen}
                title={
                  checkinLoadChartOpen
                    ? "Скрыть график (освободить место под диаграммой)"
                    : "Показать график загруженности по времени"
                }
              >
                {checkinLoadChartOpen ? "Скрыть ▲" : "Показать ▼"}
              </button>
            </div>
            {checkinLoadChartOpen && (
              <div
                className="flex shrink-0"
                style={{ height: LOAD_CHART_ROW_H }}
                title="Синхронизирован с горизонтальным скроллом диаграммы"
              >
                <div
                  className="flex shrink-0 flex-col border-r border-dispatch-border bg-[#111e31] select-none"
                  style={{ width: LABEL_W, minWidth: LABEL_W }}
                >
                  <div
                    className="flex items-center px-2 text-[11px] leading-snug text-dispatch-muted shrink-0"
                    style={{ height: LOAD_CHART_TITLE_H }}
                  >
                    Количество (стойки регистрации)
                  </div>
                  <div
                    className="relative text-[11px] text-dispatch-muted"
                    style={{ height: LOAD_CHART_H }}
                  >
                    {(() => {
                      const plotTop = CHECKIN_LOAD_CHART_PAD.top;
                      const plotBottom = LOAD_CHART_H - CHECKIN_LOAD_CHART_PAD.bottom;
                      const plotH = Math.max(1, plotBottom - plotTop);
                      const yMax = checkinLoad.yMax;
                      const valToY = (v: number) =>
                        plotBottom - (yMax > 0 ? (Math.min(v, yMax) / yMax) * plotH : 0);
                      return loadChartYTicks.map((v) => (
                        <span
                          key={v}
                          className="absolute right-1.5 -translate-y-1/2 tabular-nums"
                          style={{ top: valToY(v) }}
                        >
                          {v}
                        </span>
                      ));
                    })()}
                  </div>
                </div>
                <div className="min-w-0 flex-1 overflow-hidden bg-[#0d1728]">
                  <div
                    className="flex flex-col will-change-transform"
                    style={{
                      width: canvasWidth,
                      transform: `translateX(-${loadChartCanvasOffset}px)`,
                    }}
                  >
                    <div className="shrink-0 bg-[#0d1728]" style={{ height: LOAD_CHART_TITLE_H }} aria-hidden />
                    <div className="relative shrink-0" style={{ width: canvasWidth, height: LOAD_CHART_H }}>
                      {renderGridLines()}
                      {renderNowLine()}
                      <CheckinLoadChart
                        canvasWidth={canvasWidth}
                        height={LOAD_CHART_H}
                        rangeMin={range.min}
                        rangeSpan={range.span}
                        segments={checkinLoad.segments}
                        yMax={checkinLoad.yMax}
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
