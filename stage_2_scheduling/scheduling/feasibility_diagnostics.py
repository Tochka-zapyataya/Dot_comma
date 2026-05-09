import logging
import time
from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from . import config
from .exporter import _build_employee_summary
from .shift_candidates import build_candidates
from .validator import validate_schedule

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeasDiagParams:
    staffing_upper_extra: int | None
    enforce_one_shift_per_day: bool = True
    weekly_worktime: bool = True
    max_work_days: int | None = 5
    enforce_all_employees_used: bool = True


_DIAG_CAPTURE_SCHEDULE_TESTS = frozenset({
    "no_max_5_days",
    "no_one_shift_per_day",
})


def _extract_schedule_from_selected(
    sel: list[int],
    candidates_df: pd.DataFrame,
) -> pd.DataFrame | None:
    if not sel:
        return None
    cols = ["ds", "station_key", "employee_id", "starttime", "finishtime"]
    sub = candidates_df[candidates_df["candidate_id"].astype(int).isin(sel)]
    if sub.empty:
        return None
    return (
        sub[cols].copy()
        .sort_values(["ds", "station_key", "starttime", "employee_id"])
        .reset_index(drop=True)
    )


def _build_slot_indices(
    candidates_df: pd.DataFrame,
) -> tuple[
    defaultdict[tuple[str, int, str], list[int]],
    defaultdict[tuple[int, str], list[int]],
    defaultdict[int, list[int]],
]:
    cand_covering_slot: dict = defaultdict(list)
    cand_by_emp_day: dict = defaultdict(list)
    cand_by_emp: dict = defaultdict(list)

    for c in candidates_df.itertuples():
        cid = int(c.candidate_id)
        emp = int(c.employee_id)
        ds = str(c.ds)
        cand_by_emp_day[(emp, ds)].append(cid)
        cand_by_emp[emp].append(cid)
        for h in range(int(c.starttime), int(c.finishtime)):
            cand_covering_slot[(ds, int(h), str(c.station_key))].append(cid)
    return cand_covering_slot, cand_by_emp_day, cand_by_emp


