import logging
import sys

import pandas as pd

from . import config
from .data_loader import load_data
from .diagnostics import (
    run_post_solve_infeasibility_diagnostics,
    run_pre_solve_diagnostics,
)
from .exporter import export_all
from .greedy_solver import run_greedy
from .logging_config import setup_logging
from .requirements_builder import build_requirements
from .shift_candidates import build_candidates
from .validator import validate_schedule


def main() -> int:
    setup_logging()
    logger = logging.getLogger("scheduling.main")

    logger.info("=" * 70)
    logger.info("STAGE 2: SCHEDULE OPTIMIZER")
    logger.info("=" * 70)

    logger.info("[1/9] Loading data ...")
    data = load_data()
    forecast_meta = data.pop("forecast_meta")
    if forecast_meta.get("fallback_forecast_used"):
        logger.warning(
            "Using FALLBACK forecast | method=%s | window=%s..%s",
            forecast_meta.get("fallback_method"),
            forecast_meta.get("history_window_start"),
            forecast_meta.get("history_window_end"),
        )
    else:
        logger.info("Using production forecast from %s", forecast_meta.get("source"))

    logger.info("[2/9] Building requirements ...")
    requirements_df = build_requirements(data["forecast"], data["reqlabor"])

    logger.info("[3/9] Building candidates ...")
    candidates_df = build_candidates(data)

    logger.info("[4/9] Pre-solve diagnostics ...")
    diag = run_pre_solve_diagnostics(requirements_df, candidates_df, data)

    from .cpsat_solver import (
        candidate_ids_from_schedule,
        solve_cpsat_feasibility,
        solve_cpsat_feasibility_diagnostic_relaxed,
        solve_cpsat_optimize,
    )

    logger.info(
        "[5/9] CP-SAT feasibility-only (все ограничения, без цели минимизации) ...",
    )
    feas_schedule, feas_info = solve_cpsat_feasibility(
        requirements_df,
        candidates_df,
        data,
        enforce_all_employees_used=True,
        max_time_seconds=config.MAX_TIME_SECONDS,
    )
    logger.info(
        "Фаза feasibility | status=%s | shifts=%s | %.2fs",
        feas_info.get("status"),
        feas_info.get("final_num_shifts")
        if "final_num_shifts" in feas_info
        else "—",
        feas_info.get("wall_time_seconds", 0),
    )

    logger.info(
        "[5a/9] Диагностика батареи feasibility (поэтапное ослабление) и "
        "слот-профили …",
    )
    from .feasibility_diagnostics import run_feasibility_diagnostics_full

    diag.update(run_feasibility_diagnostics_full(
        requirements_df,
        candidates_df,
        data["forecast"],
        data,
        feas_info,
        feas_schedule if feas_info.get("status") in ("OPTIMAL", "FEASIBLE") else None,
    ))

    relaxed_info = None
    if feas_info.get("status") not in ("OPTIMAL", "FEASIBLE"):
        logger.info(
            "[5b/9] Диагностика: feasibility без ограничения «все в смене» "
            "| max_time=%ss",
            config.RELAXED_FEASIBILITY_DIAGNOSTIC_SECONDS,
        )
        _, relaxed_info = solve_cpsat_feasibility_diagnostic_relaxed(
            requirements_df,
            candidates_df,
            data,
            max_time_seconds=config.RELAXED_FEASIBILITY_DIAGNOSTIC_SECONDS,
        )
        logger.info(
            "Сравнение: relaxed feasibility status=%s (strict был %s)",
            relaxed_info.get("status"),
            feas_info.get("status"),
        )

    hints = candidate_ids_from_schedule(feas_schedule, candidates_df)

    opt_schedule = None
    opt_info: dict = {
        "status": "SKIPPED_NO_STRICT_FEASIBILITY",
        "phase": "optimize",
        "wall_time_seconds": 0.0,
        "enforce_all_employees_used": True,
    }
    if feas_info.get("status") in ("OPTIMAL", "FEASIBLE"):
        logger.info("[6/9] CP-SAT optimization (hints из feasibility) ...")
        opt_schedule, opt_info = solve_cpsat_optimize(
            requirements_df,
            candidates_df,
            data,
            enforce_all_employees_used=True,
            max_time_seconds=config.MAX_TIME_SECONDS,
            hint_selected_ids=hints,
        )
        logger.info(
            "Фаза optimize | status=%s | obj=%s | shifts=%s | %.2fs",
            opt_info.get("status"),
            opt_info.get("objective_value"),
            opt_info.get("final_num_shifts") if opt_schedule is not None else "—",
            opt_info.get("wall_time_seconds", 0),
        )
    else:
        logger.warning(
            "[6/9] Optimize пропуск: строгая feasibility недостигнута (status=%s).",
            feas_info.get("status"),
        )

    cpsat_schedule: pd.DataFrame | None = None
    solver_mode = "none"

    if opt_schedule is not None and not opt_schedule.empty:
        cpsat_schedule = opt_schedule
        solver_mode = "cpsat_optimize"
    elif feas_schedule is not None and not feas_schedule.empty:
        cpsat_schedule = feas_schedule
        solver_mode = "cpsat_feasibility_only"
        logger.warning(
            "Optimize не нашёл решение при status=%s; используется расписание "
            "feasibility-only.",
            opt_info.get("status"),
        )

    if cpsat_schedule is None:
        blank = pd.DataFrame(
            columns=["ds", "station_key", "employee_id", "starttime", "finishtime"],
        )
        cpsat_schedule = blank

    logger.info("[7/9] Validation (расписание CP-SAT) ...")
    validation = validate_schedule(cpsat_schedule, requirements_df, data)

    greedy_debug_schedule: pd.DataFrame | None = None
    if config.ALLOW_GREEDY_FALLBACK and (not validation["is_valid"]):
        logger.info(
            "[7b/9] Greedy fallback (режим диагностики, не финальная подача)",
        )
        greedy_debug_schedule, _gi = run_greedy(
            requirements_df, candidates_df, data,
        )
        gv = validate_schedule(
            greedy_debug_schedule,
            requirements_df,
            data,
        )
        diag["greedy_debug_validation"] = {
            "is_valid": gv["is_valid"],
            "errors_count": len(gv["errors"]),
            "sample_errors": gv["errors"][:5],
        }
    elif (not validation["is_valid"]) and not config.ALLOW_GREEDY_FALLBACK:
        logger.info(
            "Greedy fallback отключён (ALLOW_GREEDY_FALLBACK=False); отладочное "
            "расписание не строится.",
        )

    diag["solver_phases"] = run_post_solve_infeasibility_diagnostics(
        requirements_df,
        candidates_df,
        data,
        feas_info,
        opt_info,
        relaxed_info,
    )

    solver_info_bundle = {
        "feasibility": feas_info,
        "optimize": opt_info,
        "relaxed_feasibility_optional": relaxed_info,
        "solver_mode_selected": solver_mode,
        "export_final_schedule_artifacts": bool(validation["is_valid"]),
        "chosen_from_optimize": solver_mode == "cpsat_optimize",
    }

    metrics = validation["metrics"]
    metrics["solver_mode"] = solver_mode
    metrics["solver_info"] = solver_info_bundle
    metrics["solver_proved_optimal"] = bool(
        solver_mode == "cpsat_optimize"
        and opt_info.get("status") == "OPTIMAL",
    )
    metrics["structural_infeasibility_detected"] = False

    diag["solver_info"] = solver_info_bundle
    diag["solver_mode"] = solver_mode
    diag["solver_proved_optimal"] = bool(metrics["solver_proved_optimal"])

    logger.info("[8/9] Export ...")
    export_all(
        schedule_df=cpsat_schedule,
        requirements_df=requirements_df,
        candidates_df=candidates_df,
        validation=validation,
        diagnostics=diag,
        forecast_df=data["forecast"],
        forecast_meta=forecast_meta,
        write_final_schedule_csv_xlsx=bool(validation["is_valid"]),
        debug_greedy_schedule_df=(
            greedy_debug_schedule if greedy_debug_schedule is not None else None
        ),
    )

    sch_path = (config.OUTPUT_DIR / "schedule.xlsx").resolve()
    _print_summary(
        validation,
        solver_mode,
        forecast_meta,
        str(sch_path) if validation["is_valid"] else None,
        len(greedy_debug_schedule) if greedy_debug_schedule is not None else 0,
    )
    return 0 if validation["is_valid"] else 1


