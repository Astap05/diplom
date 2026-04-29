"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { CheckinNorm, GateNorm } from "@/lib/types";

type TabKey = "checkin" | "gate";
type NormRecord = CheckinNorm | GateNorm;

type FieldDef = {
  key: string;
  label: string;
  type: "text" | "number" | "date" | "checkbox" | "select";
  options?: { value: string; label: string }[];
  width?: string;
};

const ZONE_OPTIONS = [
  { value: "internal", label: "Внутренний" },
  { value: "international", label: "Международный" },
];

const CHECKIN_FIELDS: FieldDef[] = [
  { key: "name", label: "Название", type: "text", width: "w-48" },
  { key: "zone", label: "Зона", type: "select", options: ZONE_OPTIONS, width: "w-40" },
  { key: "priority", label: "Приоритет", type: "number", width: "w-28" },
  { key: "open_before_dep_min", label: "Открытие (мин)", type: "number", width: "w-36" },
  { key: "close_before_dep_min", label: "Закрытие (мин)", type: "number", width: "w-36" },
  { key: "counters_count", label: "Стоек", type: "number", width: "w-24" },
  { key: "has_business_counter", label: "Бизнес", type: "checkbox", width: "w-24" },
  { key: "business_counters_count", label: "Бизнес стоек", type: "number", width: "w-32" },
  { key: "airline_codes", label: "Авиакомпании", type: "text", width: "w-44" },
  { key: "aircraft_type_code", label: "Тип ВС", type: "text", width: "w-32" },
  { key: "airport_codes", label: "Аэропорты", type: "text", width: "w-44" },
  { key: "valid_from", label: "Действует с", type: "date", width: "w-40" },
  { key: "valid_to", label: "Действует до", type: "date", width: "w-40" },
  { key: "is_active", label: "Активен", type: "checkbox", width: "w-24" },
];

const GATE_FIELDS: FieldDef[] = [
  { key: "name", label: "Название", type: "text", width: "w-48" },
  { key: "zone", label: "Зона", type: "select", options: ZONE_OPTIONS, width: "w-40" },
  { key: "priority", label: "Приоритет", type: "number", width: "w-28" },
  { key: "open_before_dep_min", label: "Начало посадки (мин)", type: "number", width: "w-40" },
  { key: "close_before_dep_min", label: "Окончание посадки (мин)", type: "number", width: "w-44" },
  { key: "gates_count", label: "Кол-во выходов", type: "number", width: "w-36" },
  { key: "airline_codes", label: "Авиакомпании", type: "text", width: "w-44" },
  { key: "aircraft_type_code", label: "Тип ВС", type: "text", width: "w-32" },
  { key: "valid_from", label: "Начало действия", type: "date", width: "w-40" },
  { key: "valid_to", label: "Окончание действия", type: "date", width: "w-40" },
  { key: "is_active", label: "Активен", type: "checkbox", width: "w-24" },
];


