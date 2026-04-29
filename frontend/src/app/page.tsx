"use client";

import { useState, useEffect, useLayoutEffect, useCallback, useMemo, useRef } from "react";
import Header from "@/components/Header";
import ConflictSidebar, { type BreakdownConflictEvent, type BreakdownConflictMove } from "@/components/ConflictSidebar";
import ResourceTimeline, { getAllocationModification } from "@/components/ResourceTimeline";
import ManualOverrideModal from "@/components/ManualOverrideModal";
import DistributionModal from "@/components/DistributionModal";
import BreakdownSimulationModal, { type BreakdownKind, type BreakdownSubmitPayload } from "@/components/BreakdownSimulationModal";
import { api } from "@/lib/api";
import {
  DASHBOARD_UI_KEY,
  dateKeyLocal,
  parseDateKey,
  type DashboardMode,
  type DashboardTab,
  type PersistedDashboardUI,
} from "@/lib/dashboardSession";
import { mockResources, mockAllocations, mockConflicts } from "@/lib/mockData";
import type { Resource, AllocationForDashboard, AllocationConflict } from "@/lib/types";

// Никогда не включаем моки "автоматом": только явный флаг.
// Это исключает ситуацию, когда на проде внезапно показывается demo-датасет.
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";
const PRELOAD_DAYS_BEFORE = 2;
const PRELOAD_DAYS_AFTER = 2;

function addDays(base: Date, days: number): Date {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d;
}

function buildDateWindowKeys(center: Date, daysBefore: number, daysAfter: number): string[] {
  const keys: string[] = [];
  for (let delta = -daysBefore; delta <= daysAfter; delta += 1) {
    keys.push(dateKeyLocal(addDays(center, delta)));
  }
  return keys;
}

function normalizeLocalDay(d: Date): Date {
  // Полдень локального дня: устойчиво к UTC-сдвигам и переходам DST.
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 12, 0, 0, 0);
}

function dayBoundsLocal(d: Date): { start: number; end: number } {
  const start = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0).getTime();
  const end = start + 24 * 60 * 60 * 1000;
  return { start, end };
}

function normalizeResourceType(value: string | null | undefined) {
  const v = (value ?? "").trim().toLowerCase().replaceAll("_", "-");
  if (v === "checkin" || v === "check-in" || v === "check in") return "check-in";
  if (v === "gate" || v === "gates") return "gate";
  return value ?? "";
}

function stableRand01(seed: string): number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i += 1) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 1000000) / 1000000;
}