def _print_summary(
    validation: dict,
    solver_mode: str,
    forecast_meta: dict,
    valid_schedule_xlsx_abs: str | None,
    greedy_debug_shift_count: int,
) -> None:
    metrics = validation["metrics"]
    print()
    print("=" * 70)
    print(" ФИНАЛЬНЫЙ СТАТУС")
    print("=" * 70)
    print(f"FINAL VALID SCHEDULE FOUND: {'YES' if validation['is_valid'] else 'NO'}")
    print(f"Solver mode (CP-SAT path):           {solver_mode}")
    print(f"Validation errors:                  {len(validation['errors'])}")
    if validation["is_valid"]:
        print(f"Final schedule.xlsx path:           {valid_schedule_xlsx_abs}")
        print("(Дополнительно — SUMMARY блок ниже)")
    else:
        print("Final schedule.xlsx:                не создан (решение CP-SAT невалидно)")
        if greedy_debug_shift_count > 0:
            print(f"Greedy DEBUG shifts (не финал):      {greedy_debug_shift_count} "
                  f"| см. schedule_greedy_fallback.*")
        print("\nПричины невалидности см. validation_report.json")
    print("=" * 70)
    print()
    print("=" * 70)
    print("  SCHEDULING PIPELINE — SUMMARY")
    print("=" * 70)
    if forecast_meta.get("fallback_forecast_used"):
        print(f"Forecast source:       FALLBACK ({forecast_meta.get('fallback_method')})")
        print(f"  window:              {forecast_meta.get('history_window_start')} .. "
              f"{forecast_meta.get('history_window_end')}")
        print(f"  rows:                {forecast_meta.get('rows_used_for_fallback')}")
    else:
        print(f"Forecast source:       {forecast_meta.get('source')}")
    print(f"Solver mode:           {solver_mode}")
    print()
    print(f"Schedule (CP-SAT selection):")
    print(f"  Total shifts:        {metrics['total_shifts']}")
    print(f"  Total hours:         {metrics['total_hours']}")
    print(f"  Used employees:      {metrics['used_employees']}")
    print(f"  Unused employees:    {len(metrics['unused_employees'])} "
          f"{metrics['unused_employees'][:10]}")
    print()
    print(f"Coverage:")
    print(f"  Slots (total):       {metrics['exact_coverage_slots'] + metrics['overstaffed_slots'] + metrics['understaffed_slots'] + metrics['too_much_overstaffed_slots']}")
    print(f"  Exact (=required):   {metrics['exact_coverage_slots']}")
    print(f"  Overstaffed (+1..2): {metrics['overstaffed_slots']}")
    print(f"  Understaffed:        {metrics['understaffed_slots']}")
    print(f"  Too much (>+2):      {metrics['too_much_overstaffed_slots']}")
    print(f"  Max overstaff:       {metrics['max_overstaffing']}")
    print(f"  Total overstaff hrs: {metrics['total_overstaffing']}")
    print(f"  Coverage rate slots: {metrics['coverage_rate_slots']*100:.2f}%")
    print(f"  Coverage rate hours: {metrics['coverage_rate_hours']*100:.2f}%")
    print()
    print(f"Quality:")
    print(f"  Avg station_priority: {metrics['average_station_priority']}")
    print(f"  Shift durations:      {metrics['shift_duration_distribution']}")
    print()
    print(f"Validation:")
    print(f"  is_valid:                       {validation['is_valid']}")
    print(f"  errors:                         {len(validation['errors'])}")
    print(f"  warnings:                       {len(validation['warnings'])}")
    print(f"  solver_proved_optimal:          {metrics.get('solver_proved_optimal')}")
    if validation["errors"]:
        for e in validation["errors"][:5]:
            print(f"    - {e}")
    print()
    print(f"Output directory:                  {config.OUTPUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    sys.exit(main())