def _solve_diagnostic_feasibility(
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    data: dict,
    params: FeasDiagParams,
    max_seconds: float,
    test_label: str,
) -> tuple[dict, pd.DataFrame | None]:
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    cand_ids = candidates_df["candidate_id"].astype(int).tolist()
    duration_by_cid = dict(zip(
        candidates_df["candidate_id"].astype(int),
        candidates_df["duration"].astype(int),
    ))
    cand_covering_slot, cand_by_emp_day, cand_by_emp = _build_slot_indices(
        candidates_df,
    )
    slug = "".join(c if str(c).isalnum() else "_" for c in test_label)[:48]
    x = {cid: model.NewBoolVar(f"d_{slug}_{cid}") for cid in cand_ids}

    employees = sorted(int(e) for e in data["staff_limits"]["employee_id"].tolist())
    unused = {e: model.NewBoolVar(f"d_{slug}_u{e}") for e in employees}

    for r in requirements_df.itertuples():
        key = (str(r.ds), int(r.hour), str(r.station_key))
        req_eff = max(int(r.required_labor), 1)
        covering = cand_covering_slot.get(key, [])
        actual = sum(x[cid] for cid in covering) if covering else 0
        model.Add(actual >= req_eff)
        if params.staffing_upper_extra is not None:
            model.Add(actual <= req_eff + int(params.staffing_upper_extra))

    if params.enforce_one_shift_per_day:
        for (_, _), cids in cand_by_emp_day.items():
            if len(cids) > 1:
                model.Add(sum(x[cid] for cid in cids) <= 1)

    worktime_by_emp = dict(zip(
        data["staff_limits"]["employee_id"].astype(int),
        data["staff_limits"]["worktime_limit"].astype(int),
    ))
    if params.weekly_worktime:
        for emp, cids in cand_by_emp.items():
            model.Add(
                sum(x[cid] * int(duration_by_cid[cid]) for cid in cids)
                <= int(worktime_by_emp[emp]),
            )

    if params.max_work_days is not None:
        cap = int(params.max_work_days)
        for emp, cids in cand_by_emp.items():
            model.Add(sum(x[cid] for cid in cids) <= cap)

    for emp in employees:
        cids = cand_by_emp.get(emp, [])
        if not cids:
            if params.enforce_all_employees_used:
                model.Add(0 == 1)
            else:
                model.Add(unused[emp] == 1)
            continue
        worked = sum(x[cid] for cid in cids)
        if params.enforce_all_employees_used:
            model.Add(worked >= 1)
            model.Add(unused[emp] == 0)
        else:
            model.Add(worked >= 1).OnlyEnforceIf(unused[emp].Not())
            model.Add(worked == 0).OnlyEnforceIf(unused[emp])

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(max_seconds)
    solver.parameters.random_seed = config.RANDOM_SEED
    solver.parameters.num_search_workers = (
        1 if config.DETERMINISTIC else config.NUM_SEARCH_WORKERS
    )
    solver.parameters.log_search_progress = False

    t0 = time.perf_counter()
    status = solver.Solve(model)
    wall_time = round(time.perf_counter() - t0, 2)
    status_name = solver.StatusName(status)

    constraints_relaxed = _constraints_relaxed_sentence(params)

    row: dict = {
        "test_name": test_label,
        "status": status_name,
        "wall_time_seconds": wall_time,
        "constraints_relaxed": constraints_relaxed,
        "number_of_shifts": None,
        "total_overstaff": None,
    }

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return row, None

    sel = [cid for cid, var in x.items() if solver.Value(var) == 1]
    row["number_of_shifts"] = int(len(sel))
    oc = defaultdict(int)
    for cid in sel:
        r = candidates_df[candidates_df["candidate_id"].astype(int) == cid].iloc[0]
        for hh in range(int(r["starttime"]), int(r["finishtime"])):
            oc[(str(r["ds"]), int(hh), str(r["station_key"]))] += 1
    oss = 0
    for r in requirements_df.itertuples():
        key = (str(r.ds), int(r.hour), str(r.station_key))
        req_eff = max(int(r.required_labor), 1)
        act = int(oc.get(key, 0))
        if act > req_eff:
            oss += act - req_eff
    row["total_overstaff"] = int(oss)

    logger.info(
        "Diag %s | %s | shifts=%s | over_sum=%s | %.2fs",
        test_label,
        status_name,
        row["number_of_shifts"],
        row["total_overstaff"],
        wall_time,
    )
    sched_df = _extract_schedule_from_selected(sel, candidates_df)
    return row, sched_df


def _constraints_relaxed_sentence(params: FeasDiagParams) -> list[str]:
    out: list[str] = []
    if params.staffing_upper_extra is None:
        out.append("no_upper_staffing_cap")
    else:
        out.append(f"upper_cap_req_plus_{params.staffing_upper_extra}")
    if not params.enforce_one_shift_per_day:
        out.append("no_one_shift_per_day")
    if not params.weekly_worktime:
        out.append("no_weekly_worktime_limit")
    if params.max_work_days is None:
        out.append("no_max_work_days_cap")
    else:
        out.append(f"max_work_days_cap_{params.max_work_days}")
    if not params.enforce_all_employees_used:
        out.append("not_all_employees_required")
    return out


_TEST_ORDER = (
    "coverage_lower_only",
    "coverage_with_upper_bound",
    "max_work_days_le_5",
    "max_work_days_le_6",
    "max_work_days_le_7",
    "no_max_5_days",
    "no_weekly_worktime_limit",
    "no_one_shift_per_day",
    "allow_more_overstaff_req_plus_3",
    "allow_more_overstaff_req_plus_4",
    "allow_more_overstaff_req_plus_5",
    "shorter_or_all_durations_debug_CP-SAT",
)


