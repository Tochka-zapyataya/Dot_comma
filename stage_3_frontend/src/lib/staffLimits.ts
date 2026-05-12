/** Парсинг staff_limits.csv: employee_id,worktime_limit,shift_limit */
export type StaffLimitRow = {
  worktime_limit: number;
  shift_limit: number;
};

export type StaffLimitsMap = Record<number, StaffLimitRow>;

export function parseStaffLimitsCsv(text: string): StaffLimitsMap {
  const lines = text.trim().split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return {};
  const out: StaffLimitsMap = {};
  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(",").map((s) => s.trim());
    if (parts.length < 3) continue;
    const id = Number(parts[0]);
    const worktime_limit = Number(parts[1]);
    const shift_limit = Number(parts[2]);
    if (!Number.isFinite(id) || !Number.isFinite(worktime_limit)) continue;
    out[id] = {
      worktime_limit,
      shift_limit: Number.isFinite(shift_limit) ? shift_limit : 0,
    };
  }
  return out;
}
