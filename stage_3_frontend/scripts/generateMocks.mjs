import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const OUT_DIR = path.resolve(__dirname, "..", "src", "data");

const STATION_NAMES = {
  K: "Кухня",
  C: "Прилавок",
  BVR: "Напитки",
  FF: "Картофель",
  TS: "Зал",
};
const STATIONS = ["K", "C", "BVR", "FF", "TS"];

const PERIOD_START = "2026-04-27";
const DAY_COUNT = 7;
const OPEN_HOUR = 7;
const CLOSE_HOUR = 23;
const HOURS = Array.from(
  { length: CLOSE_HOUR - OPEN_HOUR },
  (_, i) => OPEN_HOUR + i,
);

const WEEKDAY_RU = [
  "Воскресенье",
  "Понедельник",
  "Вторник",
  "Среда",
  "Четверг",
  "Пятница",
  "Суббота",
];

function shiftDate(iso, days) {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
function ruWeekday(iso) {
  const d = new Date(iso + "T00:00:00Z");
  return WEEKDAY_RU[d.getUTCDay()];
}

function mulberry32(seed) {
  let s = seed >>> 0;
  return function () {
    s |= 0;
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rnd = mulberry32(7);

function pick(arr) {
  return arr[Math.floor(rnd() * arr.length)];
}
function clamp(x, lo, hi) {
  return Math.max(lo, Math.min(hi, x));
}

const SHIFT_PRIO_BY_DUR = { 4: 3, 5: 4, 6: 4, 7: 1, 8: 1 };
const PREFERRED_DURS = [6, 7, 7, 8, 8, 8];

const EMP_COUNT = 60;
const EMPLOYEE_IDS = Array.from({ length: EMP_COUNT }, (_, i) => 11 + i);

const EMP_PROFILES = EMPLOYEE_IDS.map((id) => {
  const r = rnd();
  let stationsAvail;
  if (r < 0.5) stationsAvail = ["K", "C", "BVR", "FF", "TS"];
  else if (r < 0.78) stationsAvail = ["K", "C", "BVR", "FF"];
  else stationsAvail = ["C", "BVR", "TS", "FF"];
  const primary = pick(stationsAvail);
  const stationPriority = {};
  for (const st of STATIONS) {
    if (!stationsAvail.includes(st)) stationPriority[st] = 4;
    else if (st === primary) stationPriority[st] = 1;
    else stationPriority[st] = pick([2, 2, 3]);
  }
  return {
    id,
    primary,
    stationsAvail,
    stationPriority,
    weeklyTarget: pick([32, 36, 40, 40]),
    preferredDuration: pick(PREFERRED_DURS),
    earlyBird: rnd() < 0.5,
  };
});

function demandProfile(weekday, hour) {
  const isWeekend = weekday === 0 || weekday === 6;
  const lunchPeak = hour >= 12 && hour <= 14;
  const dinnerPeak = hour >= 18 && hour <= 20;
  const morning = hour <= 9;
  const lateNight = hour >= 21;

  if (lunchPeak)
    return { K: isWeekend ? 5 : 4, C: 3, BVR: 2, FF: 2, TS: isWeekend ? 3 : 2 };
  if (dinnerPeak)
    return { K: isWeekend ? 5 : 4, C: 2, BVR: 2, FF: 2, TS: isWeekend ? 3 : 2 };
  if (morning) return { K: 2, C: 1, BVR: 1, FF: 1, TS: 1 };
  if (lateNight) return { K: 2, C: 1, BVR: 1, FF: 1, TS: 1 };
  if (isWeekend) return { K: 3, C: 2, BVR: 2, FF: 2, TS: 2 };
  return { K: 2, C: 2, BVR: 1, FF: 1, TS: 1 };
}

function guestsForHour(weekday, hour) {
  const isWeekend = weekday === 0 || weekday === 6;
  const lunchPeak = hour >= 12 && hour <= 14;
  const dinnerPeak = hour >= 18 && hour <= 20;
  if (lunchPeak)
    return (isWeekend ? 350 : 280) + Math.floor(rnd() * 100);
  if (dinnerPeak)
    return (isWeekend ? 320 : 240) + Math.floor(rnd() * 100);
  if (hour <= 9) return 70 + Math.floor(rnd() * 40);
  if (hour >= 21) return 80 + Math.floor(rnd() * 60);
  if (isWeekend) return 180 + Math.floor(rnd() * 80);
  return 130 + Math.floor(rnd() * 70);
}

const empWeekHours = new Map(EMP_PROFILES.map((p) => [p.id, 0]));
const empWorkedDates = new Map(EMP_PROFILES.map((p) => [p.id, new Set()]));
const allShifts = [];

function pickShiftWindow(profile, anchor) {
  const max = Math.min(8, CLOSE_HOUR - anchor);
  const target = Math.min(profile.preferredDuration, max);
  if (target >= 4) {
    const candidates = [target];
    if (target - 1 >= 4) candidates.push(target - 1);
    if (target + 1 <= max) candidates.push(target + 1);
    const dur = pick(candidates);
    return { start: anchor, dur };
  }
  for (const d of [4, 5, 6, 7, 8]) {
    const start = clamp(anchor - (d - 1), OPEN_HOUR, CLOSE_HOUR - d);
    if (start <= anchor && start + d > anchor && start + d <= CLOSE_HOUR) {
      return { start, dur: d };
    }
  }
  return null;
}

function pickEmployee(date, station, hour) {
  const dateIdx = (() => {
    const d0 = new Date(PERIOD_START + "T00:00:00Z");
    const d = new Date(date + "T00:00:00Z");
    return Math.round((d - d0) / 86400000);
  })();
  void dateIdx;

  const candidates = EMP_PROFILES.filter((p) => {
    if (!p.stationsAvail.includes(station)) return false;
    const dates = empWorkedDates.get(p.id);
    if (dates.has(date)) return false;
    if (dates.size >= 5) return false;
    if ((empWeekHours.get(p.id) ?? 0) >= p.weeklyTarget + 2) return false;
    return true;
  });
  if (candidates.length === 0) {
    const fallback = EMP_PROFILES.filter((p) => {
      if (!p.stationsAvail.includes(station)) return false;
      const dates = empWorkedDates.get(p.id);
      if (dates.has(date)) return false;
      if (dates.size >= 5) return false;
      return true;
    });
    if (fallback.length === 0) return null;
    return fallback.sort(
      (a, b) =>
        (empWeekHours.get(a.id) ?? 0) - (empWeekHours.get(b.id) ?? 0) ||
        a.stationPriority[station] - b.stationPriority[station],
    )[0];
  }
  return candidates.sort(
    (a, b) =>
      a.stationPriority[station] - b.stationPriority[station] ||
      (empWeekHours.get(a.id) ?? 0) - (empWeekHours.get(b.id) ?? 0),
  )[0];
}

for (let dayIdx = 0; dayIdx < DAY_COUNT; dayIdx++) {
  const date = shiftDate(PERIOD_START, dayIdx);
  const weekday = new Date(date + "T00:00:00Z").getUTCDay();

  const required = {};
  const filled = {};
  for (const st of STATIONS) {
    required[st] = {};
    filled[st] = {};
    for (const h of HOURS) {
      required[st][h] = demandProfile(weekday, h)[st];
      filled[st][h] = 0;
    }
  }

  function overstaffsTooMuch(st, start, finish) {
    for (let hh = start; hh < finish; hh++) {
      if (required[st][hh] === undefined) continue;
      if (filled[st][hh] + 1 > required[st][hh] + 2) return true;
    }
    return false;
  }

  for (const st of STATIONS) {
    for (const h of HOURS) {
      while (filled[st][h] < required[st][h]) {
        const profile = pickEmployee(date, st, h);
        if (!profile) break;
        const win = pickShiftWindow(profile, h);
        if (!win) break;
        const start = win.start;
        const dur = win.dur;
        const finish = start + dur;
        if (finish > CLOSE_HOUR) break;
        if (overstaffsTooMuch(st, start, finish)) {
          let placed = false;
          for (const d of [4, 5, 6, 7, 8]) {
            const cstart = clamp(h - (d - 1), OPEN_HOUR, CLOSE_HOUR - d);
            const cfinish = cstart + d;
            if (cstart > h || cfinish <= h) continue;
            if (cfinish > CLOSE_HOUR) continue;
            if (!overstaffsTooMuch(st, cstart, cfinish)) {
              allShifts.push({
                date,
                employee_id: profile.id,
                station_key: st,
                station_name: STATION_NAMES[st],
                starttime: cstart,
                finishtime: cfinish,
                duration: d,
                station_priority: profile.stationPriority[st],
                shift_priority: SHIFT_PRIO_BY_DUR[d] ?? 2,
              });
              empWorkedDates.get(profile.id).add(date);
              empWeekHours.set(
                profile.id,
                (empWeekHours.get(profile.id) ?? 0) + d,
              );
              for (let hh = cstart; hh < cfinish; hh++) {
                filled[st][hh] += 1;
              }
              placed = true;
              break;
            }
          }
          if (!placed) break;
        } else {
          allShifts.push({
            date,
            employee_id: profile.id,
            station_key: st,
            station_name: STATION_NAMES[st],
            starttime: start,
            finishtime: finish,
            duration: dur,
            station_priority: profile.stationPriority[st],
            shift_priority: SHIFT_PRIO_BY_DUR[dur] ?? 2,
          });
          empWorkedDates.get(profile.id).add(date);
          empWeekHours.set(
            profile.id,
            (empWeekHours.get(profile.id) ?? 0) + dur,
          );
          for (let hh = start; hh < finish; hh++) {
            filled[st][hh] += 1;
          }
        }
      }
    }
  }
}

function recomputeFilled() {
  const map = new Map();
  for (const sh of allShifts) {
    for (let h = sh.starttime; h < sh.finishtime; h++) {
      const k = `${sh.date}|${sh.station_key}|${h}`;
      map.set(k, (map.get(k) ?? 0) + 1);
    }
  }
  return map;
}

function getProfile(empId) {
  return EMP_PROFILES.find((p) => p.id === empId);
}

let filledMap = recomputeFilled();

for (let dayIdx = 0; dayIdx < DAY_COUNT; dayIdx++) {
  const date = shiftDate(PERIOD_START, dayIdx);
  const weekday = new Date(date + "T00:00:00Z").getUTCDay();
  for (const st of STATIONS) {
    for (const h of HOURS) {
      const need = demandProfile(weekday, h)[st];
      let cur = filledMap.get(`${date}|${st}|${h}`) ?? 0;
      if (cur >= need) continue;
      const candidates = allShifts
        .map((sh, idx) => ({ sh, idx }))
        .filter(({ sh }) => {
          if (sh.date !== date || sh.station_key !== st) return false;
          if (sh.finishtime > h || sh.finishtime === h) {
            // Extend forward: this shift ends at or before h
            return sh.finishtime <= h && sh.duration < 8;
          }
          return false;
        });
      for (const { sh } of candidates) {
        if (cur >= need) break;
        const newFinish = h + 1;
        const newDur = newFinish - sh.starttime;
        if (newDur > 8) continue;
        let ok = true;
        for (let hh = sh.finishtime; hh < newFinish; hh++) {
          const reqAt = demandProfile(weekday, hh)[st];
          const curAt = filledMap.get(`${date}|${st}|${hh}`) ?? 0;
          if (curAt + 1 > reqAt + 2) {
            ok = false;
            break;
          }
        }
        if (!ok) continue;
        for (let hh = sh.finishtime; hh < newFinish; hh++) {
          const k = `${date}|${st}|${hh}`;
          filledMap.set(k, (filledMap.get(k) ?? 0) + 1);
        }
        const profile = getProfile(sh.employee_id);
        empWeekHours.set(
          sh.employee_id,
          (empWeekHours.get(sh.employee_id) ?? 0) + (newFinish - sh.finishtime),
        );
        sh.finishtime = newFinish;
        sh.duration = newDur;
        sh.shift_priority = SHIFT_PRIO_BY_DUR[newDur] ?? 2;
        void profile;
        cur = filledMap.get(`${date}|${st}|${h}`) ?? 0;
      }
    }
  }
}
for (let dayIdx = 0; dayIdx < DAY_COUNT; dayIdx++) {
  const date = shiftDate(PERIOD_START, dayIdx);
  const weekday = new Date(date + "T00:00:00Z").getUTCDay();
  for (const st of STATIONS) {
    for (const h of HOURS) {
      const need = demandProfile(weekday, h)[st];
      let cur = filledMap.get(`${date}|${st}|${h}`) ?? 0;
      while (cur < need) {
        const candidates = EMP_PROFILES.filter((p) => {
          if (!p.stationsAvail.includes(st)) return false;
          if (empWorkedDates.get(p.id).has(date)) return false;
          return true;
        }).sort(
          (a, b) =>
            a.stationPriority[st] - b.stationPriority[st] ||
            (empWeekHours.get(a.id) ?? 0) - (empWeekHours.get(b.id) ?? 0),
        );
        if (candidates.length === 0) break;
        const profile = candidates[0];
        let placed = false;
        for (const d of [4, 5, 6, 7, 8]) {
          for (
            let s = clamp(h - (d - 1), OPEN_HOUR, CLOSE_HOUR - d);
            s <= h && s + d <= CLOSE_HOUR;
            s++
          ) {
            const f = s + d;
            if (f <= h) continue;
            let ok = true;
            for (let hh = s; hh < f; hh++) {
              const reqAt = demandProfile(weekday, hh)[st];
              const curAt = filledMap.get(`${date}|${st}|${hh}`) ?? 0;
              if (curAt + 1 > reqAt + 2) {
                ok = false;
                break;
              }
            }
            if (!ok) continue;
            allShifts.push({
              date,
              employee_id: profile.id,
              station_key: st,
              station_name: STATION_NAMES[st],
              starttime: s,
              finishtime: f,
              duration: d,
              station_priority: profile.stationPriority[st],
              shift_priority: SHIFT_PRIO_BY_DUR[d] ?? 2,
            });
            empWorkedDates.get(profile.id).add(date);
            empWeekHours.set(
              profile.id,
              (empWeekHours.get(profile.id) ?? 0) + d,
            );
            for (let hh = s; hh < f; hh++) {
              const k = `${date}|${st}|${hh}`;
              filledMap.set(k, (filledMap.get(k) ?? 0) + 1);
            }
            placed = true;
            break;
          }
          if (placed) break;
        }
        if (!placed) break;
        cur = filledMap.get(`${date}|${st}|${h}`) ?? 0;
      }
    }
  }
}

for (const profile of EMP_PROFILES) {
  const days = empWorkedDates.get(profile.id);
  if (days.size > 0) continue;
  for (let dayIdx = 0; dayIdx < DAY_COUNT; dayIdx++) {
    const date = shiftDate(PERIOD_START, dayIdx);
    if (days.has(date)) continue;
    if (days.size >= 5) break;
    const station = profile.primary;
    const win = pickShiftWindow(profile, 11) ?? { start: 11, dur: 6 };
    const start = profile.earlyBird ? Math.max(OPEN_HOUR, win.start - 3) : win.start;
    const dur = win.dur;
    const finish = clamp(start + dur, OPEN_HOUR + 1, CLOSE_HOUR);
    allShifts.push({
      date,
      employee_id: profile.id,
      station_key: station,
      station_name: STATION_NAMES[station],
      starttime: start,
      finishtime: finish,
      duration: finish - start,
      station_priority: profile.stationPriority[station],
      shift_priority: SHIFT_PRIO_BY_DUR[finish - start] ?? 2,
    });
    days.add(date);
    empWeekHours.set(
      profile.id,
      (empWeekHours.get(profile.id) ?? 0) + (finish - start),
    );
    break;
  }
}

const byKey = new Map();
for (const sh of allShifts) {
  const key = `${sh.date}|${sh.employee_id}`;
  if (byKey.has(key)) continue;
  byKey.set(key, sh);
}

function buildShiftsByEmp() {
  const m = new Map();
  for (const sh of allShifts) {
    const arr = m.get(sh.employee_id) ?? [];
    arr.push(sh);
    m.set(sh.employee_id, arr);
  }
  return m;
}

const shiftsByEmp = buildShiftsByEmp();

const days = [];
for (let d = 0; d < DAY_COUNT; d++) {
  const date = shiftDate(PERIOD_START, d);
  const weekday = new Date(date + "T00:00:00Z").getUTCDay();
  const hours = [];
  for (const h of HOURS) {
    const need = demandProfile(weekday, h);
    const stations = STATIONS.map((st) => {
      const required = need[st];
      const empOut = [];
      for (const sh of allShifts) {
        if (
          sh.date === date &&
          sh.station_key === st &&
          h >= sh.starttime &&
          h < sh.finishtime
        ) {
          const profile = EMP_PROFILES.find((p) => p.id === sh.employee_id);
          empOut.push({
            employee_id: sh.employee_id,
            shift_start: sh.starttime,
            shift_end: sh.finishtime,
            shift_duration: sh.duration,
            station_key: sh.station_key,
            station_name: sh.station_name,
            station_priority: profile.stationPriority[sh.station_key],
            shift_priority: sh.shift_priority,
            weekly_hours: empWeekHours.get(sh.employee_id) ?? 0,
          });
        }
      }
      const assigned = empOut.length;
      const diff = assigned - required;
      let status;
      if (assigned < required) status = "understaffed";
      else if (diff === 0) status = "exact";
      else if (diff <= 2) status = "overstaffed_ok";
      else status = "overstaffed_bad";
      const warnings = [];
      if (assigned === 0 && required > 0) warnings.push("Нет сотрудников");
      if (status === "understaffed") warnings.push("Недобор");
      if (status === "overstaffed_bad") warnings.push("Перебор > +2");
      return {
        station_key: st,
        station_name: STATION_NAMES[st],
        required,
        assigned,
        diff,
        status,
        warnings,
        employees: empOut,
      };
    });
    hours.push({ hour: h, stations, guests_count: guestsForHour(weekday, h) });
  }
  days.push({ date, label: ruWeekday(date), hours });
}

let totalShifts = 0;
let totalHours = 0;
for (const sh of allShifts) {
  totalShifts++;
  totalHours += sh.duration;
}

let exactSlots = 0;
let okPlus = 0;
let under = 0;
let tooMuch = 0;
for (const day of days) {
  for (const h of day.hours) {
    for (const st of h.stations) {
      if (st.status === "exact") exactSlots++;
      else if (st.status === "overstaffed_ok") okPlus++;
      else if (st.status === "understaffed") under++;
      else if (st.status === "overstaffed_bad") tooMuch++;
    }
  }
}

const isValid = under === 0 && tooMuch === 0;

const timeline = {
  meta: {
    team: "Точка запятая",
    case: "Планирование расписания рабочих смен",
    mode: "STRICT",
    is_valid: isValid,
    generated_at: new Date().toISOString(),
    period_start: shiftDate(PERIOD_START, 0),
    period_end: shiftDate(PERIOD_START, DAY_COUNT - 1),
  },
  days,
};

const validation = {
  is_valid: isValid,
  solver_mode: "STRICT",
  errors: [],
  warnings: [],
  metrics: {
    total_shifts: totalShifts,
    total_work_hours: totalHours,
    total_errors: 0,
    total_warnings: 0,
    exact_coverage_slots: exactSlots,
    overstaffed_ok_slots: okPlus,
    understaffed_slots: under,
    too_much_overstaffed_slots: tooMuch,
  },
};

const employeeSummary = {
  employees: [...shiftsByEmp.entries()]
    .map(([id, shifts]) => {
      const sorted = [...shifts]
        .map((s) => ({
          date: s.date,
          station_key: s.station_key,
          station_name: s.station_name,
          starttime: s.starttime,
          finishtime: s.finishtime,
          duration: s.duration,
          station_priority: s.station_priority,
          shift_priority: s.shift_priority,
        }))
        .sort(
          (a, b) =>
            a.date.localeCompare(b.date) || a.starttime - b.starttime,
        );
      const total = sorted.reduce((s, x) => s + x.duration, 0);
      const daysSet = new Set(sorted.map((s) => s.date)).size;
      return {
        employee_id: id,
        total_hours: total,
        working_days: daysSet,
        days_off: DAY_COUNT - daysSet,
        shifts: sorted,
      };
    })
    .sort((a, b) => a.employee_id - b.employee_id),
};

fs.mkdirSync(OUT_DIR, { recursive: true });
fs.writeFileSync(
  path.join(OUT_DIR, "mockTimeline.json"),
  JSON.stringify(timeline, null, 2),
  "utf-8",
);
fs.writeFileSync(
  path.join(OUT_DIR, "mockValidationReport.json"),
  JSON.stringify(validation, null, 2),
  "utf-8",
);
fs.writeFileSync(
  path.join(OUT_DIR, "mockEmployeeSummary.json"),
  JSON.stringify(employeeSummary, null, 2),
  "utf-8",
);

console.log("Generated mocks in", OUT_DIR);
console.log("  total_shifts:", totalShifts, "total_hours:", totalHours);
console.log(
  "  exact:",
  exactSlots,
  "okPlus:",
  okPlus,
  "under:",
  under,
  "tooMuch:",
  tooMuch,
);
console.log("  is_valid:", isValid);