_STRICT_UPPER = FeasDiagParams(staffing_upper_extra=2)


def run_feasibility_relaxation_battery(
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    data: dict,
    production_strict_feas_info: dict | None = None,
    max_seconds_per_test: float | None = None,
) -> tuple[list[dict], dict, dict[str, pd.DataFrame]]:
    per_t = (
        float(max_seconds_per_test)
        if max_seconds_per_test is not None
        else float(config.FEAS_RELAXATION_TEST_SECONDS)
    )

    defs: list[tuple[str, FeasDiagParams]] = [
        (
            "coverage_lower_only",
            FeasDiagParams(staffing_upper_extra=None),
        ),
        ("coverage_with_upper_bound", FeasDiagParams(staffing_upper_extra=2)),
        ("max_work_days_le_5", FeasDiagParams(staffing_upper_extra=2, max_work_days=5)),
        ("max_work_days_le_6", FeasDiagParams(staffing_upper_extra=2, max_work_days=6)),
        ("max_work_days_le_7", FeasDiagParams(staffing_upper_extra=2, max_work_days=7)),
        (
            "no_max_5_days",
            FeasDiagParams(staffing_upper_extra=2, max_work_days=None),
        ),
        (
            "no_weekly_worktime_limit",
            FeasDiagParams(staffing_upper_extra=2, weekly_worktime=False),
        ),
        (
            "no_one_shift_per_day",
            FeasDiagParams(staffing_upper_extra=2, enforce_one_shift_per_day=False),
        ),
    ]
    for k in (3, 4, 5):
        defs.append(
            (
                f"allow_more_overstaff_req_plus_{k}",
                FeasDiagParams(staffing_upper_extra=k),
            ),
        )

    rows: list[dict] = []
    debug_schedules: dict[str, pd.DataFrame] = {}
    synth = False
    if production_strict_feas_info is not None:
        synth = True
        cw = {
            "test_name": "coverage_with_upper_bound",
            "status": production_strict_feas_info.get("status"),
            "wall_time_seconds": production_strict_feas_info.get(
                "wall_time_seconds"),
            "constraints_relaxed": _constraints_relaxed_sentence(_STRICT_UPPER),
            "number_of_shifts": production_strict_feas_info.get("final_num_shifts"),
            "total_overstaff": production_strict_feas_info.get(
                "diagnostic_slot_overstaff_sum",
            ),
            "note": "reused_primary_pipeline_solve_same_as_battery_param",
        }
        rows.append(cw)
        rows.append({
            **cw,
            "test_name": "max_work_days_le_5",
            "note": "same_as_strict_coverage_with_upper_max_work_days_5_via_primary",

        })

    for label, parm in defs:
        if synth and label == "coverage_with_upper_bound":
            continue
        if synth and label == "max_work_days_le_5":
            continue
        diag_row, sched_df = _solve_diagnostic_feasibility(
            requirements_df,
            candidates_df,
            data,
            parm,
            per_t,
            label,
        )
        rows.append(diag_row)
        if (
            sched_df is not None
            and not sched_df.empty
            and label in _DIAG_CAPTURE_SCHEDULE_TESTS
        ):
            debug_schedules[label] = sched_df

    durations_csv = sorted(
        int(x) for x in data["shifts"]["shift_duration"].unique().tolist()
    )

    dbg_g = {"durations_in_shifts_csv": durations_csv}

    cand_df_g = candidates_df
    extras = tuple(sorted(set((3, 4, 6)) - set(durations_csv)))

    if not extras:
        dbg_g["skipped"] = "all_requested_debug_durations_already_in_shifts_csv"
        rows.append({
            "test_name": "shorter_or_all_durations_debug_CP-SAT",
            "status": "SKIPPED",
            "wall_time_seconds": None,
            "constraints_relaxed": [
                _constraints_relaxed_sentence(_STRICT_UPPER),
                "hypothetical_extra_durations_not_needed",
            ],
            "number_of_shifts": None,
            "total_overstaff": None,
            **dbg_g,
        })
    else:
        dbg_g["hypothetical_extra_durations"] = list(extras)
        dd = dict(data)
        add_rows = []
        max_pri = int(data["shifts"]["shift_priority"].max())
        for d in extras:
            add_rows.append({
                "shift_duration": int(d),
                "shift_priority": max(4, max_pri),
            })
        dd["shifts"] = pd.concat(
            [
                dd["shifts"].copy(),
                pd.DataFrame(add_rows),
            ],
            ignore_index=True,
        )
        dd["shifts"] = dd["shifts"].drop_duplicates(
            subset=["shift_duration"], keep="first",
        ).sort_values("shift_duration")
        logger.info(
            "Building diagnostic candidates (+durations %s)",
            extras,
        )
        try:
            cand_df_g = build_candidates(dd)
        except Exception as e:
            rows.append({
                "test_name": "shorter_or_all_durations_debug_CP-SAT",
                "status": "CANDIDATE_BUILD_FAILED",
                "wall_time_seconds": None,
                "constraints_relaxed": _constraints_relaxed_sentence(_STRICT_UPPER),
                "error": str(e),
                **dbg_g,
            })
        else:
            sh_row, _ = _solve_diagnostic_feasibility(
                requirements_df,
                cand_df_g,
                data,
                _STRICT_UPPER,
                per_t,
                "shorter_or_all_durations_debug_CP-SAT",
            )
            rows.append(sh_row)
            rows[-1].update(dbg_g)
            rows[-1]["hypothetical_extra_durations"] = list(extras)

    interp = interpret_battery(rows)

    def _sort_key(item: dict) -> tuple[int, str]:
        tn = item["test_name"]
        if tn in _TEST_ORDER:
            return (_TEST_ORDER.index(tn), tn)
        return (999, tn)

    rows.sort(key=_sort_key)

    return rows, {
        **dbg_g,
        "interpretation": interp,
        "max_seconds_each_test_config": per_t,
    }, debug_schedules


