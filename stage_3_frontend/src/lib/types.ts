export type StationKey = "K" | "C" | "BVR" | "FF" | "TS";

export const STATION_NAMES: Record<StationKey, string> = {
  K: "Кухня",
  C: "Прилавок",
  BVR: "Напитки",
  FF: "Картофель",
  TS: "Зал",
};

export const STATION_ORDER: StationKey[] = ["K", "C", "BVR", "FF", "TS"];

export type CoverageStatus =
  | "exact"
  | "overstaffed_ok"
  | "understaffed"
  | "overstaffed_bad"
  | "no_data";

export interface EmployeeAtSlot {
  employee_id: number;
  shift_start: number;
  shift_end: number;
  shift_duration: number;
  station_key: StationKey | string;
  station_name?: string;
  station_priority?: number | null;
  shift_priority?: number | null;
  weekly_hours?: number | null;
}

export interface StationSlot {
  station_key: StationKey | string;
  station_name?: string;
  required: number;
  assigned: number;
  diff?: number;
  status?: CoverageStatus;
  warnings?: string[];
  employees: EmployeeAtSlot[];
}

export interface HourSlot {
  hour: number;
  stations: StationSlot[];
}

export interface DaySlot {
  date: string;
  label?: string;
  hours: HourSlot[];
}

export interface TimelineMeta {
  team?: string;
  case?: string;
  mode?: string;
  is_valid?: boolean;
  generated_at?: string;
  period_start?: string;
  period_end?: string;
}

export interface TimelineData {
  meta: TimelineMeta;
  days: DaySlot[];
}

export interface ValidationMetrics {
  total_shifts?: number;
  total_work_hours?: number;
  /** Суммарные назначенные часы по графику (ключ из stage_2). */
  total_hours?: number;
  total_errors?: number;
  total_warnings?: number;
  exact_coverage_slots?: number;
  overstaffed_ok_slots?: number;
  /** Слоты с допустимым переполнением (+1…+2), как в stage_2. */
  overstaffed_slots?: number;
  understaffed_slots?: number;
  too_much_overstaffed_slots?: number;
  [key: string]: unknown;
}

export interface ValidationReport {
  is_valid: boolean;
  solver_mode?: string;
  errors: string[];
  warnings: string[];
  metrics: ValidationMetrics;
}

export interface EmployeeShift {
  date: string;
  station_key: StationKey | string;
  station_name?: string;
  starttime: number;
  finishtime: number;
  duration: number;
  station_priority?: number | null;
  shift_priority?: number | null;
}

export interface EmployeeSummary {
  employee_id: number;
  total_hours: number;
  working_days: number;
  days_off?: number;
  shifts: EmployeeShift[];
}

export interface EmployeeSummaryFile {
  employees: EmployeeSummary[];
}
