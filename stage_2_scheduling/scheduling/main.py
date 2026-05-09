from __future__ import annotations

import logging
import sys

from . import config
from .data_loader import load_data
from .diagnostics import run_pre_solve_diagnostics
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

    logger.info("[1/8] Loading data ...")
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

    logger.info("[2/8] Building requirements ...")
    requirements_df = build_requirements(data["forecast"], data["reqlabor"])

    logger.info("[3/8] Building candidates ...")
    candidates_df = build_candidates(data)

    logger.info("[4/8] Pre-solve diagnostics ...")
    diag = run_pre_solve_diagnostics(requirements_df, candidates_df, data)

    from .cpsat_solver import solve_cpsat

    logger.info("[5/8] CP-SAT attempt 1: hard 'all_employees_used' ...")
    schedule_hard, info_hard = solve_cpsat(
        requirements_df, candidates_df, data,
        enforce_all_employees_used=True,
    )

    schedule_soft, info_soft = None, None
    if (schedule_hard is None) or (info_hard.get("total_understaff", 0) > 0):
        logger.info("[5/8] CP-SAT attempt 2: soft 'all_employees_used' ...")
        schedule_soft, info_soft = solve_cpsat(
            requirements_df, candidates_df, data,
            enforce_all_employees_used=False,
        )

    schedule_df, solver_info, solver_mode = _pick_best(
        schedule_hard, info_hard, schedule_soft, info_soft,
    )

    if schedule_df is None or schedule_df.empty:
        logger.warning("CP-SAT infeasible. Falling back to greedy solver.")
        logger.info("[6/8] Greedy fallback ...")
        schedule_df, solver_info = run_greedy(
            requirements_df, candidates_df, data
        )
        solver_mode = "greedy"
    else:
        logger.info("[6/8] Solver finished (no greedy fallback needed).")

    logger.info("[7/8] Validating schedule ...")
    validation = validate_schedule(schedule_df, requirements_df, data)
    validation["metrics"]["solver_mode"] = solver_mode
    validation["metrics"]["solver_info"] = solver_info

    metrics = validation["metrics"]
    is_provably_optimal = (
        solver_mode.startswith("cpsat")
        and solver_info.get("status") == "OPTIMAL"
    )
    metrics["solver_proved_optimal"] = bool(is_provably_optimal)
    metrics["structural_infeasibility_detected"] = bool(
        is_provably_optimal and metrics["understaffed_slots"] > 0
    )
    if metrics["structural_infeasibility_detected"]:
        logger.warning(
            "Structural infeasibility detected: %d understaffed slots remain "
            "even at proven OPTIMAL. The data does not admit a fully covered "
            "schedule under the hard TZ constraints (max 5 working days + "
            "<= req+2 + 1 shift/day + sched windows).",
            metrics["understaffed_slots"],
        )

    diag["solver_info"] = solver_info
    diag["solver_mode"] = solver_mode
    diag["solver_proved_optimal"] = bool(is_provably_optimal)
    diag["structural_infeasibility_detected"] = metrics["structural_infeasibility_detected"]

    logger.info("[8/8] Exporting artifacts ...")
    export_all(
        schedule_df=schedule_df,
        requirements_df=requirements_df,
        candidates_df=candidates_df,
        validation=validation,
        diagnostics=diag,
        forecast_df=data["forecast"],
        forecast_meta=forecast_meta,
    )

    _print_summary(validation, solver_mode, forecast_meta)
    return 0 if validation["is_valid"] else 1


def _pick_best(schedule_hard, info_hard, schedule_soft, info_soft):
    candidates = []
    if schedule_hard is not None and not schedule_hard.empty:
        candidates.append(("cpsat-hard", schedule_hard, info_hard))
    if schedule_soft is not None and not schedule_soft.empty:
        candidates.append(("cpsat-soft", schedule_soft, info_soft))

    if not candidates:
        return None, info_hard or info_soft, "cpsat-failed"

    def score(item):
        _, _, info = item
        understaff = int(info.get("total_understaff", 0))
        overstaff = int(info.get("total_overstaff", 0))
        unused = int(info.get("total_unused_employees", 0))
        return (understaff, unused, overstaff)

    candidates.sort(key=score)
    mode, schedule, info = candidates[0]
    return schedule, info, mode


def _print_summary(validation: dict, solver_mode: str, forecast_meta: dict) -> None:
    metrics = validation["metrics"]
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
    print(f"Schedule:")
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
    print(f"  structural_infeasibility:       {metrics.get('structural_infeasibility_detected')}")
    if validation["errors"]:
        for e in validation["errors"][:5]:
            print(f"    - {e}")
    print()
    print(f"Files written to: {config.OUTPUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    sys.exit(main())
