from __future__ import annotations

import logging

import pandas as pd

from . import config


logger = logging.getLogger(__name__)


def build_candidates(data: dict) -> pd.DataFrame:
    sched = data["sched"]
    staff_limits = data["staff_limits"]
    station_prio = data["station_priorities"]
    shift_durations = sorted(data["shifts"]["shift_duration"].unique().tolist())

    weekday_by_date = {
        ds: pd.to_datetime(ds).weekday() + 1 for ds in config.TARGET_DATES
    }

    sched_lookup: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for r in sched.itertuples():
        sched_lookup.setdefault((int(r.employee_id), int(r.day)), []).append(
            (int(r.starttime), int(r.finishtime))
        )

    prio_lookup: dict[tuple[int, str], int] = {}
    for r in station_prio.itertuples():
        prio_lookup[(int(r.employee_id), str(r.station_key))] = int(r.station_priority)

    rows = []
    cid = 0
    missing_prio_warnings = 0

    for emp_row in staff_limits.itertuples():
        emp = int(emp_row.employee_id)
        shift_lim = int(emp_row.shift_limit)
        worktime_lim = int(emp_row.worktime_limit)

        for ds in config.TARGET_DATES:
            wd = weekday_by_date[ds]
            windows = sched_lookup.get((emp, wd), [])
            for (win_start, win_end) in windows:
                eff_start = max(win_start, config.OPEN_HOUR)
                eff_end = min(win_end, config.CLOSE_HOUR)
                if eff_end - eff_start < min(shift_durations):
                    continue
                max_dur = min(shift_lim, worktime_lim, eff_end - eff_start)

                for duration in shift_durations:
                    if duration > max_dur:
                        continue
                    for start in range(eff_start, eff_end - duration + 1):
                        end = start + duration
                        for station in config.STATIONS:
                            key = (emp, station)
                            if key in prio_lookup:
                                station_priority = prio_lookup[key]
                            else:
                                station_priority = 4
                                missing_prio_warnings += 1

                            shift_pen = config.SHIFT_DURATION_PENALTY[duration]
                            base_cost = (
                                config.STATION_PRIORITY_WEIGHT * station_priority
                                + config.SHIFT_DURATION_WEIGHT * shift_pen
                                - config.DURATION_REWARD_WEIGHT * duration
                            )
                            rows.append({
                                "candidate_id": cid,
                                "employee_id": emp,
                                "ds": ds,
                                "weekday": wd,
                                "station_key": station,
                                "starttime": int(start),
                                "finishtime": int(end),
                                "duration": int(duration),
                                "shift_duration_penalty": int(shift_pen),
                                "station_priority": int(station_priority),
                                "base_cost": int(base_cost),
                            })
                            cid += 1

    if not rows:
        raise RuntimeError(
            "No feasible candidates generated. "
            "Check sched.csv windows, shift_limits, and shift durations."
        )

    df = pd.DataFrame(rows)

    if missing_prio_warnings > 0:
        logger.warning(
            "Missing station_priority for %d (employee, station) pairs; "
            "defaulted to 4.", missing_prio_warnings,
        )

    logger.info(
        "Generated %d candidates | %d employees | avg per emp=%.1f",
        len(df),
        df["employee_id"].nunique(),
        len(df) / max(df["employee_id"].nunique(), 1),
    )

    emp_with_no_cands = (
        set(staff_limits["employee_id"].tolist()) - set(df["employee_id"].unique())
    )
    if emp_with_no_cands:
        logger.warning(
            "Employees with NO candidates (will be unused): %s",
            sorted(emp_with_no_cands),
        )

    return df
