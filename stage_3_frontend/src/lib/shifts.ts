import type { DaySlot } from "./types";

export interface ActiveShift {
  employee_id: number;
  station_key: string;
  shift_start: number;
  shift_end: number;
  shift_duration: number;
  station_priority?: number | null;
  shift_priority?: number | null;
  station_name?: string;
}

export function shiftsForDay(day: DaySlot | undefined | null): ActiveShift[] {
  if (!day) return [];
  const seen = new Map<string, ActiveShift>();
  for (const h of day.hours) {
    for (const st of h.stations) {
      for (const e of st.employees) {
        const key = `${e.employee_id}-${st.station_key}-${e.shift_start}-${e.shift_end}`;
        if (!seen.has(key)) {
          seen.set(key, {
            employee_id: e.employee_id,
            station_key: String(st.station_key),
            station_name: st.station_name ?? String(st.station_key),
            shift_start: e.shift_start,
            shift_end: e.shift_end,
            shift_duration: e.shift_duration,
            station_priority: e.station_priority ?? null,
            shift_priority: e.shift_priority ?? null,
          });
        }
      }
    }
  }
  return Array.from(seen.values()).sort(
    (a, b) =>
      a.shift_start - b.shift_start || a.employee_id - b.employee_id,
  );
}

export function activeShiftsAt(
  shifts: ActiveShift[],
  hourFloat: number,
): ActiveShift[] {
  return shifts.filter(
    (s) => s.shift_start <= hourFloat && hourFloat < s.shift_end,
  );
}

export function dayTimeBoundsHours(day: DaySlot | undefined | null): {
  min: number;
  max: number;
} {
  if (!day || day.hours.length === 0) return { min: 7, max: 23 };
  const hours = day.hours.map((h) => h.hour);
  return { min: Math.min(...hours), max: Math.max(...hours) + 1 };
}

export function formatHourMinute(totalMinutes: number): string {
  const m = Math.max(0, Math.round(totalMinutes));
  const hh = Math.floor(m / 60);
  const mm = m % 60;
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}