def interpret_battery(rows: list[dict]) -> dict:
    idx = {r["test_name"]: r for r in rows}
    a = idx.get("coverage_lower_only")
    b = idx.get("coverage_with_upper_bound")
    out = {}
    def ok(r):
        return r and r.get("status") in ("OPTIMAL", "FEASIBLE")

    out["coverage_lower_feasible"] = ok(a)
    out["strict_upper_feasible"] = ok(b)
    if ok(a) and not ok(b):
        out[
            "main_hypothesis_v2"
        ] = (
            "Верхний предел staffed_per_slot<=req+2 вместе с непрерывными сменами "
            "кандидата сушит допускаемость; см. ниже slot-level анализ."
        )
        out[
            "suggested_followup_v2"
        ] = (
            "Пересмотр жесткости +2, дробление смен или расширение матрицы кандидатов "
            "(вне финала до согласования)."
        )
    elif not ok(a):
        out["main_hypothesis_v2"] = (
            "Даже без верхней границы по слоту модель недопускаема при текущих "
            "кандидатах (доступность, лимит недельных часов, одна смена в день, "
            "макс. 5 рабочих дней, условие что все сотрудники в расписании)."
        )
        out["suggested_followup_v2"] = (
            "Проверить поочередное снятие no_max_5_days, weekly time, shift-per-day; "
            "см. статусы в feasibility_relaxation_tests."
        )
    else:
        out["main_hypothesis_v2"] = "Строгое ограничение покрытием допускается."
    return out


