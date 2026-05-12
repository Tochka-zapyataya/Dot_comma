import logging

import numpy as np
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

    shift_durations = sorted(
        int(x) for x in shifts_tbl["shift_duration"].unique().tolist()
    )
    min_shift_dur = min(shift_durations)

    dur_to_shift_prio_raw: dict[int, int] = {}
    for r in shifts_tbl.itertuples():
        d = int(r.shift_duration)
        p = int(r.shift_priority)
        if d in dur_to_shift_prio_raw and dur_to_shift_prio_raw[d] != p:
            raise ValueError(
                f"Contradictory shift_priority for duration {d} in shifts.csv",
            )
        dur_to_shift_prio_raw[d] = p

    weekday_by_date = {
        ds: pd.to_datetime(ds).weekday() + 1 for ds in config.TARGET_DATES
    }

    sched_long = sched.rename(
        columns={"starttime": "win_start", "finishtime": "win_end"},
    )

    sl = staff_limits.copy()
    dates_df = pd.DataFrame({"ds": list(config.TARGET_DATES)})
    dates_df["weekday"] = dates_df["ds"].map(weekday_by_date)
    sl["_k"] = 1
    dates_df = dates_df.copy()
    dates_df["_k"] = 1
    staff_dates = sl.merge(dates_df, on="_k").drop(columns="_k")

    base = staff_dates.merge(
        sched_long,
        left_on=["employee_id", "weekday"],
        right_on=["employee_id", "day"],
        how="inner",
    )
    if "day" in base.columns:
        base = base.drop(columns=["day"])

    base["eff_start"] = np.maximum(base["win_start"].to_numpy(), config.OPEN_HOUR)
    base["eff_end"] = np.minimum(base["win_end"].to_numpy(), config.CLOSE_HOUR)
    base = base.loc[
        base["eff_end"] - base["eff_start"] >= min_shift_dur
    ].reset_index(drop=True)

    base["span"] = base["eff_end"] - base["eff_start"]
    base["max_dur"] = base[["shift_limit", "worktime_limit", "span"]].min(axis=1)

    durs = pd.DataFrame({"duration": shift_durations})
    bd = base.assign(_k=1).merge(durs.assign(_k=1), on="_k").drop(columns="_k")
    bd = bd.loc[bd["duration"] <= bd["max_dur"]].reset_index(drop=True)

    bd["shift_priority_raw"] = bd["duration"].map(dur_to_shift_prio_raw)
    bd = bd.dropna(subset=["shift_priority_raw"]).reset_index(drop=True)
    bd["shift_priority_raw"] = bd["shift_priority_raw"].astype(int)
    bd["shift_penalty"] = bd["shift_priority_raw"].map(_SHIFT_PRIO_PENALTY)

    if bd.empty:
        raise RuntimeError(
            "No feasible candidates after vectorized expand (windows × durations).",
        )

    es = bd["eff_start"].to_numpy(dtype=np.int64)
    ee = bd["eff_end"].to_numpy(dtype=np.int64)
    darr = bd["duration"].to_numpy(dtype=np.int64)
    n = ee - darr - es + 1
    bd = bd.assign(_n=n)
    bd = bd.loc[bd["_n"] > 0].drop(columns=["_n"]).reset_index(drop=True)

    if bd.empty:
        raise RuntimeError(
            "No feasible candidates generated. "
            "Check sched.csv windows, shift_limits, and shift durations.",
        )

    es = bd["eff_start"].to_numpy(dtype=np.int64)
    ee = bd["eff_end"].to_numpy(dtype=np.int64)
    darr = bd["duration"].to_numpy(dtype=np.int64)
    n = (ee - darr - es + 1).astype(np.int64)
    idx = np.repeat(np.arange(len(bd), dtype=np.int64), n)
    csn = np.concatenate([[0], np.cumsum(n[:-1])]) if len(n) else np.array([0])
    inner = np.arange(int(n.sum()), dtype=np.int64) - np.repeat(csn, n)
    starts_flat = es[idx] + inner

    bd_exp = bd.iloc[idx].reset_index(drop=True)
    bd_exp["starttime"] = starts_flat.astype(np.int64)
    bd_exp["finishtime"] = (bd_exp["starttime"] + bd_exp["duration"]).astype(np.int64)

    stations_df = pd.DataFrame({"station_key": config.STATIONS})
    cand = bd_exp.assign(_k=1).merge(stations_df.assign(_k=1), on="_k").drop(
        columns="_k",
    )

    cand = cand.merge(
        station_prio,
        on=["employee_id", "station_key"],
        how="left",
    )
    missing_prio_warnings = int(cand["station_priority"].isna().sum())
    cand["station_priority"] = cand["station_priority"].fillna(4).astype(int)

    if config.FILTER_DOMINATED_PRIO4_STATION_CANDIDATES:
        _slot = ["employee_id", "ds", "starttime", "finishtime", "duration"]
        gmin_slot = cand.groupby(_slot)["station_priority"].transform("min")
        cand = cand.loc[
            ~((cand["station_priority"] == 4) & (gmin_slot < 4))
        ].reset_index(drop=True)

    cand["station_penalty_per_hour"] = cand["station_priority"].map(
        _STATION_PRIO_PENALTY,
    )
    cand["station_penalty_hours"] = (
        cand["station_penalty_per_hour"] * cand["duration"]
    ).astype(int)

    cand["base_cost"] = (
        config.STATION_PRIORITY_WEIGHT * cand["station_penalty_hours"]
        + config.SHIFT_PRIORITY_WEIGHT * cand["shift_penalty"]
        + config.SHIFT_COUNT_WEIGHT
        - config.GREEDY_DURATION_BIAS * cand["duration"]
    ).astype(int)

    cand["weekday"] = cand["ds"].map(weekday_by_date)
    cand["candidate_id"] = np.arange(len(cand), dtype=np.int64)

    cols = [
        "candidate_id",
        "employee_id",
        "ds",
        "weekday",
        "station_key",
        "starttime",
        "finishtime",
        "duration",
        "shift_priority_raw",
        "shift_penalty",
        "station_priority",
        "station_penalty_per_hour",
        "station_penalty_hours",
        "base_cost",
    ]
    df = cand[cols].copy()

    if df.empty:
        raise RuntimeError(
            "No feasible candidates after filtering dominated prio=4 stations.",
        )

    if missing_prio_warnings > 0:
        logger.warning(
            "Missing station_priority for %d (employee, station) pairs; "
            "defaulted to 4.",
            missing_prio_warnings,
        )

    logger.info(
        "Generated %d candidates | %d employees | avg per emp=%.1f",
        len(df),
        df["employee_id"].nunique(),
        len(df) / max(df["employee_id"].nunique(), 1),
    )

    emp_with_no_cands = sorted(
        set(staff_limits["employee_id"].tolist()) - set(df["employee_id"].unique()),
    )
    if emp_with_no_cands:
        logger.warning(
            "Employees with NO candidates (strict mode may be INFEASIBLE): %s",
            emp_with_no_cands,
        )

    df.attrs["employees_without_candidates"] = emp_with_no_cands
    df.attrs["missing_station_priority_defaults"] = missing_prio_warnings

    return df
