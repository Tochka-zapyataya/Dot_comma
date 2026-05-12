"""
build_public_data.py
--------------------
Converts real scheduling output into frontend-ready files in public/data/.

Run from stage_3_frontend/:
  python scripts/build_public_data.py
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCHED_OUT = ROOT / "stage_2_scheduling" / "output"
DATA_DIR  = ROOT / "data_tech_and_point"
FORECAST  = ROOT / "stage_1_forecast" / "output" / "forecast_standard_v14.xlsx"
PUBLIC    = Path(__file__).resolve().parents[1] / "public" / "data"

PUBLIC.mkdir(parents=True, exist_ok=True)

STATION_NAMES = {
    "BVR": "Напитки",
    "C":   "Прилавок",
    "FF":  "Картофель",
    "K":   "Кухня",
    "TS":  "Зал",
}
STATION_ORDER = ["K", "C", "BVR", "FF", "TS"]


def _weekday_ru(date: str) -> str:
    names = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
    try:
        return names[pd.Timestamp(date).weekday()]
    except Exception:
        return ""


# ── Load source data ─────────────────────────────────────────────────────────

schedule     = pd.read_csv(SCHED_OUT / "schedule.csv")
requirements = pd.read_csv(SCHED_OUT / "requirements.csv")
forecast     = pd.read_excel(FORECAST)
validation   = json.loads((SCHED_OUT / "validation_report.json").read_text())

station_prio = pd.read_csv(DATA_DIR / "station_priorities.csv")
shifts_df    = pd.read_csv(DATA_DIR / "shifts.csv")
staff_limits = pd.read_csv(DATA_DIR / "staff_limits.csv")

# Lookup dicts
prio_lookup = {
    (int(r.employee_id), str(r.station_key)): int(r.station_priority)
    for r in station_prio.itertuples()
}
shift_prio_lookup = {
    int(r.shift_duration): int(r.shift_priority)
    for r in shifts_df.itertuples()
}
weekly_hours = schedule.copy()
weekly_hours["duration"] = weekly_hours["finishtime"] - weekly_hours["starttime"]
weekly_hours_map = weekly_hours.groupby("employee_id")["duration"].sum().to_dict()

forecast_map = {
    (str(r.sale_date)[:10], int(r.sale_hour)): int(r.guests_count)
    for r in forecast.itertuples()
}
req_map = {
    (str(r.ds), int(r.hour), str(r.station_key)): int(r.required_labor)
    for r in requirements.itertuples()
}


# ── Build shift lookup: employee → day → (starttime, finishtime, station_key) ─

shift_by_emp_day = {}
for r in schedule.itertuples():
    key = (int(r.employee_id), str(r.ds))
    shift_by_emp_day[key] = {
        "starttime":    int(r.starttime),
        "finishtime":   int(r.finishtime),
        "station_key":  str(r.station_key),
        "duration":     int(r.finishtime) - int(r.starttime),
    }


# ── Build timeline ────────────────────────────────────────────────────────────

dates = sorted(schedule["ds"].unique())
days  = []

for date in dates:
    hours_list = []
    for hour in range(7, 23):
        stations = []
        for sk in STATION_ORDER:
            required = req_map.get((date, hour, sk), 0)
            # employees on this station at this hour
            mask = (
                (schedule["ds"] == date) &
                (schedule["station_key"] == sk) &
                (schedule["starttime"] <= hour) &
                (schedule["finishtime"] > hour)
            )
            rows = schedule[mask]
            employees = []
            for er in rows.itertuples():
                emp_id = int(er.employee_id)
                shift_info = shift_by_emp_day.get((emp_id, date), {})
                employees.append({
                    "employee_id":      emp_id,
                    "shift_start":      shift_info.get("starttime", hour),
                    "shift_end":        shift_info.get("finishtime", hour + 1),
                    "shift_duration":   shift_info.get("duration", 1),
                    "station_key":      sk,
                    "station_name":     STATION_NAMES.get(sk, sk),
                    "station_priority": prio_lookup.get((emp_id, sk), 4),
                    "shift_priority":   shift_prio_lookup.get(
                        shift_info.get("duration", 0), 4
                    ),
                    "weekly_hours":     int(weekly_hours_map.get(emp_id, 0)),
                })

            assigned = len(employees)
            diff     = assigned - required
            if required <= 0:
                status = "exact" if assigned == 0 else "overstaffed_bad"
            elif assigned < required:
                status = "understaffed"
            elif diff > 2:
                status = "overstaffed_bad"
            elif diff > 0:
                status = "overstaffed_ok"
            else:
                status = "exact"

            stations.append({
                "station_key":  sk,
                "station_name": STATION_NAMES.get(sk, sk),
                "required":     required,
                "assigned":     assigned,
                "diff":         diff,
                "status":       status,
                "warnings":     [],
                "employees":    employees,
            })

        hours_list.append({
            "hour":         hour,
            "guests_count": forecast_map.get((date, hour), 0),
            "stations":     stations,
        })

    days.append({
        "date":  date,
        "label": _weekday_ru(date),
        "hours": hours_list,
    })

timeline = {
    "meta": {
        "team":          "Точка запятая",
        "case":          "Планирование расписания рабочих смен",
        "mode":          "STRICT",
        "is_valid":      validation.get("is_valid", True),
        "generated_at":  datetime.now().isoformat(),
        "period_start":  dates[0] if dates else "",
        "period_end":    dates[-1] if dates else "",
    },
    "days": days,
}



(PUBLIC / "timeline.json").write_text(
    json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"✓ timeline.json  ({len(days)} days)")


# ── Build employee_summary.json ───────────────────────────────────────────────

all_dates = set(dates)
emp_list  = []

for emp_id in sorted(schedule["employee_id"].unique()):
    emp_rows = schedule[schedule["employee_id"] == emp_id].copy()
    emp_rows["duration"] = emp_rows["finishtime"] - emp_rows["starttime"]
    total_hours   = int(emp_rows["duration"].sum())
    working_days  = int(emp_rows["ds"].nunique())
    days_off      = 7 - working_days

    shifts = []
    for r in emp_rows.sort_values("ds").itertuples():
        dur = int(r.finishtime) - int(r.starttime)
        shifts.append({
            "date":             str(r.ds),
            "station_key":      str(r.station_key),
            "station_name":     STATION_NAMES.get(str(r.station_key), str(r.station_key)),
            "starttime":        int(r.starttime),
            "finishtime":       int(r.finishtime),
            "duration":         dur,
            "station_priority": prio_lookup.get((int(r.employee_id), str(r.station_key)), 4),
            "shift_priority":   shift_prio_lookup.get(dur, 4),
        })

    emp_list.append({
        "employee_id":  int(emp_id),
        "total_hours":  total_hours,
        "working_days": working_days,
        "days_off":     days_off,
        "shifts":       shifts,
    })

employee_summary = {"employees": emp_list}
(PUBLIC / "employee_summary.json").write_text(
    json.dumps(employee_summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"✓ employee_summary.json  ({len(emp_list)} employees)")


# ── Build validation_report.json ─────────────────────────────────────────────

m = validation.get("metrics", {})
report = {
    "is_valid":    validation.get("is_valid", True),
    "solver_mode": m.get("solver_mode", "STRICT"),
    "errors":      validation.get("errors", []),
    "warnings":    validation.get("warnings", []),
    "metrics": {
        "total_shifts":              m.get("total_shifts", 0),
        "total_work_hours":          m.get("total_hours", 0),
        "total_hours":               m.get("total_hours", 0),
        "total_required_hours":      m.get("total_required_hours", 0),
        "total_errors":              m.get("total_errors", 0),
        "total_warnings":            m.get("total_warnings", 0),
        "exact_coverage_slots":      m.get("exact_coverage_slots", 0),
        "overstaffed_ok_slots":      m.get("overstaffed_slots", 0),
        "overstaffed_slots":         m.get("overstaffed_slots", 0),
        "understaffed_slots":        m.get("understaffed_slots", 0),
        "too_much_overstaffed_slots":m.get("too_much_overstaffed_slots", 0),
        "used_employees":            m.get("used_employees", 0),
        "average_station_priority":  m.get("average_station_priority", 0),
        "hours_priority_1":          m.get("hours_priority_1", 0),
        "hours_priority_2":          m.get("hours_priority_2", 0),
        "hours_priority_3":          m.get("hours_priority_3", 0),
        "hours_priority_4":          m.get("hours_priority_4", 0),
        "shift_duration_distribution": m.get("shift_duration_distribution", {}),
    },
}
(PUBLIC / "validation_report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("✓ validation_report.json")


# ── Copy schedule files and staff_limits ─────────────────────────────────────

shutil.copy(SCHED_OUT / "schedule.xlsx", PUBLIC / "schedule.xlsx")
shutil.copy(SCHED_OUT / "schedule.csv",  PUBLIC / "schedule.csv")
shutil.copy(DATA_DIR / "staff_limits.csv", PUBLIC / "staff_limits.csv")
print("✓ schedule.xlsx / schedule.csv / staff_limits.csv")

print(f"\nAll files written to: {PUBLIC}")