const EMPTY_CHECKIN: Omit<CheckinNorm, "id"> = {
  name: "",
  zone: "international",
  priority: 1,
  open_before_dep_min: 120,
  close_before_dep_min: 40,
  counters_count: 2,
  has_business_counter: false,
  business_counters_count: 0,
  airline_codes: null,
  aircraft_type_code: null,
  airport_codes: null,
  valid_from: null,
  valid_to: null,
  is_active: true,
};
const EMPTY_GATE: Omit<GateNorm, "id"> = {
  name: "",
  zone: "international",
  priority: 1,
  open_before_dep_min: 40,
  close_before_dep_min: 15,
  gates_count: 1,
  airline_codes: null,
  aircraft_type_code: null,
  valid_from: null,
  valid_to: null,
  is_active: true,
};
export default function NormsPage() {
  const [tab, setTab] = useState<TabKey>("checkin");
  const [checkin, setCheckin] = useState<CheckinNorm[]>([]);
  const [gate, setGate] = useState<GateNorm[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [editing, setEditing] = useState<NormRecord | null>(null);
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [a, b] = await Promise.all([
        api.getCheckinNorms(),
        api.getGateNorms(),
      ]);
      setCheckin(a);
      setGate(b);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const title = tab === "checkin"
    ? "Нормативы стоек регистрации"
    : "Нормативы выходов на посадку";

  const fields = tab === "checkin" ? CHECKIN_FIELDS : GATE_FIELDS;
  const rows: NormRecord[] = tab === "checkin" ? checkin : gate;

  const startCreate = () => {
    const base = tab === "checkin" ? EMPTY_CHECKIN : EMPTY_GATE;
    setEditing({ id: 0, ...(base as object) } as NormRecord);
    setDraft({ ...(base as object) });
  };

  const startEdit = (row: NormRecord) => {
    setEditing(row);
    setDraft({ ...row });
  };

  const closeEditor = () => {
    setEditing(null);
    setDraft(null);
  };

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      if (tab === "checkin") {
        if (!editing || editing.id === 0) await api.createCheckinNorm(draft as Omit<CheckinNorm, "id">);
        else await api.updateCheckinNorm(editing.id, draft as Partial<CheckinNorm>);
      } else {
        if (!editing || editing.id === 0) await api.createGateNorm(draft as Omit<GateNorm, "id">);
        else await api.updateGateNorm(editing.id, draft as Partial<GateNorm>);
      }
      await load();
      closeEditor();
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: number) => {
    if (!confirm("Удалить норматив?")) return;
    if (tab === "checkin") await api.deleteCheckinNorm(id);
    else await api.deleteGateNorm(id);
    await load();
  };

  const inputCls = "rounded border border-dispatch-border bg-dispatch-bg px-2 py-1.5 text-white text-sm focus:border-dispatch-accent focus:outline-none";

  return (
    <div className="min-h-screen bg-dispatch-bg text-gray-100 flex flex-col">
      <header className="flex items-center gap-3 border-b border-dispatch-border bg-dispatch-surface px-4 py-3">
        <Link
          href="/"
          className="rounded bg-dispatch-border px-2.5 py-1 text-xs text-gray-200 hover:bg-dispatch-muted/40 transition-colors"
        >
          ← Назад
        </Link>
        <h1 className="text-lg font-semibold text-white">{title}</h1>
      </header>

      <main className="flex-1 p-4 overflow-auto dashboard-scroll">
        <div className="mb-3 flex gap-1 rounded-lg border border-dispatch-border bg-[#111e31] p-1 w-fit">
          <TabBtn text="Стойки" active={tab === "checkin"} onClick={() => setTab("checkin")} />
          <TabBtn text="Выходы" active={tab === "gate"} onClick={() => setTab("gate")} />
        </div>

        <div className="mb-4 flex items-center justify-between">
          <p className="text-sm text-dispatch-muted">Всего нормативов: {rows.length}</p>
          <div className="flex gap-2">
            <button onClick={() => void load()} className="rounded border border-dispatch-border px-3 py-1.5 text-sm text-dispatch-muted hover:text-white">Обновить</button>
            <button onClick={startCreate} className="rounded bg-dispatch-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-600">+ Добавить норматив</button>
          </div>
        </div>

        {loading ? (
          <div className="py-14 text-center text-dispatch-muted">Загрузка...</div>
        ) : (
          <div className="overflow-auto rounded border border-dispatch-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-dispatch-surface text-dispatch-muted text-left text-xs uppercase tracking-wider">
                  {fields.map((f) => <th key={f.key} className="px-3 py-2.5 whitespace-nowrap">{f.label}</th>)}
                  <th className="px-3 py-2.5 text-right">Действия</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const rowMap = r as unknown as Record<string, unknown>;
                  return (
                  <tr key={r.id} className="border-t border-dispatch-border hover:bg-dispatch-surface/60">
                    {fields.map((f) => (
                      <td key={f.key} className="px-3 py-2 whitespace-nowrap">
                        {f.type === "checkbox"
                          ? (rowMap[f.key] ? "Да" : "Нет")
                          : String(rowMap[f.key] ?? "—")}
                      </td>
                    ))}
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-2">
                        <button onClick={() => startEdit(r)} className="rounded border border-dispatch-border px-2.5 py-1 text-xs text-dispatch-muted hover:text-white">Изм.</button>
                        <button onClick={() => void remove(r.id)} className="rounded bg-red-600/80 px-2.5 py-1 text-xs text-white hover:bg-red-600">Удалить</button>
                      </div>
                    </td>
                  </tr>
                );})}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={fields.length + 1} className="px-3 py-8 text-center text-dispatch-muted">Нет нормативов для этой вкладки.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {draft && editing && (
        <div className="fixed inset-0 z-[120] bg-black/60 flex items-center justify-center p-4" onMouseDown={(e) => e.target === e.currentTarget && closeEditor()}>
          <div className="w-full max-w-4xl rounded border border-dispatch-border bg-[#0d1728] p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-semibold text-white">{editing.id === 0 ? "Новый норматив" : `Редактирование #${editing.id}`}</h2>
              <button onClick={closeEditor} className="rounded border border-dispatch-border px-3 py-1 text-sm text-dispatch-muted">Закрыть</button>
            </div>
            <div className="grid grid-cols-2 gap-3 max-h-[62vh] overflow-auto">
              {fields.map((f) => (
                <label key={f.key} className="flex flex-col gap-1 text-xs text-dispatch-muted">
                  <span>{f.label}</span>
                  {f.type === "select" ? (
                    <select className={`${inputCls} ${f.width ?? ""}`} value={String(draft[f.key] ?? "")} onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}>
                      {f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  ) : f.type === "checkbox" ? (
                    <input type="checkbox" className="h-4 w-4 accent-dispatch-accent" checked={Boolean(draft[f.key])} onChange={(e) => setDraft({ ...draft, [f.key]: e.target.checked })} />
                  ) : (
                    <input
                      type={f.type}
                      className={`${inputCls} ${f.width ?? ""}`}
                      value={draft[f.key] == null ? "" : String(draft[f.key])}
                      onChange={(e) => {
                        const raw = e.target.value;
                        const val = f.type === "number" ? Number(raw) : raw || null;
                        setDraft({ ...draft, [f.key]: val });
                      }}
                    />
                  )}
                </label>
              ))}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={closeEditor} className="rounded border border-dispatch-border px-3 py-1.5 text-sm text-dispatch-muted">Отмена</button>
              <button onClick={() => void save()} disabled={saving} className="rounded bg-dispatch-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">{saving ? "Сохранение..." : "Сохранить"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TabBtn({ text, active, onClick }: { text: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
        active ? "bg-blue-600 text-white shadow-md" : "text-gray-400 hover:bg-[#1a2d44] hover:text-white"
      }`}
    >
      {text}
    </button>
  );
}
