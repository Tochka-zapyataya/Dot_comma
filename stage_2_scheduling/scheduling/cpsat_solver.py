import logging
from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from . import config


logger = logging.getLogger(__name__)


@dataclass
class _CPSatCtx:
    model: object
    x: dict[int, object]
    overstaff: dict[tuple[str, int, str], object]
    unused: dict[int, object]
    cand_ids: list[int]
    duration_by_cid: dict[int, int]
    station_pen_by_cid: dict[int, int]
    shift_pen_by_cid: dict[int, int]
    employees: list[int]
    candidates_df: pd.DataFrame
    requirements_df: pd.DataFrame
    worktime_by_emp: dict[int, int]
    global_cap: int
    cand_by_emp: dict[int, list[int]]


def _build_cpsat_ctx(
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    data: dict,
    enforce_all_employees_used: bool,
) -> _CPSatCtx:
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()

    cand_ids = candidates_df["candidate_id"].astype(int).tolist()
    duration_by_cid = dict(zip(
        candidates_df["candidate_id"].astype(int),
        candidates_df["duration"].astype(int),
    ))
    station_pen_by_cid = dict(zip(
        candidates_df["candidate_id"].astype(int),
        candidates_df["station_penalty_hours"].astype(int),
    ))
    shift_pen_by_cid = dict(zip(
        candidates_df["candidate_id"].astype(int),
        candidates_df["shift_penalty"].astype(int),
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

    overstaff: dict[tuple[str, int, str], object] = {}
    for r in requirements_df.itertuples():
        key = (str(r.ds), int(r.hour), str(r.station_key))
        overstaff[key] = model.NewIntVar(0, 2, f"over_{r.ds}_{r.hour}_{r.station_key}")

    employees = sorted(int(e) for e in data["staff_limits"]["employee_id"].tolist())
    unused = {e: model.NewBoolVar(f"unused_{e}") for e in employees}

    for r in requirements_df.itertuples():
        key = (str(r.ds), int(r.hour), str(r.station_key))
        req = max(int(r.required_labor), 1)
        covering = cand_covering_slot.get(key, [])
        actual = sum(x[cid] for cid in covering) if covering else 0
        model.Add(actual >= req)
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
            if enforce_all_employees_used:
                model.Add(0 == 1)
            else:
                model.Add(unused[emp] == 1)
            continue
        worked = sum(x[cid] for cid in cids)
        if enforce_all_employees_used:
            model.Add(worked >= 1)
            model.Add(unused[emp] == 0)
        else:
            model.Add(worked >= 1).OnlyEnforceIf(unused[emp].Not())
            model.Add(worked == 0).OnlyEnforceIf(unused[emp])

    global_cap = (
        max(int(v) for v in worktime_by_emp.values()) if worktime_by_emp else 0
    )
    week_hours: dict[int, object] = {}
    for emp in employees:
        cids = cand_by_emp.get(emp, [])
        if cids:
            week_hours[emp] = sum(
                x[cid] * int(duration_by_cid[cid]) for cid in cids
            )
        else:
            week_hours[emp] = 0

    max_h = model.NewIntVar(0, global_cap, "week_hours_max")
    min_h = model.NewIntVar(0, global_cap, "week_hours_min")
    for emp in employees:
        wh = week_hours[emp]
        model.Add(max_h >= wh)
        model.Add(min_h <= wh)
    balance_span = model.NewIntVar(0, global_cap, "week_hours_span")
    model.Add(balance_span == max_h - min_h)

    total_station_penalty = sum(
        x[cid] * int(station_pen_by_cid[cid]) for cid in cand_ids
    )
    total_shift_prio_penalty = sum(
        x[cid] * int(shift_pen_by_cid[cid]) for cid in cand_ids
    )
    total_selected_shifts = sum(x[cid] for cid in cand_ids)
    total_overstaff = sum(overstaff.values())

    ctx = _CPSatCtx(
        model=model,
        x=x,
        overstaff=overstaff,
        unused=unused,
        cand_ids=cand_ids,
        duration_by_cid=duration_by_cid,
        station_pen_by_cid=station_pen_by_cid,
        shift_pen_by_cid=shift_pen_by_cid,
        employees=employees,
        candidates_df=candidates_df,
        requirements_df=requirements_df,
        worktime_by_emp=worktime_by_emp,
        global_cap=global_cap,
        cand_by_emp=dict(cand_by_emp),
    )

    setattr(
        ctx,
        "_optimize_terms",
        (total_station_penalty, total_shift_prio_penalty, total_selected_shifts,
         balance_span, total_overstaff),
    )
    return ctx


def _apply_objective(ctx: _CPSatCtx) -> None:
    (
        total_station_penalty,
        total_shift_prio_penalty,
        total_selected_shifts,
        balance_span,
        total_overstaff,
    ) = ctx._optimize_terms
    ctx.model.Minimize(
        config.STATION_PRIORITY_WEIGHT * total_station_penalty
        + config.OVERSTAFF_WEIGHT * total_overstaff
        + config.SHIFT_PRIORITY_WEIGHT * total_shift_prio_penalty
        + config.SHIFT_COUNT_WEIGHT * total_selected_shifts
        + config.HOUR_BALANCE_WEIGHT * balance_span
    )


def _apply_hints_from_assignment(ctx: _CPSatCtx, selected_ids: set[int]) -> None:
    for cid, var in ctx.x.items():
        ctx.model.AddHint(var, int(cid in selected_ids))


def _run_solver(model: object, max_time_seconds: float | None) -> tuple[object, object]:
    from ortools.sat.python import cp_model

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(
        max_time_seconds if max_time_seconds is not None else config.MAX_TIME_SECONDS
    )
    solver.parameters.random_seed = config.RANDOM_SEED
    solver.parameters.num_search_workers = (
        1 if config.DETERMINISTIC else config.NUM_SEARCH_WORKERS
    )
    solver.parameters.log_search_progress = False
    status = solver.Solve(model)
    return solver, status


def _schedule_from_solution(
    ctx: _CPSatCtx,
    solver: object,
) -> pd.DataFrame:
    selected_ids = [cid for cid, var in ctx.x.items() if solver.Value(var) == 1]
    return (
        ctx.candidates_df[ctx.candidates_df["candidate_id"].isin(selected_ids)][
            ["ds", "station_key", "employee_id", "starttime", "finishtime"]
        ]
        .sort_values(["ds", "station_key", "starttime", "employee_id"])
        .reset_index(drop=True)
    )


def _info_base(
    ctx: _CPSatCtx,
    phase: str,
    enforce_all_employees_used: bool,
    status_name: str,
    wall_time: float,
) -> dict:
    return {
        "phase": phase,
        "status": status_name,
        "wall_time_seconds": round(wall_time, 2),
        "enforce_all_employees_used": enforce_all_employees_used,
        "num_candidates": len(ctx.cand_ids),
        "num_slots": len(ctx.requirements_df),
        "num_employees": len(ctx.employees),
    }


def solve_cpsat_feasibility(
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    data: dict,
    enforce_all_employees_used: bool = True,
    max_time_seconds: int | float | None = None,
    hint_selected_ids: set[int] | None = None,
) -> tuple[pd.DataFrame | None, dict]:
    from ortools.sat.python import cp_model

    ctx = _build_cpsat_ctx(
        requirements_df, candidates_df, data, enforce_all_employees_used,
    )
    if hint_selected_ids:
        _apply_hints_from_assignment(ctx, hint_selected_ids)

    logger.info(
        "CP-SAT feasibility-only | candidates=%d | all_employees_used=%s | "
        "max_time=%ss | workers=%d",
        len(ctx.cand_ids), enforce_all_employees_used,
        max_time_seconds or config.MAX_TIME_SECONDS,
        1 if config.DETERMINISTIC else config.NUM_SEARCH_WORKERS,
    )

    solver, status = _run_solver(ctx.model, max_time_seconds)
    status_name = solver.StatusName(status)
    info = _info_base(
        ctx, "feasibility", enforce_all_employees_used,
        status_name, solver.WallTime(),
    )

    info["objective_mode"] = "none"

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        info["objective_value"] = None
        return None, info

    info["objective_value"] = None
    sch = _schedule_from_solution(ctx, solver)
    info.update(_finalize_metrics(ctx, solver, sch))
    logger.info(
        "Feasibility %s | shifts=%d | over=%d | %.1fs",
        status_name, len(sch), info.get("total_overstaff", 0), info["wall_time_seconds"],
    )
    return sch, info


def solve_cpsat_optimize(
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    data: dict,
    enforce_all_employees_used: bool = True,
    max_time_seconds: int | float | None = None,
    hint_selected_ids: set[int] | None = None,
) -> tuple[pd.DataFrame | None, dict]:
    from ortools.sat.python import cp_model

    ctx = _build_cpsat_ctx(
        requirements_df, candidates_df, data, enforce_all_employees_used,
    )
    _apply_objective(ctx)
    if hint_selected_ids:
        _apply_hints_from_assignment(ctx, hint_selected_ids)

    logger.info(
        "CP-SAT optimize | candidates=%d | all_used=%s | max_time=%ss",
        len(ctx.cand_ids), enforce_all_employees_used,
        max_time_seconds or config.MAX_TIME_SECONDS,
    )

    solver, status = _run_solver(ctx.model, max_time_seconds)
    status_name = solver.StatusName(status)
    info = _info_base(
        ctx, "optimize", enforce_all_employees_used,
        status_name, solver.WallTime(),
    )
    info["objective_mode"] = "weighted"

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        info["objective_value"] = None
        return None, info

    info["objective_value"] = float(solver.ObjectiveValue())
    info["best_bound"] = float(solver.BestObjectiveBound())
    sch = _schedule_from_solution(ctx, solver)
    info.update(_finalize_metrics(ctx, solver, sch))
    logger.info(
        "Optimize %s | obj=%.0f | shifts=%d | over=%d | %.1fs",
        status_name,
        info["objective_value"],
        len(sch),
        info.get("total_overstaff", 0),
        info["wall_time_seconds"],
    )
    return sch, info


def _finalize_metrics(ctx: _CPSatCtx, solver: object, schedule: pd.DataFrame) -> dict:
    out = {
        "total_overstaff": int(sum(solver.Value(v) for v in ctx.overstaff.values())),
        "total_understaff": 0,
        "total_unused_employees": int(sum(solver.Value(v) for v in ctx.unused.values())),
        "unused_employees": sorted(
            int(e) for e in ctx.employees if solver.Value(ctx.unused[e]) == 1
        ),
    }
    out["final_num_shifts"] = int(len(schedule))
    return out


def candidate_ids_from_schedule(
    schedule_df: pd.DataFrame | None,
    candidates_df: pd.DataFrame,
) -> set[int] | None:
    if schedule_df is None or schedule_df.empty:
        return None
    cols = ["ds", "station_key", "employee_id", "starttime", "finishtime"]
    left = schedule_df[cols].copy()
    left["ds"] = left["ds"].astype(str)
    left["station_key"] = left["station_key"].astype(str)
    left["employee_id"] = left["employee_id"].astype(int)
    left["starttime"] = left["starttime"].astype(int)
    left["finishtime"] = left["finishtime"].astype(int)
    m = candidates_df[["candidate_id", *cols]].copy()
    m["ds"] = m["ds"].astype(str)
    m["station_key"] = m["station_key"].astype(str)
    m["employee_id"] = m["employee_id"].astype(int)
    m["starttime"] = m["starttime"].astype(int)
    m["finishtime"] = m["finishtime"].astype(int)
    j = (
        left.merge(m, on=cols, how="inner")
        .sort_values("candidate_id")
        .drop_duplicates(subset=cols, keep="first")
    )
    if len(j) != len(left):
        logger.warning(
            "Schedule↔candidate join: expected %d shifts, merged %d (hints degraded)",
            len(left), len(j),
        )
    if j.empty:
        return None
    return set(int(x) for x in j["candidate_id"].tolist())



