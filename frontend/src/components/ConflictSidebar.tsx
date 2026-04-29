"use client";

import type { AllocationConflict } from "@/lib/types";

export interface BreakdownConflictMove {
  flight_number: string;
  from_counters: string;
  to_counters: string;
}

export interface BreakdownConflictEvent {
  id: string;
  kindLabel: string;
  brokenCounterName: string;
  brokenIsland: 1 | 2;
  targetIsland: 1 | 2;
  createdAt: string;
  status: "active" | "repaired";
  note?: string;
  moves: BreakdownConflictMove[];
}

interface ConflictSidebarProps {
  conflicts: AllocationConflict[];
  breakdownEvents?: BreakdownConflictEvent[];
  onRepairBreakdown?: (eventId: string) => void;
  repairBusyId?: string | null;
  viewMode: "plan" | "real";
  onViewModeChange: (mode: "plan" | "real") => void;
  className?: string;
}

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

function resourceTypeLabel(t: string) {
  if (t === "check-in") return "Стойки регистрации";
  if (t === "gate") return "Выходы на посадку";
  return t;
}

export default function ConflictSidebar({
  conflicts,
  breakdownEvents = [],
  onRepairBreakdown,
  repairBusyId = null,
  viewMode,
  onViewModeChange,
  className = "",
}: ConflictSidebarProps) {
  return (
    <aside
      className={`flex w-72 flex-col border-r border-dispatch-border bg-dispatch-surface ${className}`}
    >
      <div className="border-b border-dispatch-border px-3 py-2">
        <div className="flex gap-1">
          {([
            { key: "plan" as const, label: "Плановая" },
            { key: "real" as const, label: "Реальная" },
          ]).map((m) => (
            <button
              key={m.key}
              type="button"
              onClick={() => onViewModeChange(m.key)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                viewMode === m.key
                  ? m.key === "plan"
                    ? "bg-emerald-600 text-white shadow-md"
                    : "bg-blue-600 text-white shadow-md"
                  : "border border-dispatch-border text-gray-400 hover:text-white hover:border-gray-500"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>
      <h2 className="border-b border-dispatch-border px-3 py-2 text-sm font-semibold text-white">
        Неразмещённые / конфликты
      </h2>
      <div className="flex-1 overflow-y-auto p-2">
        {breakdownEvents.length === 0 && conflicts.length === 0 ? (
          <p className="text-sm text-dispatch-muted">Нет конфликтов</p>
        ) : (
          <div className="space-y-2">
            {breakdownEvents.map((e) => (
              <div
                key={e.id}
                className={`rounded border p-3 text-sm ${
                  e.status === "active"
                    ? "border-rose-500/50 bg-rose-500/10"
                    : "border-emerald-500/40 bg-emerald-500/10"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium text-white">Поломка: {e.kindLabel}</div>
                  <span className={`text-xs font-semibold ${e.status === "active" ? "text-rose-300" : "text-emerald-300"}`}>
                    {e.status === "active" ? "АКТИВНА" : "УСТРАНЕНА"}
                  </span>
                </div>
                <div className="mt-1 text-dispatch-muted">
                  Стойка {e.brokenCounterName} · остров {e.brokenIsland} → остров {e.targetIsland}
                </div>
                <div className="mt-1 text-dispatch-muted">Время: {new Date(e.createdAt).toLocaleString("ru-RU")}</div>
                {e.note && <div className="mt-1 text-xs text-white/85">{e.note}</div>}
                {e.moves.length > 0 ? (
                  <div className="mt-2 space-y-1">
                    {e.moves.slice(0, 8).map((m, idx) => (
                      <div key={`${m.flight_number}-${idx}`} className="text-xs text-white/90">
                        {m.flight_number}: {m.from_counters} → {m.to_counters}
                      </div>
                    ))}
                    {e.moves.length > 8 && (
                      <div className="text-xs text-dispatch-muted">…и ещё {e.moves.length - 8}</div>
                    )}
                  </div>
                ) : (
                  <div className="mt-2 text-xs text-dispatch-muted">Перераспределений не выполнено</div>
                )}
                {e.status === "active" && onRepairBreakdown && (
                  <button
                    type="button"
                    onClick={() => onRepairBreakdown(e.id)}
                    disabled={repairBusyId === e.id}
                    className="mt-2 rounded border border-emerald-600/70 bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50 transition-colors"
                  >
                    {repairBusyId === e.id ? "Починка…" : "Починить"}
                  </button>
                )}
              </div>
            ))}
            {conflicts.map((c, i) => (
              <div
                key={`${c.flight_number}-${c.resource_type}-${i}`}
                className="rounded border border-dispatch-conflict/50 bg-dispatch-conflict/10 p-3 text-sm"
              >
                <div className="font-medium text-white">{c.flight_number}</div>
                <div className="mt-1 text-dispatch-muted">
                  {resourceTypeLabel(c.resource_type)} · {formatTime(c.start_time)}–{formatTime(c.end_time)}
                </div>
                <div className="mt-1 text-dispatch-conflict/90">{c.reason}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
