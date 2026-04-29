/**
 * Моковые данные для тестирования UI до готовности API.
 * Структура совпадает с ответами backend: resources, allocations (AllocationForDashboard), conflicts.
 */

import type { Resource, AllocationForDashboard, AllocationConflict } from "./types";

/** Ресурсы аэропорта: группы для оси Y таймлайна (check-in, gate) */
export const mockResources: Resource[] = [
  { id: 1, resource_type: "check-in", name: "Стойка 1", zone: "A", is_active: true },
  { id: 2, resource_type: "check-in", name: "Стойка 2", zone: "A", is_active: true },
  { id: 3, resource_type: "check-in", name: "Стойка 3", zone: "A", is_active: true },
  { id: 4, resource_type: "gate", name: "Выход 10", zone: null, is_active: true },
  { id: 5, resource_type: "gate", name: "Выход 11", zone: null, is_active: true },
  { id: 6, resource_type: "gate", name: "Выход 12", zone: null, is_active: true },
];

/** Дата для моковых аллокаций: сегодня 06:00–22:00 */
function dayMs(hour: number, minute: number) {
  const d = new Date();
  d.setHours(hour, minute, 0, 0);
  return d.getTime();
}

/** Аллокации для таймлайна: маппинг в формат GET /allocations (id, resource_id, start/end, поля рейса) */
export const mockAllocations: AllocationForDashboard[] = [
  {
    id: 101,
    flight_id: 1,
    resource_id: 1,
    start_time: new Date(dayMs(6, 0)).toISOString(),
    end_time: new Date(dayMs(8, 30)).toISOString(),
    allocation_type: "auto",
    flight_number: "SU 1234",
    airline: "Aeroflot",
    aircraft_type: "A320",
    plan_time: new Date(dayMs(8, 0)).toISOString(),
    estimated_time: null,
    is_delayed: false,
    code_shares: null,
    resource_name: "Стойка 1",
    resource_type: "check-in",
  },
  {
    id: 102,
    flight_id: 2,
    resource_id: 2,
    start_time: new Date(dayMs(7, 0)).toISOString(),
    end_time: new Date(dayMs(9, 0)).toISOString(),
    allocation_type: "manual",
    flight_number: "S7 5678",
    airline: "S7",
    aircraft_type: "B737",
    plan_time: new Date(dayMs(8, 30)).toISOString(),
    estimated_time: new Date(dayMs(9, 15)).toISOString(),
    is_delayed: true,
    code_shares: "SU1234",
    resource_name: "Стойка 2",
    resource_type: "check-in",
  },
  {
    id: 103,
    flight_id: 3,
    resource_id: 4,
    start_time: new Date(dayMs(8, 15)).toISOString(),
    end_time: new Date(dayMs(8, 45)).toISOString(),
    allocation_type: "auto",
    flight_number: "SU 1234",
    airline: "Aeroflot",
    aircraft_type: "A320",
    plan_time: new Date(dayMs(8, 0)).toISOString(),
    estimated_time: null,
    is_delayed: false,
    code_shares: null,
    resource_name: "Выход 10",
    resource_type: "gate",
  },
  {
    id: 104,
    flight_id: 2,
    resource_id: 5,
    start_time: new Date(dayMs(9, 0)).toISOString(),
    end_time: new Date(dayMs(9, 30)).toISOString(),
    allocation_type: "auto",
    flight_number: "S7 5678",
    airline: "S7",
    aircraft_type: "B737",
    plan_time: new Date(dayMs(8, 30)).toISOString(),
    estimated_time: new Date(dayMs(9, 15)).toISOString(),
    is_delayed: true,
    code_shares: "SU1234",
    resource_name: "Выход 11",
    resource_type: "gate",
  },
  {
    id: 105,
    flight_id: 4,
    resource_id: 6,
    start_time: new Date(dayMs(10, 0)).toISOString(),
    end_time: new Date(dayMs(10, 45)).toISOString(),
    allocation_type: "auto",
    flight_number: "U6 9012",
    airline: "Ural Airlines",
    aircraft_type: "A321",
    plan_time: new Date(dayMs(10, 0)).toISOString(),
    estimated_time: null,
    is_delayed: false,
    code_shares: null,
    resource_name: "Выход 12",
    resource_type: "gate",
  },
];

/** Конфликты/неразмещённые рейсы для сайдбара (как из ответа POST /allocate) */
export const mockConflicts: AllocationConflict[] = [
  {
    flight_number: "WZ 5941",
    flight_type: "departure",
    resource_type: "check-in",
    start_time: new Date(dayMs(12, 0)).toISOString(),
    end_time: new Date(dayMs(14, 0)).toISOString(),
    required_count: 2,
    reason: "Нет свободных стоек в указанное время",
  },
  {
    flight_number: "DP 111",
    flight_type: "arrival",
    resource_type: "gate",
    start_time: new Date(dayMs(13, 30)).toISOString(),
    end_time: new Date(dayMs(14, 0)).toISOString(),
    reason: "Пересечение с SU 1234",
  },
];
