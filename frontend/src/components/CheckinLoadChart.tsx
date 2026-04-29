"use client";

import { useMemo } from "react";
import type { AllocationForDashboard } from "@/lib/types";

/** Отступы графика — используйте те же значения для подписей оси Y снаружи SVG. */
export const CHECKIN_LOAD_CHART_PAD = { top: 12, bottom: 10 } as const;

export type LoadSegment = { tStart: number; tEnd: number; count: number };

function normRt(v: string | null | undefined): string {
  const x = (v ?? "").trim().toLowerCase().replaceAll("_", "-");
  if (x === "checkin" || x === "check in") return "check-in";
  return x;
}

function effStart(a: AllocationForDashboard, mode: "plan" | "real"): string {
  if (mode === "plan" && a.plan_start_time) return a.plan_start_time;
  return a.start_time;
}

function effEnd(a: AllocationForDashboard, mode: "plan" | "real"): string {
  if (mode === "plan" && a.plan_end_time) return a.plan_end_time;
  return a.end_time;
}

/** Число занятых стоек в момент времени = число разных resource_id с активной аллокацией [s,e). */
export function computeCheckinLoadSegments(
  allocations: AllocationForDashboard[],
  viewMode: "plan" | "real",
  rangeMin: number,
  rangeMax: number
): { segments: LoadSegment[]; maxCount: number } {
  const checkin = allocations.filter((a) => normRt(a.resource_type) === "check-in");
  const intervals = checkin
    .map((a) => {
      const s = new Date(effStart(a, viewMode)).getTime();
      const e = new Date(effEnd(a, viewMode)).getTime();
      return {
        s: Math.max(rangeMin, s),
        e: Math.min(rangeMax, e),
        resId: a.resource_id,
      };
    })
    .filter((iv) => iv.e > iv.s && Number.isFinite(iv.s) && Number.isFinite(iv.e));

  const times = new Set<number>([rangeMin, rangeMax]);
  for (const iv of intervals) {
    times.add(iv.s);
    times.add(iv.e);
  }
  const sorted = Array.from(times).sort((a, b) => a - b);
  const segments: LoadSegment[] = [];
  let maxCount = 0;

  for (let i = 0; i < sorted.length - 1; i++) {
    const tStart = sorted[i];
    const tEnd = sorted[i + 1];
    if (tEnd <= tStart) continue;
    const mid = tStart + (tEnd - tStart) / 2;
    const active = new Set<number>();
    for (const iv of intervals) {
      if (mid >= iv.s && mid < iv.e) active.add(iv.resId);
    }
    const count = active.size;
    maxCount = Math.max(maxCount, count);
    segments.push({ tStart, tEnd, count });
  }

  return { segments, maxCount };
}

type Props = {
  canvasWidth: number;
  height: number;
  rangeMin: number;
  rangeSpan: number;
  segments: LoadSegment[];
  yMax: number;
};

/**
 * Ступенчатый график загруженности (как на терминале): синяя заливка + красная линия «сейчас».
 */
export default function CheckinLoadChart({
  canvasWidth,
  height,
  rangeMin,
  rangeSpan,
  segments,
  yMax,
}: Props) {
  const plotTop = CHECKIN_LOAD_CHART_PAD.top;
  const plotBottom = height - CHECKIN_LOAD_CHART_PAD.bottom;
  const plotH = Math.max(1, plotBottom - plotTop);

  const valToY = (v: number) =>
    plotBottom - (yMax > 0 ? (Math.min(v, yMax) / yMax) * plotH : 0);

  const { areaPath, linePath } = useMemo(() => {
    if (!segments.length || rangeSpan <= 0) {
      return { areaPath: "", linePath: "" };
    }
    const tx = (t: number) => ((t - rangeMin) / rangeSpan) * canvasWidth;
    const vy = (v: number) =>
      plotBottom - (yMax > 0 ? (Math.min(v, yMax) / yMax) * plotH : 0);
    const parts: string[] = [];
    const lineParts: string[] = [];
    let first = true;
    for (const seg of segments) {
      const x0 = tx(seg.tStart);
      const x1 = tx(seg.tEnd);
      const y = vy(seg.count);
      if (first) {
        parts.push(`M ${x0} ${plotBottom} L ${x0} ${y}`);
        lineParts.push(`M ${x0} ${y}`);
        first = false;
      } else {
        parts.push(`L ${x0} ${y}`);
        lineParts.push(`L ${x0} ${y}`);
      }
      parts.push(`L ${x1} ${y}`);
      lineParts.push(`L ${x1} ${y}`);
    }
    const lastX = tx(segments[segments.length - 1].tEnd);
    parts.push(`L ${lastX} ${plotBottom} Z`);
    return { areaPath: parts.join(" "), linePath: lineParts.join(" ") };
  }, [segments, rangeMin, rangeSpan, canvasWidth, plotBottom, yMax, plotH]);

  const nowMs = Date.now();
  const rangeEnd = rangeMin + rangeSpan;
  const showNow = nowMs >= rangeMin && nowMs <= rangeEnd;
  const nowX = showNow ? ((nowMs - rangeMin) / rangeSpan) * canvasWidth : null;

  const yTicks: number[] = [];
  const step = yMax <= 8 ? 2 : yMax <= 16 ? 2 : 4;
  for (let v = 0; v <= yMax; v += step) yTicks.push(v);

  return (
    <svg
      width={canvasWidth}
      height={height}
      className="block select-none"
      role="img"
      aria-label="График загруженности стоек регистрации"
    >
      {/* горизонтальная сетка */}
      {yTicks.map((v) => {
        const y = valToY(v);
        return (
          <line
            key={v}
            x1={0}
            x2={canvasWidth}
            y1={y}
            y2={y}
            stroke="rgba(148,163,184,0.2)"
            strokeDasharray="4 4"
            strokeWidth={1}
          />
        );
      })}
      {/* линия нуля (красноватая как на терминале) */}
      <line
        x1={0}
        x2={canvasWidth}
        y1={plotBottom}
        y2={plotBottom}
        stroke="rgba(239,68,68,0.5)"
        strokeWidth={1}
      />
      {areaPath ? (
        <>
          <path d={areaPath} fill="rgba(59,130,246,0.45)" stroke="none" />
          <path
            d={linePath}
            fill="none"
            stroke="#2563eb"
            strokeWidth={2.25}
            vectorEffect="non-scaling-stroke"
          />
        </>
      ) : null}
      {nowX != null && nowX >= 0 && nowX <= canvasWidth && (
        <line
          x1={nowX}
          x2={nowX}
          y1={0}
          y2={height}
          stroke="#ef4444"
          strokeWidth={2.5}
          pointerEvents="none"
        />
      )}
    </svg>
  );
}
