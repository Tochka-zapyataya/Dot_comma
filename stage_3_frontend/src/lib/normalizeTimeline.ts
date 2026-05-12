import { buildWarnings, computeCoverageStatus } from "./coverageStatus";
import {
  STATION_NAMES,
  STATION_ORDER,
  type DaySlot,
  type EmployeeAtSlot,
  type HourSlot,
  type StationKey,
  type StationSlot,
  type TimelineData,
  type TimelineMeta,
  type CoverageStatus,
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

/** Плоский массив слотов из stage_2 (date, hour, stations..., employees: number[]). */
type BackendTimelineRow = {
  date?: string;
  hour?: number;
  stations?: Array<{
    station_key?: string;
    required?: number;
    assigned?: number;
    employees?: unknown[];
  }>;
};

/**
 * Принимает либо { meta?, days } (как в моках), либо массив часовых слотов из exporter stage_2.
 */
export function coerceTimelineInput(raw: unknown): TimelineData {
  if (
    raw &&
    typeof raw === "object" &&
    !Array.isArray(raw) &&
    Array.isArray((raw as TimelineData).days) &&
    (raw as TimelineData).days!.length > 0
  ) {
    return raw as TimelineData;
  }
  if (!Array.isArray(raw) || raw.length === 0) {
    return { meta: {}, days: [] };
  }

  const byDate = new Map<string, HourSlot[]>();

  for (const row of raw as BackendTimelineRow[]) {
    const date = row?.date;
    const hour = row?.hour;
    if (!date || typeof hour !== "number") continue;

    const stations: StationSlot[] = (row.stations ?? []).map((st) => {
      const key = String(st.station_key ?? "");
      const empsRaw = st.employees ?? [];
      const employees: EmployeeAtSlot[] = empsRaw.map((e) => {
        if (typeof e === "number") {
          return {
            employee_id: e,
            shift_start: hour,
            shift_end: hour + 1,
            shift_duration: 1,
            station_key: key,
          };
        }
        return e as EmployeeAtSlot;
      });
      return {
        station_key: key,
        required: Number(st.required ?? 0),
        assigned: Number(st.assigned ?? 0),
        employees,
      };
    });

    const slot: HourSlot = { hour, stations };
    const list = byDate.get(date) ?? [];
    list.push(slot);
    byDate.set(date, list);
  }

  const dates = [...byDate.keys()].sort();
  const days: DaySlot[] = dates.map((d) => ({
    date: d,
    hours: (byDate.get(d) ?? []).sort((a, b) => a.hour - b.hour),
  }));

  const meta: TimelineMeta = {
    period_start: dates[0],
    period_end: dates[dates.length - 1],
  };
  return { meta, days };
}

const VALID_COVERAGE: ReadonlySet<string> = new Set([
  "exact",
  "overstaffed_ok",
  "understaffed",
  "overstaffed_bad",
  "no_data",
]);

function normalizeStation(st: StationSlot): StationSlot {
  const required = Math.max(0, Number(st.required ?? 0));
  const assigned = Math.max(0, Number(st.assigned ?? 0));
  const incoming = st.status != null ? String(st.status) : "";
  const status: CoverageStatus = VALID_COVERAGE.has(incoming)
    ? (incoming as CoverageStatus)
    : computeCoverageStatus(required, assigned);
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
