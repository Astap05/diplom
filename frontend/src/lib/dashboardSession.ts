/**
 * Сохранение UI дашборда между переходами по страницам Next.js (без полной перезагрузки вкладки).
 * sessionStorage — на вкладку; очищается при закрытии вкладки.
 */

export const DASHBOARD_UI_KEY = "rms_dashboard_ui_v1";

export type DashboardTab = "check-in" | "gate";
export type DashboardMode = "plan" | "real";

export type PersistedDashboardUI = {
  v: 1;
  /** YYYY-MM-DD в локальном календаре */
  dateKey: string;
  tab: DashboardTab;
  mode: DashboardMode;
};

/** Парсинг YYYY-MM-DD как локальная дата (без UTC-сдвига). */
export function parseDateKey(key: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(key.trim());
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]) - 1;
  const d = Number(m[3]);
  const dt = new Date(y, mo, d);
  if (dt.getFullYear() !== y || dt.getMonth() !== mo || dt.getDate() !== d) return null;
  return dt;
}

export function dateKeyLocal(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
