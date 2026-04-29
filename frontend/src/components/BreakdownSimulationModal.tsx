"use client";

import { useMemo, useState } from "react";
import type { Resource } from "@/lib/types";

export type BreakdownKind = "belt_gap" | "conveyor_engine";

export interface BreakdownSubmitPayload {
  kind: BreakdownKind;
  checkinResourceId: number;
}

interface BreakdownSimulationModalProps {
  open: boolean;
  resources: Resource[];
  busy?: boolean;
  onClose: () => void;
  onSubmit: (payload: BreakdownSubmitPayload) => Promise<void> | void;
}

function islandByCounterName(name: string): 1 | 2 | null {
  const m = String(name || "").trim().match(/^\d+$/);
  if (!m) return null;
  const n = Number(m[0]);
  if (n >= 1 && n <= 22) return 1;
  if (n >= 23 && n <= 43) return 2;
  return null;
}

export default function BreakdownSimulationModal({
  open,
  resources,
  busy = false,
  onClose,
  onSubmit,
}: BreakdownSimulationModalProps) {
  const checkinResources = useMemo(
    () => resources
      .filter((r) => r.resource_type === "check-in")
      .filter((r) => islandByCounterName(r.name) != null)
      .sort((a, b) => Number(a.name) - Number(b.name)),
    [resources]
  );

  const [kind, setKind] = useState<BreakdownKind>("belt_gap");
  const [checkinResourceId, setCheckinResourceId] = useState<number>(0);

  const selectedResource = checkinResources.find((r) => r.id === checkinResourceId);
  const island = selectedResource ? islandByCounterName(selectedResource.name) : null;

  const canSubmit = checkinResourceId > 0 && island != null && !busy;
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl rounded-xl border border-dispatch-border bg-[#0d1728] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-dispatch-border bg-[#111e31] px-5 py-3">
          <h3 className="text-base font-semibold text-white">Имитация поломки</h3>
          <button onClick={onClose} className="text-dispatch-muted hover:text-white">✕</button>
        </div>

        <div className="space-y-4 px-5 py-4">
          <div className="text-xs text-dispatch-muted">
            1 остров: стойки 1-22, 2 остров: стойки 23-43.
          </div>

          <label className="block">
            <span className="mb-1 block text-sm text-white">Тип поломки</span>
            <select
              className="w-full rounded border border-dispatch-border bg-dispatch-bg px-3 py-2 text-sm text-white focus:border-dispatch-accent focus:outline-none"
              value={kind}
              onChange={(e) => setKind(e.target.value as BreakdownKind)}
              disabled={busy}
            >
              <option value="belt_gap">Разрыв ленты</option>
              <option value="conveyor_engine">Поломка двигателя конвейера</option>
            </select>
          </label>

          <label className="block">
            <span className="mb-1 block text-sm text-white">Стойка, где произошла поломка</span>
            <select
              className="w-full rounded border border-dispatch-border bg-dispatch-bg px-3 py-2 text-sm text-white focus:border-dispatch-accent focus:outline-none"
              value={checkinResourceId}
              onChange={(e) => setCheckinResourceId(Number(e.target.value))}
              disabled={busy}
            >
              <option value={0}>Выберите стойку…</option>
              {checkinResources.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} {(() => {
                    const isl = islandByCounterName(r.name);
                    return isl ? `(остров ${isl})` : "";
                  })()}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex justify-end gap-2 border-t border-dispatch-border bg-[#111e31] px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-dispatch-border px-4 py-2 text-sm text-white hover:bg-dispatch-border transition-colors"
            disabled={busy}
          >
            Отмена
          </button>
          <button
            type="button"
            disabled={!canSubmit}
            onClick={() => onSubmit({ kind, checkinResourceId })}
            className="rounded bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {busy ? "Перераспределение…" : "Перераспределить"}
          </button>
        </div>
      </div>
    </div>
  );
}

