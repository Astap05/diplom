/**
 * Типы данных, соответствующие контрактам FastAPI backend.
 * Используются для типобезопасного маппинга ответов API в компоненты таймлайна.
 */

export type ResourceType = "check-in" | "gate";
export type AllocationType = "auto" | "manual";
export type FlightType = "arrival" | "departure";

export interface Flight {
  id: number;
  flight_number: string;
  airline: string;
  aircraft_type: string;
  plan_time: string | null;
  estimated_time: string | null;
  fact_time?: string | null;
  delayed_to?: string | null;
  is_delayed: boolean;
  is_cancelled?: boolean;
  flight_type: FlightType;
  code_shares: string | null;
  external_flight_id?: string | null;
  airport?: string | null;
  ru_airport?: string | null;
  en_airport?: string | null;
  status_raw?: string | null;
  status_tablo?: string | null;
  status_tablo_en?: string | null;
  status: string;
  passengers_count: number;
}

export interface Resource {
  id: number;
  resource_type: ResourceType;
  name: string;
  zone: string | null;
  is_active: boolean;
}

/** Аллокация с полями рейса и ресурса (ответ GET /api/v1/allocations) */
export interface AllocationForDashboard {
  id: number;
  flight_id: number;
  resource_id: number;
  start_time: string;
  end_time: string;
  plan_start_time?: string | null;
  plan_end_time?: string | null;
  allocation_type: AllocationType;
  flight_number: string;
  airline: string;
  aircraft_type: string;
  plan_time: string | null;
  estimated_time: string | null;
  fact_time?: string | null;
  delayed_to?: string | null;
  is_delayed: boolean;
  is_cancelled?: boolean;
  code_shares: string | null;
  external_flight_id?: string | null;
  airport?: string | null;
  ru_airport?: string | null;
  en_airport?: string | null;
  status_raw?: string | null;
  status_tablo?: string | null;
  status_tablo_en?: string | null;
  /** Может приходить с бэкенда для диаграмм загрузки */
  passengers_count?: number;
  extra_data?: string | null;
  resource_name: string;
  resource_type: ResourceType;
  /** Исходный ресурс до ручного изменения (если задан и ≠ resource_id — жёлтая плитка) */
  original_resource_id?: number | null;
  original_resource_name?: string | null;
  original_resource_type?: ResourceType | null;
}

/** Успешная аллокация из ответа POST /api/v1/allocate (resource_names — массив имён) */
export interface AllocationSuccess {
  flight_id: number;
  flight_number: string;
  flight_type: string;
  resource_type: ResourceType;
  resource_names: string[];
  start_time: string;
  end_time: string;
  allocation_type: AllocationType;
}

/** Конфликт/неразмещённый рейс из ответа POST /api/v1/allocate */
export interface AllocationConflict {
  flight_number: string;
  flight_type: string;
  resource_type: ResourceType;
  start_time: string;
  end_time: string;
  required_count?: number;
  reason: string;
}

export interface AllocateResponse {
  parsed_flights: number;
  parsed_resources: number;
  created_manual_allocations: number;
  auto_allocations_created: number;
  successes: AllocationSuccess[];
  conflicts: AllocationConflict[];
}

/** Информация об изменении аллокации диспетчером */
export interface ModificationInfo {
  oldResourceName: string;
  newResourceName: string;
  oldResourceType: ResourceType;
}

/** Норматив стоек регистрации */
export interface CheckinNorm {
  id: number;
  name: string;
  zone: string;
  priority: number;
  open_before_dep_min: number;
  close_before_dep_min: number;
  counters_count: number;
  has_business_counter: boolean;
  business_counters_count: number;
  airline_codes: string | null;
  aircraft_type_code: string | null;
  airport_codes: string | null;
  valid_from: string | null;
  valid_to: string | null;
  is_active: boolean;
}

/** Норматив выходов на посадку */
export interface GateNorm {
  id: number;
  name: string;
  zone: string;
  priority: number;
  open_before_dep_min: number;
  close_before_dep_min: number;
  gates_count: number;
  airline_codes: string | null;
  aircraft_type_code: string | null;
  valid_from: string | null;
  valid_to: string | null;
  is_active: boolean;
}

/** POST /api/v1/distribution/run */
export interface DistributionRunRequest {
  date_from: string;
  date_to: string;
  distribution_type: "selected_groups" | "all_flights";
  airline_names: string[];
  flight_numbers?: string[];
  common_checkin_same_counters: boolean;
  consider_slf: boolean;
  forecast_mode?: boolean;
  forecast_source_files?: string[];
}

export interface DistributionRunResponse {
  ok: boolean;
  message: string;
  flights_in_period: number;
  airlines_considered: number;
  manual_allocations_touched: number;
  duration_ms: number;
  log: string[];
}

export interface SimilarFlightHistoryItem {
  date: string;
  aircraft_type: string;
  checkin_interval: string;
  counters: string;
  pax_total: number;
  seats_total: number;
  status: string;
}

export interface ForecastAirlineFlightsOption {
  airline: string;
  airline_norm: string;
  flights: string[];
}

export type BreakdownKind = "belt_gap" | "conveyor_engine";

export interface BreakdownMoveItem {
  flight_number: string;
  from_counters: string;
  to_counters: string;
}

export interface BreakdownEvent {
  id: string;
  kind: BreakdownKind | string;
  kind_label: string;
  broken_resource_id: number | null;
  broken_counter_name: string;
  broken_island: 1 | 2;
  target_island: 1 | 2;
  created_at: string;
  repaired_at: string | null;
  status: "active" | "repaired";
  note?: string | null;
  moves: BreakdownMoveItem[];
}

export interface BreakdownActionResponse {
  ok: boolean;
  event: BreakdownEvent;
  moved_allocations: number;
  moved_flights: number;
  failed_flights: number;
}

export interface BreakdownReconcileResponse {
  ok: boolean;
  total_moved_allocations: number;
  total_moved_flights: number;
  events_touched: number;
}
