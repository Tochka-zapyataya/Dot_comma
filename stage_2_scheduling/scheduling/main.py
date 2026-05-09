import logging
import sys

import pandas as pd

from . import config
from .data_loader import load_data
from .exporter import export_all
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

    logger.info("[1/5] Loading data ...")
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

    logger.info("[2/5] Building requirements ...")
    requirements_df = build_requirements(data["forecast"], data["reqlabor"])

    logger.info("[3/5] Building candidates ...")
    candidates_df = build_candidates(data)

    from .cpsat_solver import (
        candidate_ids_from_schedule,
        solve_cpsat_feasibility,
        solve_cpsat_optimize,
    )

    logger.info("[4/5] CP-SAT solve ...")
    feas_schedule, feas_info = solve_cpsat_feasibility(
        requirements_df,
        candidates_df,
        data,
        enforce_all_employees_used=True,
        max_time_seconds=config.MAX_TIME_SECONDS,
    )
    logger.info(
        "Feasibility | status=%s | shifts=%s | %.2fs",
        feas_info.get("status"),
        feas_info.get("final_num_shifts", "—"),
        feas_info.get("wall_time_seconds", 0),
    )

    opt_schedule = None
    opt_info: dict = {
        "status": "SKIPPED_NO_STRICT_FEASIBILITY",
        "phase": "optimize",
        "wall_time_seconds": 0.0,
    }
    if feas_info.get("status") in ("OPTIMAL", "FEASIBLE"):
        hints = candidate_ids_from_schedule(feas_schedule, candidates_df)
        opt_schedule, opt_info = solve_cpsat_optimize(
            requirements_df,
            candidates_df,
            data,
            enforce_all_employees_used=True,
            max_time_seconds=config.MAX_TIME_SECONDS,
            hint_selected_ids=hints,
        )
        logger.info(
            "Optimize | status=%s | obj=%s | shifts=%s | %.2fs",
            opt_info.get("status"),
            opt_info.get("objective_value"),
            opt_info.get("final_num_shifts", "—"),
            opt_info.get("wall_time_seconds", 0),
        )
    else:
        logger.warning(
            "Optimize skipped: feasibility status=%s",
            feas_info.get("status"),
        )

    if opt_schedule is not None and not opt_schedule.empty:
        final_schedule = opt_schedule
        solver_mode = "cpsat_optimize"
    elif feas_schedule is not None and not feas_schedule.empty:
        final_schedule = feas_schedule
        solver_mode = "cpsat_feasibility_only"
        logger.warning("Using feasibility-only schedule (optimize did not converge).")
    else:
        final_schedule = pd.DataFrame(
            columns=["ds", "station_key", "employee_id", "starttime", "finishtime"],
        )
        solver_mode = "none"

    logger.info("[5/5] Validate + Export ...")
    validation = validate_schedule(final_schedule, requirements_df, data)

    metrics = validation["metrics"]
    metrics["solver_mode"] = solver_mode
    metrics["solver_proved_optimal"] = bool(
        solver_mode == "cpsat_optimize" and opt_info.get("status") == "OPTIMAL"
    )

    diag = {
        "solver_mode": solver_mode,
        "feasibility": feas_info,
        "optimize": opt_info,
    }

    export_all(
        schedule_df=final_schedule,
        requirements_df=requirements_df,
        candidates_df=candidates_df,
        validation=validation,
        diagnostics=diag,
        forecast_df=data["forecast"],
        forecast_meta=forecast_meta,
        write_final_schedule_csv_xlsx=bool(validation["is_valid"]),
    )

    _print_summary(validation, solver_mode)
    return 0 if validation["is_valid"] else 1


def _print_summary(validation: dict, solver_mode: str) -> None:
    m = validation["metrics"]
    print("\n" + "=" * 60)
    print(f"  Valid: {validation['is_valid']} | mode: {solver_mode}")
    print(f"  Shifts: {m['total_shifts']} | Hours: {m['total_hours']}")
    print(f"  Coverage: {m['coverage_rate_slots']*100:.1f}% slots | {m['coverage_rate_hours']*100:.1f}% hours")
    print(f"  Errors: {len(validation['errors'])} | Warnings: {len(validation['warnings'])}")
    if validation["errors"]:
        for e in validation["errors"][:3]:
            print(f"    - {e}")
    print(f"  Output: {config.OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
