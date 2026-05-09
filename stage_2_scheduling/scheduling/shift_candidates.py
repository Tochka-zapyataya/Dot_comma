import logging

import pandas as pd

from . import config


logger = logging.getLogger(__name__)


_STATION_PRIO_PENALTY = {1: 0, 2: 1, 3: 4, 4: 10}
_SHIFT_PRIO_PENALTY = {1: 0, 2: 1, 3: 2, 4: 4}


def build_candidates(data: dict) -> pd.DataFrame:
    sched = data["sched"]
    staff_limits = data["staff_limits"]
    station_prio = data["station_priorities"]
    shifts_tbl = data["shifts"]

    shift_durations = sorted(int(x) for x in shifts_tbl["shift_duration"].unique().tolist())
    dur_to_shift_prio_raw: dict[int, int] = {}
    for r in shifts_tbl.itertuples():
        d = int(r.shift_duration)
        p = int(r.shift_priority)
        if d in dur_to_shift_prio_raw and dur_to_shift_prio_raw[d] != p:
            raise ValueError(f"Contradictory shift_priority for duration {d} in shifts.csv")
        dur_to_shift_prio_raw[d] = p

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
                    sp_raw = dur_to_shift_prio_raw.get(duration)
                    if sp_raw is None:
                        raise ValueError(f"Duration {duration} not listed in shifts.csv")
                    shift_pen = _SHIFT_PRIO_PENALTY[sp_raw]
                    for start in range(eff_start, eff_end - duration + 1):
                        end = start + duration
                        for station in config.STATIONS:
                            key = (emp, station)
                            if key in prio_lookup:
                                station_priority = prio_lookup[key]
                            else:
                                station_priority = 4
                                missing_prio_warnings += 1

                            st_pen_h = _STATION_PRIO_PENALTY[station_priority]
                            station_penalty_hours = int(st_pen_h * duration)
                            base_cost = int(
                                config.STATION_PRIORITY_WEIGHT * station_penalty_hours
                                + config.SHIFT_PRIORITY_WEIGHT * shift_pen
                                + config.SHIFT_COUNT_WEIGHT
                                - config.GREEDY_DURATION_BIAS * duration
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
                                "shift_priority_raw": int(sp_raw),
                                "shift_penalty": int(shift_pen),
                                "station_priority": int(station_priority),
                                "station_penalty_per_hour": int(st_pen_h),
                                "station_penalty_hours": int(station_penalty_hours),
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
