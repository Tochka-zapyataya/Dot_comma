import { buildWarnings, computeCoverageStatus } from "./coverageStatus";
import {
  STATION_NAMES,
  STATION_ORDER,
  type DaySlot,
  type HourSlot,
  type StationKey,
  type StationSlot,
  type TimelineData,
} from "./types";

const WEEKDAY_LABEL_RU = [
  "Воскресенье",
  "Понедельник",
  "Вторник",
  "Среда",
  "Четверг",
  "Пятница",
  "Суббота",
];

function ruWeekday(date: string): string {
  try {
    const d = new Date(date + "T00:00:00");
    if (Number.isNaN(d.getTime())) return "";
    return WEEKDAY_LABEL_RU[d.getDay()] ?? "";
  } catch {
    return "";
  }
}

function normalizeStation(st: StationSlot): StationSlot {
  const required = Math.max(0, Number(st.required ?? 0));
  const assigned = Math.max(0, Number(st.assigned ?? 0));
  const status = st.status ?? computeCoverageStatus(required, assigned);
  const warnings =
    st.warnings && st.warnings.length > 0
      ? st.warnings
      : buildWarnings(required, assigned, status);
  const station_name =
    st.station_name ??
    STATION_NAMES[st.station_key as StationKey] ??
    String(st.station_key);
  return {
    ...st,
    station_name,
    required,
    assigned,
    diff: assigned - required,
    status,
    warnings,
  };
}

function normalizeHour(h: HourSlot): HourSlot {
  const map = new Map<string, StationSlot>();
  for (const st of h.stations ?? []) {
    map.set(String(st.station_key), normalizeStation(st));
  }
  const ordered: StationSlot[] = STATION_ORDER.map((k) => {
    const found = map.get(k);
    if (found) return found;
    return normalizeStation({
      station_key: k,
      station_name: STATION_NAMES[k],
      required: 0,
      assigned: 0,
      employees: [],
    });
  });
  return {
    hour: Number(h.hour),
    stations: ordered,
  };
}

function normalizeDay(d: DaySlot): DaySlot {
  const sortedHours = [...(d.hours ?? [])]
    .map(normalizeHour)
    .sort((a, b) => a.hour - b.hour);
  return {
    date: d.date,
    label: d.label ?? ruWeekday(d.date),
    hours: sortedHours,
  };
}

export function normalizeTimeline(t: TimelineData): TimelineData {
  return {
    meta: {
      team: t.meta?.team ?? "Точка запятая",
      case: t.meta?.case ?? "Планирование расписания рабочих смен",
      mode: t.meta?.mode ?? "STRICT",
      is_valid: t.meta?.is_valid,
      generated_at: t.meta?.generated_at,
      period_start: t.meta?.period_start ?? t.days?.[0]?.date,
      period_end:
        t.meta?.period_end ?? t.days?.[t.days.length - 1]?.date,
    },
    days: (t.days ?? []).map(normalizeDay),
  };
}

export function findHour(t: TimelineData, dateIdx: number, hour: number): HourSlot | null {
  const day = t.days[dateIdx];
  if (!day) return null;
  return day.hours.find((h) => h.hour === hour) ?? null;
}

export function availableHours(day: DaySlot | undefined): number[] {
  if (!day) return [];
  return day.hours.map((h) => h.hour).sort((a, b) => a - b);
}

export function formatRuDate(iso: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yyyy = d.getFullYear();
  return `${dd}.${mm}.${yyyy}`;
}

export function formatHour(h: number): string {
  return `${String(h).padStart(2, "0")}:00`;
}
