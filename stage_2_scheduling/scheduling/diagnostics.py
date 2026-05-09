import logging
from collections import defaultdict

import pandas as pd

from . import config


logger = logging.getLogger(__name__)


def run_pre_solve_diagnostics(
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    data: dict,
) -> dict:
    coverage_index: dict[tuple[str, int, str], list[int]] = defaultdict(list)
    employees_per_slot: dict[tuple[str, int, str], set[int]] = defaultdict(set)
    for c in candidates_df.itertuples():
        for h in range(int(c.starttime), int(c.finishtime)):
            key = (str(c.ds), int(h), str(c.station_key))
            coverage_index[key].append(int(c.candidate_id))
            employees_per_slot[key].add(int(c.employee_id))

    slot_diagnostics = []
    infeasible_hints = 0
    for r in requirements_df.itertuples():
        key = (str(r.ds), int(r.hour), str(r.station_key))
        n_cov = len(coverage_index.get(key, []))
        n_emp = len(employees_per_slot.get(key, set()))
        req_eff = max(int(r.required_labor), 1)
        infeasible = n_emp < req_eff
        if infeasible:
            infeasible_hints += 1
        slot_diagnostics.append({
            "ds": r.ds,
            "hour": int(r.hour),
            "station": r.station_key,
            "required": int(r.required_labor),
            "required_eff": req_eff,
            "n_covering_candidates": int(n_cov),
            "n_unique_employees": int(n_emp),
            "infeasibility_hint_unique_employees": bool(infeasible),
            "criticality": float(req_eff) / max(n_cov, 1),
        })

    top_critical = sorted(
        slot_diagnostics, key=lambda d: (-d["criticality"], -d["required_eff"])
    )[:10]

    employee_diagnostics = []
    no_candidate_ids: list[int] = []
    for emp_row in data["staff_limits"].itertuples():
        emp = int(emp_row.employee_id)
        emp_cands = candidates_df[candidates_df["employee_id"] == emp]
        nc = int(len(emp_cands))
        if nc == 0:
            no_candidate_ids.append(emp)
        employee_diagnostics.append({
            "employee_id": emp,
            "n_candidates": nc,
            "available_days": int(emp_cands["ds"].nunique()) if nc else 0,
            "worktime_limit": int(emp_row.worktime_limit),
            "shift_limit": int(emp_row.shift_limit),
            "risk_of_unused": bool(nc == 0),
        })

    total_required_eff = int(
        requirements_df["required_labor"].clip(lower=1).astype(int).sum(),
    )
    total_available_max = int(data["staff_limits"]["worktime_limit"].astype(int).sum())

    aggregates = {
        "total_required_person_hours_eff_floor1": total_required_eff,
        "total_worktime_capacity_sum": total_available_max,
        "capacity_ge_required_aggregate": bool(
            total_available_max >= total_required_eff,
        ),
        "total_candidates": int(len(candidates_df)),
        "total_slots": int(len(requirements_df)),
        "slots_unique_employees_lt_required_eff": int(infeasible_hints),
        "employees_with_zero_candidates": no_candidate_ids,
        "employees_at_risk_of_unused_no_candidates": int(
            sum(1 for e in employee_diagnostics if e["risk_of_unused"])
        ),
        "total_required_person_hours_min": total_required_eff,
        "total_available_person_hours_max": total_available_max,
        "feasibility_indicator_required_le_available": bool(
            total_available_max >= total_required_eff,
        ),
        "infeasibility_hints": int(infeasible_hints),
    }

    req_by_ds = (
        requirements_df.assign(
            _req=lambda d: d["required_labor"].clip(lower=1).astype(int),
        )
        .groupby("ds")["_req"]
        .sum()
        .to_dict()
    )
    req_by_ds_station = (
        requirements_df.assign(
            _req=lambda d: d["required_labor"].clip(lower=1).astype(int),
        )
        .groupby(["ds", "station_key"])["_req"]
        .sum()
        .to_dict()
    )

    cap_slot_max = defaultdict(int)
    cand_hours_by_ds_station = defaultdict(int)
    for c in candidates_df.itertuples():
        nh = int(c.finishtime) - int(c.starttime)
        ds = str(c.ds)
        st = str(c.station_key)
        cand_hours_by_ds_station[(ds, st)] += nh
        for h in range(int(c.starttime), int(c.finishtime)):
            cap_slot_max[(ds, h, st)] += 1

    max_assignable_hours_upper_bound_ds_station = dict(cand_hours_by_ds_station)

    all_emps_cnt = len(data["staff_limits"])
    sum_req_eff = requirements_df.assign(
        r=lambda x: x["required_labor"].clip(lower=1).astype(int),
    )[["ds", "hour", "station_key", "r"]].drop_duplicates()
    total_slots = len(sum_req_eff)
    max_total_if_cap2_per_slot = int((sum_req_eff["r"] + 2).sum())

    heuristic_all_used_vs_cap2_note = (
        f"При «все {all_emps_cnt} должны быть в смене» нижняя оценка персоно-часов "
        f"минимум {all_emps_cnt} часов суммарно по выбранным сменам; слотов {total_slots} "
        f"с суммой верхней границы покрытия Σ(req_eff+2)={max_total_if_cap2_per_slot} по слотам."
    )

    if infeasible_hints > 0:
        logger.warning(
            "Предрешение: у %d слотов число доступных работников меньше эффективного требования.",
            infeasible_hints,
        )

    return {
        "aggregates": aggregates,
        "top_10_critical_slots": top_critical,
        "employee_diagnostics": employee_diagnostics,
        "slot_diagnostics_count": len(slot_diagnostics),
        "required_hours_by_day": {
            str(k): int(v) for k, v in sorted(req_by_ds.items(),
                                              key=lambda x: str(x[0]))
        },
        "required_hours_by_day_station": {
            f"{d}|{st}": int(v) for (d, st), v in req_by_ds_station.items()
        },
        "candidate_max_assignable_per_slot": {
            f"{ds}|{h}|{st}": int(v)
            for (ds, h, st), v in sorted(cap_slot_max.items())
        },
        "candidate_shift_hours_aggregate_by_day_station_upper_bound": {
            f"{d}|{st}": int(v)
            for (d, st), v in sorted(max_assignable_hours_upper_bound_ds_station.items())
        },
        "heuristic_all_employees_must_work_notes": heuristic_all_used_vs_cap2_note,
        "slots_sum_req_plus_2_capacity_upper_bound_hours": (
            max_total_if_cap2_per_slot),
    }


def run_post_solve_infeasibility_diagnostics(
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    data: dict,
    feasibility_info: dict | None,
    optimize_info: dict | None,
    relaxed_feasibility_info: dict | None,
) -> dict:
    out: dict = {
        "summary": [],
    }
    for label, inf in (
        ("feasibility_strict_all_staff", feasibility_info),
        ("optimize_strict_all_staff", optimize_info),
        ("feasibility_relaxed_without_all_staff", relaxed_feasibility_info),
    ):
        if inf is None:
            continue
        status = inf.get("status")
        phase = inf.get("phase", "?")
        out["summary"].append({
            "label": label,
            "phase": phase,
            "status": status,
            "seconds": inf.get("wall_time_seconds"),
        })
    if feasibility_info:
        fx = feasibility_info.get("status")
        rx = relaxed_feasibility_info.get("status") if relaxed_feasibility_info else None
        out["comparison_note"] = (
            f"Жёсткая допустимость (все в смене): {fx}. "
            f"Без «все в смене» (диагностика): {rx}."
            if relaxed_feasibility_info
            else f"Жёсткая допустимость (все в смене): {fx}"
        )
    return out