function parseExtraData(raw: string | null | undefined): Record<string, unknown> {
  if (!raw) return {};
  try {
    const obj = JSON.parse(raw);
    return obj && typeof obj === "object" ? (obj as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function toNumber(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function synthesizeRealAllocations(items: AllocationForDashboard[], nowMs: number): AllocationForDashboard[] {
  return items.map((a) => {
    const planBase = a.plan_time ?? a.estimated_time ?? a.start_time;
    const planMs = new Date(planBase ?? 0).getTime();
    if (!Number.isFinite(planMs) || nowMs < planMs) {
      return { ...a, is_delayed: false };
    }

    const seed = `${a.flight_id}|${a.plan_time ?? a.start_time}|${a.flight_number}|${a.airline}`;
    const r1 = stableRand01(`${seed}|delay`);
    const delayed = r1 < 0.07; // 7% рейсов с задержкой > 15 минут
    const r2 = stableRand01(`${seed}|offset`);
    // Отклонения до +15 минут считаем "по плану".
    // Статус "ЗАДЕРЖКА" только при отклонении > 15 минут.
    const offsetMin = delayed ? (16 + Math.round(r2 * 19)) : (-10 + Math.round(r2 * 25));
    const factMs = planMs + offsetMin * 60_000;
    const factIso = new Date(factMs).toISOString();

    const extra = parseExtraData(a.extra_data);
    const avgPax =
      toNumber(extra["predicted_pax_total"]) ??
      toNumber(extra["Пассаж. всего"]) ??
      0;
    const seatsTotal =
      toNumber(extra["Кол-во кресел"]) ??
      toNumber(extra["Кол-во кресел для типа ВС (макс.)"]);
    if (avgPax > 0) {
      const r3 = stableRand01(`${seed}|pax`);
      const paxFactor = 0.92 + r3 * 0.16; // +/-8%
      const paxRaw = Math.max(1, Math.round(avgPax * paxFactor));
      const paxFact = seatsTotal != null ? Math.min(paxRaw, Math.round(seatsTotal)) : paxRaw;
      extra["Пассаж. всего"] = paxFact;
      if (toNumber(extra["predicted_pax_biz"]) != null && toNumber(extra["predicted_pax_econ"]) != null) {
        const biz = Math.max(0, Math.round((toNumber(extra["predicted_pax_biz"]) ?? 0) * paxFactor));
        const econ = Math.max(0, paxFact - Math.min(biz, paxFact));
        extra["Пассаж. Бизнес"] = biz;
        extra["Пассаж. Эконом"] = econ;
      }
    }
    extra["Дата/Время отпр. факт"] = factIso;
    extra["Время задержки (мин)"] = delayed ? Math.max(0, offsetMin) : 0;

    return {
      ...a,
      is_delayed: delayed,
      estimated_time: delayed ? factIso : (a.plan_time ?? a.estimated_time),
      fact_time: factIso,
      delayed_to: delayed ? factIso : null,
      status_tablo: delayed ? "ЗАДЕРЖАН" : "ПО РАСПИСАНИЮ",
      extra_data: JSON.stringify(extra),
    };
  });
}

export default function DashboardPage() {
  const [selectedDate, setSelectedDate] = useState(() => normalizeLocalDay(new Date()));
  const [visibleDay, setVisibleDay] = useState(() => normalizeLocalDay(new Date()));
  const [viewMode, setViewMode] = useState<DashboardMode>("real");
  const [activeTab, setActiveTab] = useState<DashboardTab>("check-in");
  const [resources, setResources] = useState<Resource[]>([]);
  const [allocations, setAllocations] = useState<AllocationForDashboard[]>([]);
  const [conflicts, setConflicts] = useState<AllocationConflict[]>([]);
  const [selectedAllocation, setSelectedAllocation] = useState<AllocationForDashboard | null>(null);
  const [useMock, setUseMock] = useState(USE_MOCK);
  const [dataReady, setDataReady] = useState(false);
  const [refreshBusy, setRefreshBusy] = useState(false);
  const [distributionOpen, setDistributionOpen] = useState(false);
  const [breakdownOpen, setBreakdownOpen] = useState(false);
  const [breakdownBusy, setBreakdownBusy] = useState(false);
  const [repairBusyId, setRepairBusyId] = useState<string | null>(null);
  const [breakdownEvents, setBreakdownEvents] = useState<BreakdownConflictEvent[]>([]);
  const [flightSearch, setFlightSearch] = useState("");
  const [hideUnusedResources, setHideUnusedResources] = useState(false);
  /** UI восстановлен из sessionStorage — до этого не грузим данные, чтобы не сбросить дату на «первую в БД». */
  const [persistReady, setPersistReady] = useState(false);
  const importDoneRef = useRef(false);
  /**
   * Один раз за «цикл с данными» подставляем дату, если в окне ±2 дня нет MANUAL-аллокаций,
   * но в БД они есть (иначе при сохранённом sessionStorage и дате «сегодня» таймлайн оставался пустым).
   */
  const emptyWindowFallbackOnceRef = useRef(false);
  const setSelectedDateSafe = useCallback((d: Date) => {
    setSelectedDate(normalizeLocalDay(d));
  }, []);

  useEffect(() => {
    setVisibleDay(selectedDate);
  }, [selectedDate]);

  // Синхронно до paint: вернуть дату / вкладку / режим после перехода с /norms и т.д.
  useLayoutEffect(() => {
    try {
      const raw = sessionStorage.getItem(DASHBOARD_UI_KEY);
      if (!raw) {
        setPersistReady(true);
        return;
      }
      const p = JSON.parse(raw) as PersistedDashboardUI;
      // Дату из storage намеренно НЕ восстанавливаем:
      // при каждом обновлении страницы показываем "сегодня".
      if (p.tab === "check-in" || p.tab === "gate") setActiveTab(p.tab);
      if (p.mode === "plan" || p.mode === "real") setViewMode(p.mode);
    } catch {
      /* ignore */
    }
    setPersistReady(true);
  }, []);

  // Сохранять UI при каждом изменении (после восстановления из storage)
  useEffect(() => {
    if (!persistReady) return;
    const payload: PersistedDashboardUI = {
      v: 1,
      dateKey: dateKeyLocal(selectedDate),
      tab: activeTab,
      mode: viewMode,
    };
    try {
      sessionStorage.setItem(DASHBOARD_UI_KEY, JSON.stringify(payload));
    } catch {
      /* quota */
    }
  }, [selectedDate, activeTab, viewMode, persistReady]);

  // One-time import on first mount
  useEffect(() => {
    if (useMock || importDoneRef.current) return;
    importDoneRef.current = true;
    const run = async () => {
      try {
        // Check if data already exists by fetching a small sample
        const probe = await api.getAllocations(undefined, { allocation_type: "manual" });
        if (probe.length > 0) {
          console.log("[Dashboard] DB already has data, skip import", probe.length);
          setDataReady(true);
          return;
        }
      } catch {
        // If even the probe fails, try importing
      }
      console.log("[Dashboard] Importing Excel...");
      try {
        const stats = await api.importExcel();
        console.log("[Dashboard] Excel import done:", stats);
      } catch (e) {
        console.warn("[Dashboard] Excel import failed:", e);
        try { await api.importXml({}); } catch { /* fallback */ }
      }
      setDataReady(true);
    };
    void run();
  }, [useMock]);

  const mapBreakdownEvent = useCallback((e: import("@/lib/types").BreakdownEvent): BreakdownConflictEvent => ({
    id: e.id,
    kindLabel: e.kind_label,
    brokenCounterName: e.broken_counter_name,
    brokenIsland: e.broken_island,
    targetIsland: e.target_island,
    createdAt: e.created_at,
    status: e.status,
    note: e.note ?? undefined,
    moves: e.moves.map((m) => ({
      flight_number: m.flight_number,
      from_counters: m.from_counters,
      to_counters: m.to_counters,
    })),
  }), []);

  const loadBreakdownHistory = useCallback(async () => {
    if (useMock) {
      setBreakdownEvents([]);
      return;
    }
    try {
      const rows = await api.getBreakdownHistory();
      setBreakdownEvents(rows.map(mapBreakdownEvent));
    } catch (e) {
      console.error("[Dashboard] Breakdown history failed:", e);
    }
  }, [useMock, mapBreakdownEvent]);

  // Load data when dataReady or selectedDate changes (после persistReady — с правильной датой из sessionStorage)
  useEffect(() => {
    if (!persistReady) return;
    if (useMock) {
      setResources(mockResources);
      setAllocations(mockAllocations);
      setConflicts(mockConflicts);
      return;
    }
    if (!dataReady) return;

    const centerKey = dateKeyLocal(selectedDate);
    const dateKeys = buildDateWindowKeys(selectedDate, PRELOAD_DAYS_BEFORE, PRELOAD_DAYS_AFTER);
    let cancelled = false;

    const fetchData = async () => {
      try {
        await api.reconcileBreakdowns();
        console.log("[Dashboard] Fetching window data for", centerKey, "keys:", dateKeys.join(", "));
        const [resList, allocByDay] = await Promise.all([
          api.getResources(),
          Promise.all(dateKeys.map((k) => api.getAllocations(k, { allocation_type: "manual" }))),
        ]);
        if (cancelled) return;
        const allocList = allocByDay.flat();
        const allocMap = new Map<number, AllocationForDashboard>();
        for (const a of allocList) allocMap.set(a.id, a);
        const mergedAllocations = Array.from(allocMap.values()).sort(
          (a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
        );
        console.log("[Dashboard] Got", resList.length, "resources,", mergedAllocations.length, "allocations (window)");

        setResources(resList);

        if (mergedAllocations.length > 0) {
          emptyWindowFallbackOnceRef.current = false;
          setAllocations(mergedAllocations);
          setConflicts([]);
        } else {
          const all = await api.getAllocations(undefined, { allocation_type: "manual" });
          if (cancelled) return;
          if (
            all.length > 0 &&
            !emptyWindowFallbackOnceRef.current &&
            dateKeyLocal(new Date(all[0].start_time)) !== centerKey
          ) {
            const first = new Date(all[0].start_time);
            if (!Number.isNaN(first.getTime())) {
              emptyWindowFallbackOnceRef.current = true;
              console.log("[Dashboard] No MANUAL in window", centerKey, "→ first data day", dateKeyLocal(first));
              setSelectedDateSafe(first);
              return;
            }
          }
          setAllocations([]);
          setConflicts([]);
        }
        await loadBreakdownHistory();
      } catch (e) {
        console.error("[Dashboard] Failed to load data:", e);
      }
    };

    void fetchData();
    return () => { cancelled = true; };
  }, [useMock, dataReady, selectedDate, persistReady, loadBreakdownHistory]);

  /** Повторная загрузка с API: та же дата, без смены вкладок/режима; не перескакиваем на «первую дату с данными». */
  const handleRefreshData = useCallback(async () => {
    if (useMock) {
      setResources(mockResources);
      setAllocations(mockAllocations);
      setConflicts(mockConflicts);
      setSelectedAllocation(null);
      return;
    }
    if (!dataReady) return;
    setRefreshBusy(true);
    setSelectedAllocation(null);
    const dateKeys = buildDateWindowKeys(selectedDate, PRELOAD_DAYS_BEFORE, PRELOAD_DAYS_AFTER);
    try {
      await api.reconcileBreakdowns();
      const [resList, allocByDay] = await Promise.all([
        api.getResources(),
        Promise.all(dateKeys.map((k) => api.getAllocations(k, { allocation_type: "manual" }))),
      ]);
      const allocMap = new Map<number, AllocationForDashboard>();
      for (const a of allocByDay.flat()) allocMap.set(a.id, a);
      const mergedAllocations = Array.from(allocMap.values()).sort(
        (a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
      );
      setResources(resList);
      setAllocations(mergedAllocations);
      setConflicts([]);
      await loadBreakdownHistory();
    } catch (e) {
      console.error("[Dashboard] Refresh failed:", e);
    } finally {
      setRefreshBusy(false);
    }
  }, [useMock, dataReady, selectedDate, loadBreakdownHistory]);

  const handleSaveOverride = useCallback(
    async (allocationId: number, newResourceId: number, _startTime: string, _endTime: string) => {
      const alloc = allocations.find((a) => a.id === allocationId);
      if (!alloc) return;
      const newRes = resources.find((r) => r.id === newResourceId);
      if (!newRes) return;
      if (alloc.resource_id === newResourceId) return;

      const before = { ...alloc };

      setAllocations((prev) =>
        prev.map((a) =>
          a.id === allocationId
            ? {
                ...a,
                resource_id: newResourceId,
                resource_name: newRes.name,
                resource_type: newRes.resource_type,
                original_resource_id: a.original_resource_id ?? a.resource_id,
                original_resource_name: a.original_resource_name ?? a.resource_name,
                original_resource_type: a.original_resource_type ?? a.resource_type,
              }
            : a
        )
      );

      if (!useMock) {
        try {
          const updated = await api.patchAllocation(allocationId, { resource_id: newResourceId });
          setAllocations((prev) => prev.map((a) => (a.id === allocationId ? updated : a)));
        } catch (e) {
          console.error("PATCH failed, reverting:", e);
          setAllocations((prev) => prev.map((a) => (a.id === allocationId ? before : a)));
          throw e;
        }
      }
    },
    [allocations, resources, useMock]
  );

  const handleBreakdownSubmit = useCallback(async (payload: BreakdownSubmitPayload) => {
    setBreakdownBusy(true);
    try {
      if (!useMock) {
        await api.startBreakdown({ kind: payload.kind, checkin_resource_id: payload.checkinResourceId });
        await handleRefreshData();
        await loadBreakdownHistory();
      }
      setBreakdownOpen(false);
    } finally {
      setBreakdownBusy(false);
    }
  }, [useMock, handleRefreshData, loadBreakdownHistory]);

  const handleRepairBreakdown = useCallback(async (eventId: string) => {
    setRepairBusyId(eventId);
    try {
      if (!useMock) {
        await api.repairBreakdown(eventId);
        await handleRefreshData();
        await loadBreakdownHistory();
      }
    } finally {
      setRepairBusyId(null);
    }
  }, [useMock, handleRefreshData, loadBreakdownHistory]);

  useEffect(() => {
    if (useMock || !dataReady || !persistReady) return;
    const t = window.setInterval(async () => {
      try {
        const r = await api.reconcileBreakdowns();
        if ((r.total_moved_allocations ?? 0) > 0) {
          await handleRefreshData();
        } else {
          await loadBreakdownHistory();
        }
      } catch {
        // ignore periodic errors
      }
    }, 20_000);
    return () => window.clearInterval(t);
  }, [useMock, dataReady, persistReady, handleRefreshData, loadBreakdownHistory]);

  const conflictIds = useMemo(() => new Set<number>(), []);

  const checkinResources = useMemo(
    () => resources.filter((r) => normalizeResourceType(r.resource_type) === "check-in"),
    [resources]
  );
  const gateResources = useMemo(
    () => resources.filter((r) => normalizeResourceType(r.resource_type) === "gate"),
    [resources]
  );

  const allocationsForView = useMemo(
    () => (viewMode === "real" ? synthesizeRealAllocations(allocations, Date.now()) : allocations),
    [allocations, viewMode]
  );
  const searchNeedle = flightSearch.trim().toLowerCase();
  const filteredAllocationsForView = useMemo(() => {
    if (!searchNeedle) return allocationsForView;
    return allocationsForView.filter((a) => {
      const hay = [
        a.flight_number,
        a.airline,
        a.airport,
        a.ru_airport,
        a.en_airport,
      ]
        .map((x) => String(x ?? "").toLowerCase())
        .join(" ");
      return hay.includes(searchNeedle);
    });
  }, [allocationsForView, searchNeedle]);

  const checkinAllocations = useMemo(
    () => filteredAllocationsForView.filter((a) => normalizeResourceType(a.resource_type) === "check-in"),
    [filteredAllocationsForView]
  );
  const gateAllocations = useMemo(
    () => filteredAllocationsForView.filter((a) => normalizeResourceType(a.resource_type) === "gate"),
    [filteredAllocationsForView]
  );

  const isAllocationActiveOnDay = useCallback((a: AllocationForDashboard, day: Date) => {
    const startRaw = viewMode === "plan" && a.plan_start_time ? a.plan_start_time : a.start_time;
    const endRaw = viewMode === "plan" && a.plan_end_time ? a.plan_end_time : a.end_time;
    const startMs = new Date(startRaw).getTime();
    const endMs = new Date(endRaw).getTime();
    if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return false;
    const { start, end } = dayBoundsLocal(day);
    // Любое пересечение интервала с текущим локальным днём.
    return startMs < end && endMs > start;
  }, [viewMode]);

  const usedCheckinResourceIds = useMemo(
    () => {
      const source = hideUnusedResources
        ? checkinAllocations.filter((a) => isAllocationActiveOnDay(a, visibleDay))
        : checkinAllocations;
      return new Set(source.map((a) => a.resource_id));
    },
    [hideUnusedResources, checkinAllocations, isAllocationActiveOnDay, visibleDay]
  );
  const usedGateResourceIds = useMemo(
    () => {
      const source = hideUnusedResources
        ? gateAllocations.filter((a) => isAllocationActiveOnDay(a, visibleDay))
        : gateAllocations;
      return new Set(source.map((a) => a.resource_id));
    },
    [hideUnusedResources, gateAllocations, isAllocationActiveOnDay, visibleDay]
  );

  const checkinResourcesShown = useMemo(
    () => (hideUnusedResources ? checkinResources.filter((r) => usedCheckinResourceIds.has(r.id)) : checkinResources),
    [hideUnusedResources, checkinResources, usedCheckinResourceIds]
  );
  const gateResourcesShown = useMemo(
    () => (hideUnusedResources ? gateResources.filter((r) => usedGateResourceIds.has(r.id)) : gateResources),
    [hideUnusedResources, gateResources, usedGateResourceIds]
  );
  return (
    <div className="flex h-screen flex-col">
      <Header
        selectedDate={selectedDate}
        onDateChange={setSelectedDateSafe}
        onRefreshData={handleRefreshData}
        refreshBusy={refreshBusy}
        onOpenBreakdownSimulation={() => setBreakdownOpen(true)}
        onOpenDistribution={() => setDistributionOpen(true)}
      />
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <ConflictSidebar
          conflicts={conflicts}
          breakdownEvents={breakdownEvents}
          onRepairBreakdown={handleRepairBreakdown}
          repairBusyId={repairBusyId}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
        />
        <main className="dashboard-scroll flex-1 overflow-hidden p-3 flex flex-col">
          {/* Resource type tabs */}
          <div className="mb-3 flex gap-1 rounded-lg border border-dispatch-border bg-[#111e31] p-1 shrink-0">
            {([
              { key: "check-in" as const, label: "Стойки регистрации", count: `${checkinResourcesShown.length}` },
              { key: "gate" as const, label: "Выходы на посадку", count: `${gateResourcesShown.length}` },
            ]).map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={`flex-1 rounded-md px-4 py-2.5 text-sm font-medium transition-colors ${
                  activeTab === tab.key
                    ? "bg-blue-600 text-white shadow-md"
                    : "text-gray-400 hover:bg-[#1a2d44] hover:text-white"
                }`}
              >
                {tab.label}
                <span className={`ml-2 text-xs ${activeTab === tab.key ? "text-blue-200" : "text-gray-500"}`}>
                  ({tab.count})
                </span>
              </button>
            ))}
          </div>

          <div className="mb-3 shrink-0 mx-auto flex w-full max-w-2xl gap-3">
            <input
              type="text"
              value={flightSearch}
              onChange={(e) => setFlightSearch(e.target.value)}
              placeholder="Поиск рейса: номер, авиакомпания, направление"
              className="flex-1 rounded border border-dispatch-border bg-dispatch-bg px-3 py-2 text-sm text-white placeholder:text-dispatch-muted focus:border-dispatch-accent focus:outline-none"
            />
            <button
              type="button"
              onClick={() => setFlightSearch("")}
              className="shrink-0 rounded border border-red-500/70 bg-red-500/10 px-3 py-2 text-sm text-red-300 hover:bg-red-500/20 hover:text-red-200 hover:border-red-400 transition-colors"
            >
              Очистить
            </button>
            <button
              type="button"
              onClick={() => setHideUnusedResources((v) => !v)}
              className="shrink-0 rounded border border-dispatch-border px-3 py-2 text-sm text-dispatch-muted hover:text-white hover:border-gray-500 transition-colors"
              title="Убирает стойки/выходы без рейсов в текущем дне, который сейчас в области просмотра"
            >
              {hideUnusedResources ? "Показать неиспользуемые" : "Скрыть неиспользуемое"}
            </button>
          </div>

          {/* Active diagram */}
          {activeTab === "check-in" && (
            <section className="flex-1 min-h-0 rounded border border-dispatch-border bg-dispatch-surface/30 p-2">
              <ResourceTimeline
                resources={checkinResourcesShown}
                allocations={checkinAllocations}
                selectedDate={selectedDate}
                onVisibleDayChange={setVisibleDay}
                onItemClick={setSelectedAllocation}
                conflictIds={conflictIds}
                viewMode={viewMode}
                showCheckinLoadChart
              />
            </section>
          )}
          {activeTab === "gate" && (
            <section className="flex-1 min-h-0 rounded border border-dispatch-border bg-dispatch-surface/30 p-2">
              <ResourceTimeline
                resources={gateResourcesShown}
                allocations={gateAllocations}
                selectedDate={selectedDate}
                onVisibleDayChange={setVisibleDay}
                onItemClick={setSelectedAllocation}
                conflictIds={conflictIds}
                viewMode={viewMode}
              />
            </section>
          )}
        </main>
      </div>
      <footer className="flex shrink-0 items-start justify-between gap-4 border-t border-dispatch-border bg-dispatch-surface px-4 py-2 text-xs text-dispatch-muted">
        <span className="pt-1">
          Неразмещённые / конфликты:{" "}
          <strong className={conflicts.length > 0 ? "text-amber-400" : "text-gray-400"}>{conflicts.length}</strong>
        </span>
        <span className="text-gray-500 pt-1">
          Окно «Распределение» — анализ периода; полный алгоритм пересчёта подключается к API отдельно.
        </span>
      </footer>
      <DistributionModal
        open={distributionOpen}
        onClose={() => setDistributionOpen(false)}
        referenceDate={selectedDate}
        allocations={allocations}
        useMock={useMock}
        onApplied={handleRefreshData}
      />
      <ManualOverrideModal
        allocation={selectedAllocation}
        resources={resources}
        onClose={() => setSelectedAllocation(null)}
        onSave={handleSaveOverride}
        readOnly={viewMode === "plan"}
        modification={selectedAllocation ? getAllocationModification(selectedAllocation) : undefined}
      />
      <BreakdownSimulationModal
        open={breakdownOpen}
        resources={resources}
        busy={breakdownBusy}
        onClose={() => !breakdownBusy && setBreakdownOpen(false)}
        onSubmit={handleBreakdownSubmit}
      />
    </div>
  );
}
