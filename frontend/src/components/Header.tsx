"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

interface HeaderProps {
  selectedDate: Date;
  onDateChange: (date: Date) => void;
  /** Обновить данные с сервера без перезагрузки вкладки браузера (дата и вкладки не сбрасываются) */
  onRefreshData?: () => void;
  refreshBusy?: boolean;
  onOpenBreakdownSimulation?: () => void;
  /** Окно «Распределение» (как на терминале аэропорта) */
  onOpenDistribution?: () => void;
}

/** Форматирование времени аэропорта (локальное) и даты для пикера */
function formatTime(d: Date) {
  return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function formatDateForInput(d: Date) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function parseDateInputLocal(value: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((value || "").trim());
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]) - 1;
  const d = Number(m[3]);
  const dt = new Date(y, mo, d);
  if (dt.getFullYear() !== y || dt.getMonth() !== mo || dt.getDate() !== d) return null;
  return dt;
}

/** Как в page.tsx: полдень локального дня для стабильной работы с таймлайном. */
function normalizeLocalDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 12, 0, 0, 0);
}

function isSameLocalDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export default function Header({
  selectedDate,
  onDateChange,
  onRefreshData,
  refreshBusy = false,
  onOpenBreakdownSimulation,
  onOpenDistribution,
}: HeaderProps) {
  const [mounted, setMounted] = useState(false);
  const [now, setNow] = useState<Date>(() => new Date(0));

  useEffect(() => {
    setMounted(true);
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <header className="flex items-center justify-between gap-4 border-b border-dispatch-border bg-dispatch-surface px-4 py-3">
      <div className="flex items-center gap-6">
        <img
          src="/MSQ_English_logo.svg.png"
          alt="Логотип аэропорта"
          className="h-10 w-auto object-contain"
        />
        <div className="flex items-center gap-2 text-dispatch-muted">
          <span className="text-sm">Время аэропорта:</span>
          <span className="font-mono text-white" suppressHydrationWarning>
            {mounted ? formatTime(now) : "--:--:--"}
          </span>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-dispatch-muted">Дата:</span>
          <div className="flex items-center gap-1.5">
            <div className="header-date-wrap relative">
              <input
                type="date"
                value={formatDateForInput(selectedDate)}
                onChange={(e) => {
                  const parsed = parseDateInputLocal(e.target.value);
                  if (parsed) onDateChange(parsed);
                }}
                className="header-date-input rounded border border-dispatch-border bg-dispatch-bg px-2 py-1.5 pr-8 text-white focus:border-dispatch-accent focus:outline-none"
              />
              <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-white/95">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M7 2v3M17 2v3M3 9h18M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </span>
            </div>
            <button
              type="button"
              onClick={() => onDateChange(normalizeLocalDay(new Date()))}
              disabled={mounted && isSameLocalDay(selectedDate, now)}
              title="Перейти на сегодняшнюю дату"
              className="shrink-0 rounded border border-sky-600/50 bg-sky-500/10 px-2 py-1 text-xs font-medium text-sky-200 hover:bg-sky-500/20 hover:border-sky-500 disabled:cursor-default disabled:opacity-40 disabled:hover:bg-sky-500/10 transition-colors"
            >
              Сегодня
            </button>
          </div>
        </label>
      </div>
      <div className="flex items-center gap-2">
        <span className="mx-2 hidden text-sm font-semibold tracking-wider text-white/90 md:inline">
          TRMS
        </span>
        {onRefreshData && (
          <button
            type="button"
            onClick={() => onRefreshData()}
            disabled={refreshBusy}
            title="Обновить данные с сервера. Дата, план/реальная и тип диаграммы не меняются."
            className="inline-flex items-center gap-1.5 rounded border border-dispatch-border px-3 py-1.5 text-sm text-dispatch-muted hover:text-white hover:border-gray-500 transition-colors disabled:cursor-wait disabled:opacity-50"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M20 11a8 8 0 1 0-2.34 5.66M20 11V5m0 6h-6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {refreshBusy ? "Обновление…" : "Обновить"}
          </button>
        )}
        {onOpenBreakdownSimulation && (
          <button
            type="button"
            onClick={onOpenBreakdownSimulation}
            title="Имитация поломки острова стоек и оперативное перераспределение рейсов"
            className="rounded border border-rose-700/60 bg-rose-950/40 px-3 py-1.5 text-sm text-rose-200 hover:bg-rose-900/50 hover:border-rose-600 transition-colors"
          >
            Имитировать поломку
          </button>
        )}
        {onOpenDistribution && (
          <button
            type="button"
            onClick={onOpenDistribution}
            title="Анализ периода и каркас автоматического распределения (как на терминале)"
            className="rounded border border-emerald-700/60 bg-emerald-950/40 px-3 py-1.5 text-sm text-emerald-200 hover:bg-emerald-900/50 hover:border-emerald-600 transition-colors"
          >
            Распределение
          </button>
        )}
        <Link
          href="/norms"
          className="inline-flex items-center gap-1.5 rounded border border-amber-600/70 bg-amber-500/10 px-3 py-1.5 text-sm text-amber-300 hover:bg-amber-500/20 hover:text-amber-200 hover:border-amber-500 transition-colors"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M5 4h12a2 2 0 0 1 2 2v14l-4-2-4 2-4-2-4 2V6a2 2 0 0 1 2-2Z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M8 8h8M8 11h8M8 14h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          Нормативы
        </Link>
      </div>
    </header>
  );
}