def build_candidate_slot_profiles(
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    cand_covering_slot: defaultdict[tuple[str, int, str], list[int]] | None = None,
) -> list[dict]:
    cand_covering_slot = cand_covering_slot or _build_slot_indices(candidates_df)[0]
    cands_by_id = {
        int(r.candidate_id): r for r in candidates_df.itertuples()
    }

    profiles: list[dict] = []
    for r in requirements_df.itertuples():
        key = (str(r.ds), int(r.hour), str(r.station_key))
        req_eff = max(int(r.required_labor), 1)
        cids = cand_covering_slot.get(key, [])
        emps = {cands_by_id[c].employee_id for c in cids if c in cands_by_id}
        dur_cn: defaultdict[int, int] = defaultdict(int)
        prio_cn: defaultdict[int, int] = defaultdict(int)
        for cid in cids:
            row = cands_by_id[cid]
            dur_cn[int(row.duration)] += 1
            prio_cn[int(row.station_priority)] += 1
        profiles.append({
            "ds": str(r.ds),
            "hour": int(r.hour),
            "station_key": str(r.station_key),
            "required_eff": req_eff,
            "required_plus_2": req_eff + 2,
            "n_covering_candidates": int(len(cids)),
            "n_unique_covering_employees": int(len(emps)),
            "candidates_by_duration": {str(k): v for k, v in sorted(dur_cn.items())},
            "candidates_by_station_priority_class": {
                str(k): v for k, v in sorted(prio_cn.items())
            },
        })
    return profiles


def compute_slot_overstaff_sum_from_occ(
    occ: defaultdict[tuple[str, int, str], int],
    requirements_df: pd.DataFrame,
) -> int:
    oss = 0
    for r in requirements_df.itertuples():
        key = (str(r.ds), int(r.hour), str(r.station_key))
        req_eff = max(int(r.required_labor), 1)
        act = int(occ.get(key, 0))
        if act > req_eff:
            oss += act - req_eff
    return int(oss)


def slot_occ_from_candidate_ids(
    sel_cids: list[int],
    candidates_df: pd.DataFrame,
) -> defaultdict[tuple[str, int, str], int]:
    oc: defaultdict[tuple[str, int, str], int] = defaultdict(int)
    for cid in sel_cids:
        r = candidates_df[candidates_df["candidate_id"].astype(int) == int(cid)].iloc[0]
        for hh in range(int(r["starttime"]), int(r["finishtime"])):
            oc[(str(r["ds"]), int(hh), str(r["station_key"]))] += 1
    return oc


def diagnostic_overstaff_primary_feas_solution(
    schedule_df: pd.DataFrame | None,
    candidates_df: pd.DataFrame,
    requirements_df: pd.DataFrame,
) -> int | None:
    if schedule_df is None or schedule_df.empty:
        return None
    cols = ["ds", "station_key", "employee_id", "starttime", "finishtime"]
    left = schedule_df[cols].copy()
    m = candidates_df[["candidate_id"] + cols].copy()
    for df_ in (left, m):
        df_["ds"] = df_["ds"].astype(str)
        df_["station_key"] = df_["station_key"].astype(str)
        df_["employee_id"] = df_["employee_id"].astype(int)
        df_["starttime"] = df_["starttime"].astype(int)
        df_["finishtime"] = df_["finishtime"].astype(int)
    j = (
        left.merge(m, on=cols, how="inner")
        .sort_values("candidate_id")
        .drop_duplicates(subset=cols, keep="first")
    )
    if j.empty:
        return None
    occ = slot_occ_from_candidate_ids(
        j["candidate_id"].astype(int).tolist(),
        candidates_df,
    )
    return compute_slot_overstaff_sum_from_occ(occ, requirements_df)


