from __future__ import annotations

import logging
from collections import defaultdict

import pandas as pd

from . import config


logger = logging.getLogger(__name__)


def solve_cpsat(
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    data: dict,
    enforce_all_employees_used: bool = True,
    max_time_seconds: int | None = None,
) -> tuple[pd.DataFrame | None, dict]:
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()

    cand_ids = candidates_df["candidate_id"].astype(int).tolist()
    duration_by_cid = dict(zip(
        candidates_df["candidate_id"].astype(int),
        candidates_df["duration"].astype(int),
    ))
    base_cost_by_cid = dict(zip(
        candidates_df["candidate_id"].astype(int),
        candidates_df["base_cost"].astype(int),
    ))

    x = {cid: model.NewBoolVar(f"x_{cid}") for cid in cand_ids}

    cand_by_emp_day: dict[tuple[int, str], list[int]] = defaultdict(list)
    cand_by_emp: dict[int, list[int]] = defaultdict(list)
    cand_covering_slot: dict[tuple[str, int, str], list[int]] = defaultdict(list)

    for c in candidates_df.itertuples():
        cid = int(c.candidate_id)
        cand_by_emp_day[(int(c.employee_id), str(c.ds))].append(cid)
        cand_by_emp[int(c.employee_id)].append(cid)
        for h in range(int(c.starttime), int(c.finishtime)):
            cand_covering_slot[(str(c.ds), int(h), str(c.station_key))].append(cid)

    overstaff = {}
    understaff = {}
    for r in requirements_df.itertuples():
        key = (str(r.ds), int(r.hour), str(r.station_key))
        req = max(int(r.required_labor), 1)
        overstaff[key] = model.NewIntVar(0, 2, f"over_{r.ds}_{r.hour}_{r.station_key}")
        understaff[key] = model.NewIntVar(0, req, f"under_{r.ds}_{r.hour}_{r.station_key}")

    employees = sorted(int(e) for e in data["staff_limits"]["employee_id"].tolist())
    unused = {e: model.NewBoolVar(f"unused_{e}") for e in employees}

    for r in requirements_df.itertuples():
        key = (str(r.ds), int(r.hour), str(r.station_key))
        req = max(int(r.required_labor), 1)
        covering = cand_covering_slot.get(key, [])
        actual = sum(x[cid] for cid in covering) if covering else 0
        model.Add(actual + understaff[key] >= req)
        model.Add(actual <= req + 2)
        model.Add(overstaff[key] >= actual - req)

    for (_, _), cids in cand_by_emp_day.items():
        if len(cids) > 1:
            model.Add(sum(x[cid] for cid in cids) <= 1)

    worktime_by_emp = dict(zip(
        data["staff_limits"]["employee_id"].astype(int),
        data["staff_limits"]["worktime_limit"].astype(int),
    ))
    for emp, cids in cand_by_emp.items():
        model.Add(
            sum(x[cid] * int(duration_by_cid[cid]) for cid in cids)
            <= int(worktime_by_emp[emp])
        )

    for emp, cids in cand_by_emp.items():
        model.Add(sum(x[cid] for cid in cids) <= 5)

    for emp in employees:
        cids = cand_by_emp.get(emp, [])
        if not cids:
            model.Add(unused[emp] == 1)
            continue
        worked = sum(x[cid] for cid in cids)
        if enforce_all_employees_used:
            model.Add(worked >= 1)
            model.Add(unused[emp] == 0)
        else:
            model.Add(worked >= 1).OnlyEnforceIf(unused[emp].Not())
            model.Add(worked == 0).OnlyEnforceIf(unused[emp])

    total_base_cost = sum(
        x[cid] * int(base_cost_by_cid[cid]) for cid in cand_ids
    )
    total_overstaff = sum(overstaff.values())
    total_understaff = sum(understaff.values())
    total_unused = sum(unused.values())

    model.Minimize(
        config.UNDERSTAFF_PENALTY * total_understaff
        + config.OVERSTAFF_PENALTY * total_overstaff
        + config.UNUSED_EMPLOYEE_PENALTY * total_unused
        + total_base_cost
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(
        max_time_seconds or config.MAX_TIME_SECONDS
    )
    solver.parameters.random_seed = config.RANDOM_SEED
    solver.parameters.num_search_workers = (
        1 if config.DETERMINISTIC else config.NUM_SEARCH_WORKERS
    )
    solver.parameters.log_search_progress = False

    logger.info(
        "Starting CP-SAT solve | candidates=%d | enforce_all_used=%s | "
        "max_time=%ds | workers=%d",
        len(cand_ids), enforce_all_employees_used,
        int(solver.parameters.max_time_in_seconds),
        solver.parameters.num_search_workers,
    )

    status = solver.Solve(model)
    status_name = solver.StatusName(status)

    info: dict = {
        "status": status_name,
        "wall_time_seconds": round(solver.WallTime(), 2),
        "enforce_all_employees_used": enforce_all_employees_used,
        "num_candidates": len(cand_ids),
        "num_slots": len(requirements_df),
        "num_employees": len(employees),
    }

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        info["objective_value"] = None
        return None, info

    info["objective_value"] = float(solver.ObjectiveValue())
    info["best_bound"] = float(solver.BestObjectiveBound())

    selected_ids = [cid for cid, var in x.items() if solver.Value(var) == 1]
    schedule = (
        candidates_df[candidates_df["candidate_id"].isin(selected_ids)][
            ["ds", "station_key", "employee_id", "starttime", "finishtime"]
        ]
        .sort_values(["ds", "station_key", "starttime", "employee_id"])
        .reset_index(drop=True)
    )

    info["total_overstaff"] = int(sum(solver.Value(v) for v in overstaff.values()))
    info["total_understaff"] = int(sum(solver.Value(v) for v in understaff.values()))
    info["total_unused_employees"] = int(sum(solver.Value(v) for v in unused.values()))
    info["unused_employees"] = sorted(
        int(e) for e in employees if solver.Value(unused[e]) == 1
    )

    logger.info(
        "CP-SAT %s | obj=%.0f | shifts=%d | over=%d | under=%d | unused=%d | %.1fs",
        status_name, info["objective_value"], len(schedule),
        info["total_overstaff"], info["total_understaff"],
        info["total_unused_employees"], info["wall_time_seconds"],
    )
    return schedule, info
