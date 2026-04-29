/**
 * Клиент API backend (FastAPI).
 * BASE_URL задаётся через env (NEXT_PUBLIC_API_URL) или по умолчанию localhost:8000.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_V1 = `${BASE_URL}/api/v1`;

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_V1}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body?: object): Promise<T> {
  const res = await fetch(`${API_V1}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = `API ${path}: ${res.status}`;
    try {
      const data = await res.json();
      if (data?.detail) msg = `${msg} — ${String(data.detail)}`;
    } catch {
      // ignore parse error, keep generic message
    }
    throw new Error(msg);
  }
  return res.json();
}

async function patch<T>(path: string, body: object): Promise<T> {
  const res = await fetch(`${API_V1}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
  return res.json();
}

async function del(path: string): Promise<void> {
  const res = await fetch(`${API_V1}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
}

export const api = {
  getFlights: () => get<import("./types").Flight[]>("/flights/"),
  getAirlines: () => get<string[]>("/flights/airlines"),
  getResources: (params?: { resource_type?: string; active_only?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.resource_type) q.set("resource_type", params.resource_type);
    if (params?.active_only != null) q.set("active_only", String(params.active_only));
    const query = q.toString();
    return get<import("./types").Resource[]>(`/resources/${query ? `?${query}` : ""}`);
  },
  /** Аллокации для таймлайна за выбранную дату (date в ISO строке начала суток) */
  getAllocations: (date?: string, params?: { allocation_type?: "manual" | "auto" }) => {
    const q = new URLSearchParams();
    if (date) q.set("date", date);
    if (params?.allocation_type) q.set("allocation_type", params.allocation_type);
    const qs = q.toString();
    return get<import("./types").AllocationForDashboard[]>(`/allocations/${qs ? `?${qs}` : ""}`);
  },
  getForecastAirlineFlights: () =>
    get<import("./types").ForecastAirlineFlightsOption[]>("/distribution/forecast-options"),
  getSimilarFlightHistory: (params: { flight_number: string; airline: string; exclude_flight_id?: number; reference_plan_time?: string; limit?: number }) => {
    const q = new URLSearchParams();
    q.set("flight_number", params.flight_number);
    q.set("airline", params.airline);
    if (params.exclude_flight_id != null) q.set("exclude_flight_id", String(params.exclude_flight_id));
    if (params.reference_plan_time) q.set("reference_plan_time", params.reference_plan_time);
    if (params.limit != null) q.set("limit", String(params.limit));
    return get<import("./types").SimilarFlightHistoryItem[]>(`/allocations/history/similar?${q.toString()}`);
  },
  /** Импорт XML (только реальные MANUAL-аллокации, без автоалгоритма) */
  importXml: (body?: { arrival_xml_path?: string; departure_xml_path?: string }) =>
    post<{ parsed_flights: number; parsed_resources: number; created_manual_allocations: number }>("/import-xml/", body ?? {}),
  /** Импорт Excel-файла практики */
  importExcel: () =>
    post<{ flights: number; allocations: number; checkin: number; gate: number }>("/import-excel/", {}),
  /** Изменить ресурс/время аллокации (ручной override диспетчером) */
  patchAllocation: (id: number, body: { resource_id?: number; start_time?: string; end_time?: string }) =>
    patch<import("./types").AllocationForDashboard>(`/allocations/${id}`, body),

  /** Нормативы стоек регистрации */
  getCheckinNorms: () => get<import("./types").CheckinNorm[]>("/checkin-norms/"),
  createCheckinNorm: (body: Omit<import("./types").CheckinNorm, "id">) =>
    post<import("./types").CheckinNorm>("/checkin-norms/", body),
  updateCheckinNorm: (id: number, body: Partial<import("./types").CheckinNorm>) =>
    patch<import("./types").CheckinNorm>(`/checkin-norms/${id}`, body),
  deleteCheckinNorm: (id: number) => del(`/checkin-norms/${id}`),

  /** Нормативы выходов на посадку */
  getGateNorms: () => get<import("./types").GateNorm[]>("/gate-norms/"),
  createGateNorm: (body: Omit<import("./types").GateNorm, "id">) =>
    post<import("./types").GateNorm>("/gate-norms/", body),
  updateGateNorm: (id: number, body: Partial<import("./types").GateNorm>) =>
    patch<import("./types").GateNorm>(`/gate-norms/${id}`, body),
  deleteGateNorm: (id: number) => del(`/gate-norms/${id}`),

  /** Каркас «Распределение»: статистика по периоду (алгоритм — позже) */
  runDistribution: (body: import("./types").DistributionRunRequest) =>
    post<import("./types").DistributionRunResponse>("/distribution/run", body),

  getBreakdownHistory: () =>
    get<import("./types").BreakdownEvent[]>("/breakdowns/history"),
  startBreakdown: (body: { kind: import("./types").BreakdownKind; checkin_resource_id: number }) =>
    post<import("./types").BreakdownActionResponse>("/breakdowns/start", body),
  reconcileBreakdowns: () =>
    post<import("./types").BreakdownReconcileResponse>("/breakdowns/reconcile", {}),
  repairBreakdown: (eventId: string) =>
    post<import("./types").BreakdownActionResponse>(`/breakdowns/${encodeURIComponent(eventId)}/repair`, {}),
};
