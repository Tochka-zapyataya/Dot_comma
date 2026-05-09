import {
  STATION_NAMES,
  type EmployeeShift,
  type EmployeeSummary,
  type EmployeeSummaryFile,
  type StationKey,
  type TimelineData,
} from "./types";

export function buildEmployeeSummaryFromTimeline(
  timeline: TimelineData,
): EmployeeSummaryFile {
  const byEmp = new Map<number, EmployeeShift[]>();
  const seen = new Set<string>();
  for (const day of timeline.days) {
    for (const hour of day.hours) {
      for (const st of hour.stations) {
        for (const e of st.employees) {
          const key = `${e.employee_id}:${day.date}:${e.station_key}:${e.shift_start}:${e.shift_end}`;
          if (seen.has(key)) continue;
          seen.add(key);
          const arr = byEmp.get(e.employee_id) ?? [];
          arr.push({
            date: day.date,
            station_key: e.station_key,
            station_name:
              e.station_name ??
              STATION_NAMES[e.station_key as StationKey] ??
              String(e.station_key),
            starttime: e.shift_start,
            finishtime: e.shift_end,
            duration: e.shift_duration,
            station_priority: e.station_priority ?? null,
            shift_priority: e.shift_priority ?? null,
          });
          byEmp.set(e.employee_id, arr);
        }
      }
    }
  }

  const employees: EmployeeSummary[] = Array.from(byEmp.entries()).map(
    ([id, shifts]) => {
      const sorted = shifts.sort(
        (a, b) =>
          a.date.localeCompare(b.date) || a.starttime - b.starttime,
      );
      const total = sorted.reduce((s, x) => s + x.duration, 0);
      const days = new Set(sorted.map((s) => s.date)).size;
      return {
        employee_id: id,
        total_hours: total,
        working_days: days,
        days_off: Math.max(timeline.days.length - days, 0),
        shifts: sorted,
      };
    },
  );

  return { employees: employees.sort((a, b) => a.employee_id - b.employee_id) };
}

export function findEmployeeShift(
  summary: EmployeeSummaryFile,
  employeeId: number,
  date: string,
  hour: number,
): EmployeeShift | null {
  const emp = summary.employees.find((e) => e.employee_id === employeeId);
  if (!emp) return null;
  return (
    emp.shifts.find(
      (s) =>
        s.date === date && hour >= s.starttime && hour < s.finishtime,
    ) ?? null
  );
}

export function getEmployeeSummary(
  summary: EmployeeSummaryFile,
  employeeId: number,
): EmployeeSummary | null {
  return (
    summary.employees.find((e) => e.employee_id === employeeId) ?? null
  );
}
