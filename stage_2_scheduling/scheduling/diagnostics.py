from __future__ import annotations

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
            key = (c.ds, h, c.station_key)
            coverage_index[key].append(int(c.candidate_id))
            employees_per_slot[key].add(int(c.employee_id))

    slot_diagnostics = []
    infeasible_hints = 0
    for r in requirements_df.itertuples():
        key = (r.ds, int(r.hour), r.station_key)
        n_cov = len(coverage_index.get(key, []))
        n_emp = len(employees_per_slot.get(key, set()))
        req = int(r.required_labor)
        infeasible = n_emp < req
        if infeasible:
            infeasible_hints += 1
        slot_diagnostics.append({
            "ds": r.ds,
            "hour": int(r.hour),
            "station": r.station_key,
            "required": req,
            "n_covering_candidates": int(n_cov),
            "n_unique_employees": int(n_emp),
            "infeasibility_hint": bool(infeasible),
            "criticality": float(req) / max(n_cov, 1),
        })

    top_critical = sorted(
        slot_diagnostics, key=lambda d: (-d["criticality"], -d["required"])
    )[:10]

    employee_diagnostics = []
    for emp_row in data["staff_limits"].itertuples():
        emp = int(emp_row.employee_id)
        emp_cands = candidates_df[candidates_df["employee_id"] == emp]
        employee_diagnostics.append({
            "employee_id": emp,
            "n_candidates": int(len(emp_cands)),
            "available_days": int(emp_cands["ds"].nunique()),
            "worktime_limit": int(emp_row.worktime_limit),
            "shift_limit": int(emp_row.shift_limit),
            "risk_of_unused": bool(len(emp_cands) == 0),
        })

    total_required = int(requirements_df["required_labor"].sum())
    total_available = int(data["staff_limits"]["worktime_limit"].sum())
    aggregates = {
        "total_required_person_hours_min": total_required,
        "total_available_person_hours_max": total_available,
        "feasibility_indicator_required_le_available": bool(total_required <= total_available),
        "total_candidates": int(len(candidates_df)),
        "total_slots": int(len(requirements_df)),
        "infeasibility_hints": int(infeasible_hints),
        "employees_at_risk_of_unused": int(
            sum(1 for e in employee_diagnostics if e["risk_of_unused"])
        ),
    }

    if infeasible_hints > 0:
        logger.warning(
            "Pre-solve: %d slots have fewer unique employees than required.",
            infeasible_hints,
        )

    return {
        "aggregates": aggregates,
        "top_10_critical_slots": top_critical,
        "employee_diagnostics": employee_diagnostics,
        "slot_diagnostics_count": len(slot_diagnostics),
    }
