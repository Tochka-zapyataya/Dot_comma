from __future__ import annotations

import logging
import random
from collections import defaultdict

import pandas as pd

from . import config


logger = logging.getLogger(__name__)


def run_greedy(
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    data: dict,
) -> tuple[pd.DataFrame, dict]:
    rng = random.Random(config.RANDOM_SEED)

    cand_by_id = {int(r.candidate_id): r for r in candidates_df.itertuples()}
    cand_by_emp_day: dict[tuple[int, str], list[int]] = defaultdict(list)
    cand_covering: dict[tuple[str, int, str], list[int]] = defaultdict(list)
    for c in candidates_df.itertuples():
        cand_by_emp_day[(int(c.employee_id), str(c.ds))].append(int(c.candidate_id))
        for h in range(int(c.starttime), int(c.finishtime)):
            cand_covering[(str(c.ds), int(h), str(c.station_key))].append(
                int(c.candidate_id)
            )

    worktime_by_emp = dict(zip(
        data["staff_limits"]["employee_id"].astype(int),
        data["staff_limits"]["worktime_limit"].astype(int),
    ))
    shift_limit_by_emp = dict(zip(
        data["staff_limits"]["employee_id"].astype(int),
        data["staff_limits"]["shift_limit"].astype(int),
    ))

    used_emp_day: set[tuple[int, str]] = set()
    emp_total_hours: dict[int, int] = defaultdict(int)
    emp_working_days: dict[int, set[str]] = defaultdict(set)
    selected_cids: set[int] = set()
    slot_assigned: dict[tuple[str, int, str], int] = defaultdict(int)

    slots_sorted = []
    for r in requirements_df.itertuples():
        key = (str(r.ds), int(r.hour), str(r.station_key))
        n_cov = len(cand_covering.get(key, []))
        crit = float(r.required_labor) / max(n_cov, 1)
        slots_sorted.append((crit, r.required_labor, r.ds, r.hour, r.station_key))
    slots_sorted.sort(reverse=True)

    def can_use(cid: int) -> bool:
        c = cand_by_id[cid]
        emp = int(c.employee_id)
        ds = str(c.ds)
        dur = int(c.duration)
        if cid in selected_cids:
            return False
        if (emp, ds) in used_emp_day:
            return False
        if emp_total_hours[emp] + dur > worktime_by_emp.get(emp, 0):
            return False
        if dur > shift_limit_by_emp.get(emp, 0):
            return False
        if ds not in emp_working_days[emp] and len(emp_working_days[emp]) >= 5:
            return False
        return True

    def commit(cid: int) -> None:
        c = cand_by_id[cid]
        emp = int(c.employee_id)
        ds = str(c.ds)
        dur = int(c.duration)
        selected_cids.add(cid)
        used_emp_day.add((emp, ds))
        emp_total_hours[emp] += dur
        emp_working_days[emp].add(ds)
        for h in range(int(c.starttime), int(c.finishtime)):
            slot_assigned[(ds, h, str(c.station_key))] += 1

    for _, req, ds, hour, station in slots_sorted:
        key = (str(ds), int(hour), str(station))
        req_eff = max(int(req), 1)
        while slot_assigned[key] < req_eff:
            best_cid = None
            best_cost = None
            for cid in cand_covering.get(key, []):
                if not can_use(cid):
                    continue
                cost = int(cand_by_id[cid].base_cost)
                if best_cost is None or cost < best_cost:
                    best_cost = cost
                    best_cid = cid
            if best_cid is None:
                break
            commit(best_cid)

    employees = sorted(int(e) for e in data["staff_limits"]["employee_id"].tolist())
    unused_now = [e for e in employees if not emp_working_days[e]]

    for emp in unused_now:
        candidates_for_emp = sorted(
            (cid for cid in [
                cid for (e, _ds), cids in cand_by_emp_day.items() if e == emp
                for cid in cids
            ] if cid not in selected_cids),
            key=lambda cid: int(cand_by_id[cid].base_cost),
        )
        placed = False
        for cid in candidates_for_emp:
            c = cand_by_id[cid]
            ds = str(c.ds)
            if (emp, ds) in used_emp_day:
                continue
            if int(c.duration) > shift_limit_by_emp.get(emp, 0):
                continue
            if int(c.duration) > worktime_by_emp.get(emp, 0):
                continue
            if any(
                slot_assigned[(ds, h, str(c.station_key))]
                >= _req_at(requirements_df, ds, h, str(c.station_key)) + 2
                for h in range(int(c.starttime), int(c.finishtime))
            ):
                continue
            commit(cid)
            placed = True
            break
        if not placed:
            logger.warning("Greedy could not place employee %d", emp)

    schedule_rows = []
    for cid in selected_cids:
        c = cand_by_id[cid]
        schedule_rows.append({
            "ds": str(c.ds),
            "station_key": str(c.station_key),
            "employee_id": int(c.employee_id),
            "starttime": int(c.starttime),
            "finishtime": int(c.finishtime),
        })
    schedule_df = pd.DataFrame(schedule_rows).sort_values(
        ["ds", "station_key", "starttime", "employee_id"]
    ).reset_index(drop=True)

    info = {
        "status": "GREEDY",
        "total_shifts": int(len(schedule_df)),
        "unused_employees": sorted(
            int(e) for e in employees if not emp_working_days[e]
        ),
        "wall_time_seconds": None,
        "objective_value": None,
        "enforce_all_employees_used": False,
    }
    logger.info(
        "Greedy: %d shifts | unused=%d",
        info["total_shifts"], len(info["unused_employees"]),
    )
    return schedule_df, info


def _req_at(requirements_df: pd.DataFrame, ds: str, hour: int, station: str) -> int:
    sub = requirements_df[
        (requirements_df["ds"] == ds)
        & (requirements_df["hour"] == int(hour))
        & (requirements_df["station_key"] == station)
    ]
    if sub.empty:
        return 1
    return max(int(sub.iloc[0]["required_labor"]), 1)