def build_day_station_upper_tension_index(
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
) -> list[dict]:
    cand_covering_slot = _build_slot_indices(candidates_df)[0]
    cid_emp = dict(zip(
        candidates_df["candidate_id"].astype(int),
        candidates_df["employee_id"].astype(int),
    ))
    grp: dict[tuple[str, str], list[tuple[int, int, int]]] = defaultdict(list)
    for r in requirements_df.itertuples():
        ds = str(r.ds)
        st = str(r.station_key)
        h = int(r.hour)
        req_eff = max(int(r.required_labor), 1)
        cov = cand_covering_slot.get((ds, h, st), [])
        nu = len({cid_emp[c] for c in cov if c in cid_emp})
        grp[(ds, st)].append((h, req_eff, nu))

    out: list[dict] = []
    for (ds, st), hours in grp.items():
        hours.sort(key=lambda z: z[0])
        reqs = [q for (_, q, _) in hours]
        uniqs = [u for (_, _, u) in hours]
        cumulative = sum(reqs)
        peak = max(reqs)
        bottleneck = min(uniqs)
        slack_vs_upper = bottleneck - peak
        stressed_hours = sum(1 for r in reqs if r >= peak)
        contiguous_high_multi = _longest_run_ge(reqs, 2)
        out.append({
            "ds": ds,
            "station_key": st,
            "total_required_person_hours": int(cumulative),
            "peak_hourly_required": int(peak),
            "min_hourly_unique_employees_available": int(bottleneck),
            "bottleneck_vs_peak_margin": int(slack_vs_upper),
            "hours_at_peak_need": int(stressed_hours),
            "longest_contiguous_hours_req_ge_2": int(contiguous_high_multi),
            "strict_upper_hardness_hint": round(
                float(peak) / max(float(bottleneck), 0.001), 4,
            ),
        })
    out.sort(key=lambda d: (-d["strict_upper_hardness_hint"], -d["peak_hourly_required"]))
    return out[:50]


def _longest_run_ge(arr: list[int], thresh: int) -> int:
    best = cur = 0
    for v in arr:
        if v >= thresh:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _diag_row_ok(row: dict | None) -> bool:
    return row is not None and row.get("status") in ("OPTIMAL", "FEASIBLE")


def export_debug_schedule_pair(
    label: str,
    sched_df: pd.DataFrame,
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    out_dir,
) -> None:
    cols = ["ds", "station_key", "employee_id", "starttime", "finishtime"]
    sd = sched_df[cols].copy()
    sd.to_csv(out_dir / f"schedule_{label}_debug.csv", index=False)
    summ = _build_employee_summary(sd, requirements_df, candidates_df, forecast_df)
    summ.to_csv(out_dir / f"employee_summary_{label}_debug.csv", index=False)


def analyze_no_max_days_debug_solution(
    sched_df: pd.DataFrame | None,
    requirements_df: pd.DataFrame,
    data: dict,
) -> dict:
    if sched_df is None or sched_df.empty:
        return {"error": "no_feasible_debug_schedule_exported"}

    sdf = sched_df.copy()
    sdf["ds"] = sdf["ds"].astype(str)
    sdf["employee_id"] = sdf["employee_id"].astype(int)
    wd = sdf.groupby("employee_id")["ds"].nunique()
    offenders = wd[wd >= 6].sort_values(ascending=False)

    employees_ge_6: list[dict] = []
    for emp_id_int in offenders.index.astype(int).tolist():
        cnt = int(offenders.loc[emp_id_int])
        sub = sdf[sdf["employee_id"] == emp_id_int].sort_values(
            ["ds", "starttime", "station_key"],
        )
        days_sorted = sorted(sub["ds"].unique().tolist())
        stations_days = (
            sub.groupby(["ds", "station_key"]).size().reset_index(name="shifts_here")
            .sort_values(["ds", "station_key"])
            .rename(columns={"ds": "calendar_date"})
            .to_dict(orient="records")
        )
        employees_ge_6.append({
            "employee_id": int(emp_id_int),
            "working_days": cnt,
            "calendar_dates": days_sorted,
            "coverage_by_station_and_day": stations_days,
        })

    full_v = validate_schedule(sdf, requirements_df, data)
    exc_v = validate_schedule(
        sdf, requirements_df, data,
        omit_max_working_days_rule=True,

    )


    offenders_df = offenders.reset_index()
    offenders_df.columns = ["employee_id", "working_days"]

    return {
        "count_employees_working_days_ge_6": int(len(offenders)),
        "count_exactly_6_working_days": int((wd == 6).sum()),
        "count_7_or_more_working_days": int((wd >= 7).sum()),
        "employees_ge_6_days_detail": employees_ge_6,
        "schedule_valid_under_full_validator": bool(full_v["is_valid"]),
        "would_be_valid_except_max_work_days_rule": bool(exc_v["is_valid"]),
        "validation_errors_when_max_work_days_omitted": exc_v["errors"][:50],
        "top_employees_by_working_days": offenders_df.head(40).to_dict(
            orient="records",
        ),
    }


