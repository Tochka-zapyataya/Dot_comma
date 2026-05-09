import logging
from collections import defaultdict

import pandas as pd

from . import config


logger = logging.getLogger(__name__)


REQUIRED_SCHEDULE_COLUMNS = ["ds", "station_key", "employee_id", "starttime", "finishtime"]
_STATION_PRIO_PENALTY_HOUR = {1: 0, 2: 1, 3: 4, 4: 10}


def validate_schedule(
    schedule_df: pd.DataFrame,
    requirements_df: pd.DataFrame,
    data: dict,
    omit_max_working_days_rule: bool = False,
    omit_one_shift_per_day_rule: bool = False,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    if schedule_df is None or len(schedule_df) == 0:
        errors.append("Schedule is empty.")
        return {
            "is_valid": False,
            "errors": errors,
            "warnings": warnings,
            "metrics": _empty_metrics(),
        }

    schedule = schedule_df.copy()
    _check_columns(schedule, errors)
    if errors:
        return {
            "is_valid": False,
            "errors": errors,
            "warnings": warnings,
            "metrics": _empty_metrics(),
        }

    schedule["employee_id"] = schedule["employee_id"].astype(int)
    schedule["starttime"] = schedule["starttime"].astype(int)
    schedule["finishtime"] = schedule["finishtime"].astype(int)
    schedule["ds"] = schedule["ds"].astype(str)
    schedule["station_key"] = schedule["station_key"].astype(str)
    schedule["duration"] = schedule["finishtime"] - schedule["starttime"]

    _check_no_nan(schedule, errors)
    _check_time_range(schedule, errors)
    _check_duration_in_shifts(schedule, data, errors)
    _check_shift_limit(schedule, data, errors)
    _check_within_sched_window(schedule, data, errors)
    _check_known_employees_only(schedule, data, errors)
    if not omit_one_shift_per_day_rule:
        _check_one_shift_per_day(schedule, errors)
    _check_no_double_station(schedule, errors)
    _check_worktime_limit(schedule, data, errors)
    if not omit_max_working_days_rule:
        _check_max_5_days(schedule, errors)
    used, unused = _check_all_employees_used(schedule, data, errors)

    prio_lookup_station = dict(
        zip(
            zip(
                data["station_priorities"]["employee_id"].astype(int),
                data["station_priorities"]["station_key"].astype(str),
            ),
            data["station_priorities"]["station_priority"].astype(int),
        )
    )

    shifts_df = data["shifts"].copy()
    shifts_df["shift_duration"] = shifts_df["shift_duration"].astype(int)
    shifts_df["shift_priority"] = shifts_df["shift_priority"].astype(int)
    dur_to_shift_prio = dict(
        zip(shifts_df["shift_duration"], shifts_df["shift_priority"])
    )

    coverage_metrics = _check_coverage(schedule, requirements_df, errors)

    avg_station_prio = _avg_station_priority(schedule, data)
    pq_metrics = _station_priority_hours_and_penalty(schedule, prio_lookup_station)

    duration_dist = (
        schedule["duration"].astype(int).value_counts().sort_index().to_dict()
    )
    duration_dist = {int(k): int(v) for k, v in duration_dist.items()}

    shift_prio_dist = _shift_priority_distribution(schedule, dur_to_shift_prio)

    emp_hours = schedule.groupby("employee_id")["duration"].sum()
    eh_min = int(emp_hours.min()) if len(emp_hours) else 0
    eh_max = int(emp_hours.max()) if len(emp_hours) else 0
    eh_avg = float(emp_hours.mean()) if len(emp_hours) else 0.0
    eh_std = (
        float(emp_hours.std(ddof=0)) if len(emp_hours) > 1 else 0.0
    )


    is_valid = len(errors) == 0

    total_slots = int(len(requirements_df))
    total_required_hours = int(requirements_df["required_labor"].clip(lower=1).sum())
    total_assigned_hours = int(schedule["duration"].sum())
    valid_slots = (
        total_slots
        - coverage_metrics["understaffed_slots"]
        - coverage_metrics["too_much_overstaffed_slots"]
    )
    coverage_rate_slots = round(valid_slots / max(total_slots, 1), 4)
    coverage_rate_hours = round(
        min(total_assigned_hours, total_required_hours)
        / max(total_required_hours, 1), 4,
    )

    metrics = {
        "is_valid": is_valid,
        "total_errors": len(errors),
        "total_warnings": len(warnings),
        "total_shifts": int(len(schedule)),
        "total_hours": total_assigned_hours,
        "total_required_hours": total_required_hours,
        "coverage_rate_slots": coverage_rate_slots,
        "coverage_rate_hours": coverage_rate_hours,
        "used_employees": int(len(used)),
        "unused_employees": sorted(int(e) for e in unused),
        "average_station_priority": avg_station_prio,
        "shift_duration_distribution": duration_dist,
        "shift_priority_distribution": shift_prio_dist,
        **pq_metrics,
        "min_hours": eh_min,
        "max_hours": eh_max,
        "avg_hours": round(eh_avg, 4),
        "std_hours": round(eh_std, 4),
        **coverage_metrics,
    }

    return {
        "is_valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "metrics": metrics,
    }


def _empty_metrics() -> dict:
    return {
        "is_valid": False,
        "total_errors": 0,
        "total_warnings": 0,
        "total_shifts": 0,
        "total_hours": 0,
        "total_required_hours": 0,
        "coverage_rate_slots": 0,
        "coverage_rate_hours": 0,
        "used_employees": 0,
        "unused_employees": [],
        "average_station_priority": None,
        "shift_duration_distribution": {},
        "shift_priority_distribution": {},
        "hours_priority_1": 0,
        "hours_priority_2": 0,
        "hours_priority_3": 0,
        "hours_priority_4": 0,
        "weighted_station_priority_penalty": 0,
        "min_hours": 0,
        "max_hours": 0,
        "avg_hours": 0.0,
        "std_hours": 0.0,
        "exact_coverage_slots": 0,
        "overstaffed_slots": 0,
        "understaffed_slots": 0,
        "too_much_overstaffed_slots": 0,
        "max_overstaffing": 0,
        "total_overstaffing": 0,
    }


def _check_columns(schedule: pd.DataFrame, errors: list[str]) -> None:
    missing = set(REQUIRED_SCHEDULE_COLUMNS) - set(schedule.columns)
    if missing:
        errors.append(f"Schedule missing columns: {sorted(missing)}")


def _check_no_nan(schedule: pd.DataFrame, errors: list[str]) -> None:
    for col in REQUIRED_SCHEDULE_COLUMNS:
        if schedule[col].isna().any():
            errors.append(f"Column {col} contains NaN/None")


def _check_time_range(schedule: pd.DataFrame, errors: list[str]) -> None:
    bad_start = (schedule["starttime"] < config.OPEN_HOUR).sum()
    bad_finish = (schedule["finishtime"] > config.CLOSE_HOUR).sum()
    bad_order = (schedule["starttime"] >= schedule["finishtime"]).sum()
    if bad_start:
        errors.append(f"{bad_start} shifts start before {config.OPEN_HOUR}")
    if bad_finish:
        errors.append(f"{bad_finish} shifts end after {config.CLOSE_HOUR}")
    if bad_order:
        errors.append(f"{bad_order} shifts have starttime >= finishtime")


def _check_duration_in_shifts(schedule: pd.DataFrame, data: dict, errors: list[str]) -> None:
    allowed = set(int(d) for d in data["shifts"]["shift_duration"].tolist())
    bad = schedule[~schedule["duration"].isin(allowed)]
    if len(bad):
        errors.append(
            f"{len(bad)} shifts have duration not in shifts.csv: "
            f"{sorted(bad['duration'].unique().tolist())}"
        )


def _check_shift_limit(schedule: pd.DataFrame, data: dict, errors: list[str]) -> None:
    sl = dict(zip(
        data["staff_limits"]["employee_id"].astype(int),
        data["staff_limits"]["shift_limit"].astype(int),
    ))
    violations = []
    for r in schedule.itertuples():
        emp = int(r.employee_id)
        if int(r.duration) > sl.get(emp, 0):
            violations.append((emp, int(r.duration), sl.get(emp, 0)))
    if violations:
        errors.append(
            f"{len(violations)} shifts exceed shift_limit. "
            f"Sample: {violations[:3]}"
        )


def _check_within_sched_window(
    schedule: pd.DataFrame, data: dict, errors: list[str]
) -> None:
    sched_lookup: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for r in data["sched"].itertuples():
        sched_lookup[(int(r.employee_id), int(r.day))].append(
            (int(r.starttime), int(r.finishtime))
        )
    weekday_by_ds = {
        ds: pd.to_datetime(ds).weekday() + 1 for ds in schedule["ds"].unique()
    }
    violations = 0
    for r in schedule.itertuples():
        emp = int(r.employee_id)
        wd = weekday_by_ds[r.ds]
        windows = sched_lookup.get((emp, wd), [])
        ok = any(
            int(r.starttime) >= win_s and int(r.finishtime) <= win_e
            for (win_s, win_e) in windows
        )
        if not ok:
            violations += 1
    if violations:
        errors.append(
            f"{violations} shifts violate sched.csv availability windows"
        )


def _check_one_shift_per_day(schedule: pd.DataFrame, errors: list[str]) -> None:
    counts = schedule.groupby(["employee_id", "ds"]).size()
    bad = counts[counts > 1]
    if len(bad):
        errors.append(
            f"{len(bad)} (employee, day) pairs have more than 1 shift"
        )


def _check_no_double_station(schedule: pd.DataFrame, errors: list[str]) -> None:
    overlaps = 0
    for (emp, ds), grp in schedule.groupby(["employee_id", "ds"]):
        rows = list(grp.itertuples())
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                if int(a.starttime) < int(b.finishtime) and int(b.starttime) < int(a.finishtime):
                    overlaps += 1
    if overlaps:
        errors.append(
            f"{overlaps} pairs of overlapping shifts for same employee on same day"
        )


def _check_worktime_limit(schedule: pd.DataFrame, data: dict, errors: list[str]) -> None:
    wl = dict(zip(
        data["staff_limits"]["employee_id"].astype(int),
        data["staff_limits"]["worktime_limit"].astype(int),
    ))
    totals = schedule.groupby("employee_id")["duration"].sum().to_dict()
    violations = []
    for emp, total in totals.items():
        if int(total) > wl.get(int(emp), 0):
            violations.append((int(emp), int(total), wl.get(int(emp), 0)))
    if violations:
        errors.append(
            f"{len(violations)} employees exceed worktime_limit. "
            f"Sample: {violations[:3]}"
        )


def _check_max_5_days(schedule: pd.DataFrame, errors: list[str]) -> None:
    days = schedule.groupby("employee_id")["ds"].nunique()
    bad = days[days > 5]
    if len(bad):
        errors.append(
            f"{len(bad)} employees have more than 5 working days. "
            f"Sample: {bad.head(3).to_dict()}"
        )


def _check_known_employees_only(
    schedule: pd.DataFrame, data: dict, errors: list[str]
) -> None:
    allowed = set(int(e) for e in data["staff_limits"]["employee_id"].tolist())
    rogue = sorted(set(schedule["employee_id"].astype(int).unique()) - allowed)
    if rogue:
        errors.append(
            f"{len(rogue)} employee(s) appear in schedule but not in "
            f"staff_limits.csv: {rogue}",
        )


def _check_all_employees_used(
    schedule: pd.DataFrame, data: dict, errors: list[str],
) -> tuple[set[int], set[int]]:
    all_emps = set(int(e) for e in data["staff_limits"]["employee_id"].tolist())
    used = set(int(e) for e in schedule["employee_id"].astype(int).unique())
    unused = all_emps - used
    if unused:
        errors.append(
            f"{len(unused)} employee(s) have no shifts (everyone must work ≥1): "
            f"{sorted(unused)}",
        )
    return used, unused


def _check_coverage(
    schedule: pd.DataFrame,
    requirements_df: pd.DataFrame,
    errors: list[str],
) -> dict:
    ds_arr = schedule["ds"].to_numpy()
    st_arr = schedule["station_key"].to_numpy()
    s_arr = schedule["starttime"].to_numpy()
    f_arr = schedule["finishtime"].to_numpy()

    exact = under = over = too_much = total_over = 0
    max_over = 0
    coverage_errors = []

    for r in requirements_df.itertuples():
        mask = (
            (ds_arr == r.ds)
            & (st_arr == r.station_key)
            & (s_arr <= r.hour)
            & (f_arr > r.hour)
        )
        actual = int(mask.sum())
        req_eff = max(int(r.required_labor), 1)
        diff = actual - req_eff

        if actual < req_eff:
            under += 1
            if len(coverage_errors) < 5:
                coverage_errors.append(
                    f"under: {r.ds} h={r.hour} {r.station_key} req={req_eff} actual={actual}"
                )
        elif diff > 2:
            too_much += 1
            max_over = max(max_over, diff)
            if len(coverage_errors) < 5:
                coverage_errors.append(
                    f"over+{diff}: {r.ds} h={r.hour} {r.station_key} req={req_eff} actual={actual}"
                )
        elif diff > 0:
            over += 1
            total_over += diff
            max_over = max(max_over, diff)
        else:
            exact += 1

    if under > 0:
        errors.append(f"{under} understaffed slots. Examples: {coverage_errors[:3]}")
    if too_much > 0:
        errors.append(
            f"{too_much} slots overstaffed by more than +2. "
            f"Examples: {[e for e in coverage_errors if 'over+' in e][:3]}"
        )

    return {
        "exact_coverage_slots": exact,
        "overstaffed_slots": over,
        "understaffed_slots": under,
        "too_much_overstaffed_slots": too_much,
        "max_overstaffing": max_over,
        "total_overstaffing": total_over,
    }


def _avg_station_priority(schedule: pd.DataFrame, data: dict) -> float | None:
    prio = dict(
        zip(
            zip(
                data["station_priorities"]["employee_id"].astype(int),
                data["station_priorities"]["station_key"].astype(str),
            ),
            data["station_priorities"]["station_priority"].astype(int),
        )
    )
    if schedule.empty:
        return None
    vals = [
        prio.get((int(r.employee_id), str(r.station_key)), 4)
        for r in schedule.itertuples()
    ]
    return round(sum(vals) / len(vals), 4)


def _station_priority_hours_and_penalty(
    schedule: pd.DataFrame,
    prio_lookup: dict,
) -> dict:
    buckets = {1: 0, 2: 0, 3: 0, 4: 0}
    weighted = 0
    for r in schedule.itertuples():
        dur = int(r.duration)
        p = prio_lookup.get((int(r.employee_id), str(r.station_key)), 4)
        if p not in buckets:
            p = 4
        buckets[p] += dur
        weighted += _STATION_PRIO_PENALTY_HOUR.get(p, 10) * dur
    return {
        "hours_priority_1": int(buckets[1]),
        "hours_priority_2": int(buckets[2]),
        "hours_priority_3": int(buckets[3]),
        "hours_priority_4": int(buckets[4]),
        "weighted_station_priority_penalty": int(weighted),
    }


def _shift_priority_distribution(
    schedule: pd.DataFrame,
    dur_to_shift_prio: dict[int, int],
) -> dict[str, int]:
    counts: dict[int, int] = defaultdict(int)
    for r in schedule.itertuples():
        sp = dur_to_shift_prio.get(int(r.duration))
        key = int(sp) if sp is not None else 0
        counts[key] += 1
    return {str(k): int(v) for k, v in sorted(counts.items())}
