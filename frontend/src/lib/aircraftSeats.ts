/**
 * Типовая макс. вместимость по типу ВС (согласовано с backend/app/services/aircraft_seat_capacity.py).
 * Используется в UI, если в extra ещё нет canonical_seats.
 */

const IATA_MAX: Record<string, number> = {
  E95: 124,
  E90: 110,
  E75: 76,
  E7W: 88,
  "738": 189,
  "73G": 149,
  "73H": 189,
  "733": 149,
  "73J": 189,
  "7M8": 189,
  "7M9": 220,
  "7M7": 172,
  "320": 220,
  "32N": 194,
  "32Q": 244,
  "321": 244,
  "319": 156,
  "332": 406,
  "333": 440,
  "359": 440,
  "388": 544,
  "763": 290,
  "764": 375,
  "752": 239,
  "77W": 550,
  "788": 250,
  "789": 330,
  SU9: 103,
  CR2: 50,
  CR7: 78,
  CR9: 90,
};

const NAME_PATTERNS: [string, number][] = [
  ["сухой superjet 100", 103],
  ["superjet 100", 103],
  ["superjet", 103],
  ["ssj-100", 103],
  ["ssj100", 103],
  ["ssj", 103],
  ["су-95", 103],
  ["su95", 103],
  ["ембраэр e175", 76],
  ["embraer e175", 76],
  ["e175-200", 76],
  ["e175", 76],
  ["емб195", 124],
  ["e195", 124],
  ["емб190", 110],
  ["e190", 110],
  ["бойнг 737 макс 9", 220],
  ["737 макс 9", 220],
  ["бойнг 737 макс 8", 189],
  ["бойнг 737 макс", 189],
  ["737 max 8", 189],
  ["737 макс 8", 189],
  ["б737-8", 189],
  ["737-800", 189],
  ["б737-3", 149],
  ["737-300", 149],
  ["б737-7", 149],
  ["737-700", 149],
  ["б-737", 149],
  ["эйрбас а321", 244],
  ["а321 нео", 244],
  ["а321", 244],
  ["эйрбас а320 нео", 194],
  ["а320 нео", 194],
  ["а-320", 220],
  ["а320", 220],
  ["эйрбас а320", 220],
  ["а-319", 156],
  ["а319", 156],
  ["а330-3", 440],
  ["а330-2", 406],
  ["а350", 440],
  ["б777", 550],
  ["б767", 290],
  ["б757", 239],
  ["б787", 250],
  ["боинг 787-8", 250],
  ["787-8", 250],
  ["црй200", 50],
  ["crj200", 50],
  ["crj", 50],
];

export function canonicalSeatCapacity(
  typeFull: string,
  iata: string | null | undefined,
  excelSeats: number | null | undefined
): number {
  const ia = (iata ?? "").trim().toUpperCase();
  if (ia && IATA_MAX[ia] != null) return IATA_MAX[ia];

  const tl = (typeFull ?? "").trim().toLowerCase();
  if (tl && tl !== "nan") {
    for (const [sub, seats] of NAME_PATTERNS) {
      if (tl.includes(sub)) return seats;
    }
  }

  if (excelSeats != null && Number.isFinite(excelSeats)) {
    const v = Math.round(excelSeats);
    if (v >= 1 && v <= 900) return v;
  }

  return 180;
}

/** Кресла для отображения: сначала поля из БД/прогноза, иначе расчёт по типу. */
export function resolveDisplaySeats(extra: Record<string, unknown>, aircraftTypeLabel: string | undefined): number {
  const rawCanon = Number(extra["canonical_seats"]);
  if (Number.isFinite(rawCanon) && rawCanon >= 1 && rawCanon <= 900) return Math.round(rawCanon);

  const maxCol = Number(extra["Кол-во кресел для типа ВС (макс.)"]);
  if (Number.isFinite(maxCol) && maxCol >= 1 && maxCol <= 900) return Math.round(maxCol);

  const seatsCol = Number(extra["Кол-во кресел"]);
  const iata = String(extra["Тип ВС (IATA)"] ?? extra["predicted_aircraft_type"] ?? "").trim();
  return canonicalSeatCapacity(String(aircraftTypeLabel ?? ""), iata || null, Number.isFinite(seatsCol) ? seatsCol : null);
}