def analyze_no_one_shift_debug_solution(
    sched_df: pd.DataFrame | None,
    requirements_df: pd.DataFrame,
    data: dict,
) -> dict:
    if sched_df is None or sched_df.empty:
        return {"error": "no_feasible_debug_schedule_exported"}

    sdf = sched_df.copy()
    sdf["ds"] = sdf["ds"].astype(str)
    sdf["employee_id"] = sdf["employee_id"].astype(int)
    per_day = sdf.groupby(["employee_id", "ds"]).size()

    breaches = per_day[per_day > 1].sort_values(ascending=False)
    breach_details: list[dict] = []
    for (emp_id, ds_), nsh in breaches.items():

        emp_id_i = int(emp_id)



        ds_s = str(ds_)

        

        row_sub = sdf[(sdf["employee_id"] == emp_id_i) & (sdf["ds"] == ds_s)].sort_values(
            ["starttime", "station_key"],
        )
        breach_details.append({
            "employee_id": emp_id_i,
            "calendar_date": ds_s,
            "shift_count_that_day": int(nsh),

            "shifts_station_and_times": row_sub[["station_key", "starttime", "finishtime"]].to_dict(
                orient="records",
            ),

        })

    full_v = validate_schedule(sdf, requirements_df, data)



    exc_v = validate_schedule(
        sdf, requirements_df, data,
        omit_one_shift_per_day_rule=True,

    )



    return {


        "count_employee_day_pairs_with_multiple_shifts": int(len(breaches)),

        "total_extra_shifts_beyond_first_per_day": int((breaches - 1).sum()),




        "breach_cases_detail": breach_details[:200],
        "schedule_valid_under_full_validator": bool(full_v["is_valid"]),
        "would_be_valid_except_one_shift_per_day_rule": bool(exc_v["is_valid"]),


        "validation_errors_when_one_shift_rule_omitted": exc_v["errors"][:50],
    }




def build_infeasibility_root_cause_summary(
    rows: list[dict],
    analyze_no_max: dict,
    analyze_1shift: dict,
) -> dict:
    indexed: dict[str, dict] = {r["test_name"]: r for r in rows}

    def ok(tn: str) -> bool:
        return _diag_row_ok(indexed.get(tn))

    feas_relaxed_unbounded_days = ok("no_max_5_days")
    feas_relaxed_one_shift = ok("no_one_shift_per_day")

    min_cap_val: int | str | None
    if ok("max_work_days_le_5"):
        min_cap_val = 5
    elif ok("max_work_days_le_6"):
        min_cap_val = 6
    elif ok("max_work_days_le_7"):
        min_cap_val = 7
    elif feas_relaxed_unbounded_days:
        min_cap_val = "unbounded"
    else:
        min_cap_val = None

    top = analyze_no_max.get("top_employees_by_working_days") or []

    curator_ru_parts: list[str] = []
    if feas_relaxed_unbounded_days and not ok("max_work_days_le_5"):
        curator_ru_parts.append(
            "Ограничение «не более 5 рабочих дней в неделю» блокирует допускаемость при "
            "строгих правилах; при диагностическом снятии ограничения по числу рабочих дней "
            "решение находится.",
        )
    if feas_relaxed_one_shift:
        curator_ru_parts.append(
            "Разрешение более одной смены у сотрудника в один календарный день делает задачу "
            "диагностически допустимой (см. schedule_no_one_shift_per_day_debug.csv).",
        )
    if not curator_ru_parts:
        curator_ru_parts.append(
            "Сверьте coverage_lower_only со strict_upper и недельными лимитами; при необходимости "
            "запросите у куратора уточнение по двум выходным, одной смене в день и покрытию.",
        )

    return {
        "strict_max_work_days_5_under_req_plus_2_feasible": ok("max_work_days_le_5"),
        "feasible_if_max_work_days_relaxed_or_removed": feas_relaxed_unbounded_days,
        "minimum_feasible_max_work_days_cap": min_cap_val,
        "feasible_if_one_shift_per_day_relaxed": feas_relaxed_one_shift,
        "top_employees_6_or_more_days_in_relaxed_unbounded_solution": top[:25],
        "debug_relaxed_max_days_analysis": analyze_no_max,
        "debug_relaxed_one_shift_per_day_analysis": analyze_1shift,
        "curator_clarification_recommendation_ru": " ".join(curator_ru_parts),
    }


def run_feasibility_diagnostics_full(
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    data: dict,
    production_strict_feas_info: dict | None,
    feasibility_schedule_primary: pd.DataFrame | None,
) -> dict:
    slot_cov = build_candidate_slot_profiles(
        requirements_df, candidates_df,
    )
    tension = build_day_station_upper_tension_index(
        requirements_df, candidates_df,
    )

    pinfo = dict(production_strict_feas_info or {})
    if feasibility_schedule_primary is not None:
        ovs = diagnostic_overstaff_primary_feas_solution(
            feasibility_schedule_primary,
            candidates_df,
            requirements_df,
        )
        pinfo["diagnostic_slot_overstaff_sum"] = ovs

    tests, dbg, dbg_schedules = run_feasibility_relaxation_battery(
        requirements_df,
        candidates_df,
        data,
        production_strict_feas_info=pinfo,
    )

    out_dir = config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    exported_debug: dict[str, str | None] = {}
    for lbl in ("no_max_5_days", "no_one_shift_per_day"):
        sd = dbg_schedules.get(lbl)
        if sd is not None and not sd.empty:
            export_debug_schedule_pair(
                lbl, sd, requirements_df, candidates_df, forecast_df, out_dir,
            )
            exported_debug[f"schedule_{lbl}_debug.csv"] = str(
                (out_dir / f"schedule_{lbl}_debug.csv").resolve(),
            )
            exported_debug[f"employee_summary_{lbl}_debug.csv"] = str(
                (out_dir / f"employee_summary_{lbl}_debug.csv").resolve(),
            )
        else:
            exported_debug[f"schedule_{lbl}_debug.csv"] = None
            exported_debug[f"employee_summary_{lbl}_debug.csv"] = None

    analyze_no_max = analyze_no_max_days_debug_solution(
        dbg_schedules.get("no_max_5_days"),
        requirements_df,
        data,
    )
    analyze_oshift = analyze_no_one_shift_debug_solution(
        dbg_schedules.get("no_one_shift_per_day"),
        requirements_df,
        data,
    )
    dbg["debug_relaxed_schedule_exports"] = exported_debug

    root_cause = build_infeasibility_root_cause_summary(
        tests, analyze_no_max, analyze_oshift,
    )

    return {
        "feasibility_relaxation_tests": tests,
        "feasibility_relaxation_meta": dbg,
        "candidate_slot_profiles": slot_cov,
        "day_station_upper_tension_ranked_top50": tension,
        "hypothesis_and_followup_hint": dbg.get("interpretation", {}),
        "infeasibility_root_cause_summary": root_cause,
    }
