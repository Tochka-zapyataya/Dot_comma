from __future__ import annotations

import json
import logging
import math
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from . import config
from . import main as main_module
from .logging_config import setup_logging


logger = logging.getLogger(__name__)


@contextmanager
def config_overrides(**overrides):
    snapshot = {}
    for k in overrides:
        if hasattr(config, k):
            snapshot[k] = getattr(config, k)
    try:
        for k, v in overrides.items():
            setattr(config, k, v)
        yield
    finally:
        for k, v in snapshot.items():
            setattr(config, k, v)


def extract_actual_forecast(target_dates: list[str], train_csv: Path) -> pd.DataFrame:
    train = pd.read_csv(train_csv)
    train["sale_date"] = pd.to_datetime(train["sale_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    train["sale_hour"] = pd.to_numeric(train["sale_hour"], errors="coerce")
    train["guests_count"] = pd.to_numeric(train["guests_count"], errors="coerce")
    train = train.dropna(subset=["sale_date", "sale_hour", "guests_count"])
    train["sale_hour"] = train["sale_hour"].astype(int)

    target_set = set(target_dates)
    sub = train[
        train["sale_date"].isin(target_set)
        & train["sale_hour"].between(min(config.HOURS), max(config.HOURS))
    ].copy()
    grouped = (
        sub.groupby(["sale_date", "sale_hour"], as_index=False)["guests_count"]
        .sum()
    )
    grouped["guests_count"] = (
        grouped["guests_count"].clip(lower=0).map(math.ceil).astype(int)
    )

    rows = []
    for ds in target_dates:
        for h in config.HOURS:
            rows.append({"sale_date": ds, "sale_hour": int(h)})
    grid = pd.DataFrame(rows)
    out = grid.merge(grouped, on=["sale_date", "sale_hour"], how="left")
    if out["guests_count"].isna().any():
        n_miss = int(out["guests_count"].isna().sum())
        logger.warning(
            "actual forecast: %d (date,hour) slots missing in train.csv; "
            "filled with 0", n_miss,
        )
        out["guests_count"] = out["guests_count"].fillna(0).astype(int)
    return out[["sale_date", "sale_hour", "guests_count"]]


def run_one(label: str, target_dates: list[str], mode: str,
            output_root: Path, holiday_override: dict | None = None) -> dict:
    out_dir = output_root / f"{label}_{mode}"
    out_dir.mkdir(parents=True, exist_ok=True)

    forecast_path = out_dir / "forecast.csv"
    if mode == "actual":
        forecast_df = extract_actual_forecast(target_dates, config.TRAIN_CSV)
        expected = len(target_dates) * len(config.HOURS)
        if len(forecast_df) != expected:
            raise ValueError(
                f"actual forecast for {label} has {len(forecast_df)} rows, expected {expected}"
            )
        forecast_df.to_csv(forecast_path, index=False)
    elif mode == "median":
        if forecast_path.exists():
            forecast_path.unlink()
    else:
        raise ValueError(f"Unknown mode: {mode}")

    overrides = dict(
        TARGET_DATES=list(target_dates),
        OUTPUT_DIR=out_dir,
        FORECAST_CANDIDATES=[forecast_path],
        FALLBACK_FORECAST_PATH=forecast_path,
        FALLBACK_FORECAST_BACKUP=out_dir / "forecast_baseline.csv",
        HOLIDAY_VERSION_OVERRIDE=dict(holiday_override) if holiday_override else {},
    )

    with config_overrides(**overrides):
        try:
            main_module.main()
            run_ok = True
            err_msg = None
        except Exception as exc:
            logger.exception("Pipeline failed for %s/%s: %s", label, mode, exc)
            run_ok = False
            err_msg = repr(exc)

    validation = {}
    diagnostics = {}
    vr_path = out_dir / "validation_report.json"
    diag_path = out_dir / "diagnostics.json"
    if vr_path.exists():
        validation = json.load(open(vr_path))
    if diag_path.exists():
        diagnostics = json.load(open(diag_path))

    return {
        "label": label,
        "mode": mode,
        "out_dir": str(out_dir),
        "run_ok": run_ok,
        "error": err_msg,
        "validation": validation,
        "diagnostics": diagnostics,
        "forecast_path": str(forecast_path) if forecast_path.exists() else None,
    }


def compute_forecast_accuracy(
    median_fc: pd.DataFrame, actual_fc: pd.DataFrame,
) -> dict:
    merged = median_fc.rename(columns={"guests_count": "median"}).merge(
        actual_fc.rename(columns={"guests_count": "actual"}),
        on=["sale_date", "sale_hour"], how="inner",
    )
    if merged.empty:
        return {"error": "no overlapping rows"}
    merged["error"] = merged["median"] - merged["actual"]
    merged["abs_error"] = merged["error"].abs()
    mae = float(merged["abs_error"].mean())
    rmse = float((merged["error"] ** 2).mean() ** 0.5)
    denom = merged["actual"].clip(lower=1)
    mape = float((merged["abs_error"] / denom).mean() * 100)
    return {
        "n_slots": int(len(merged)),
        "MAE": round(mae, 2),
        "RMSE": round(rmse, 2),
        "MAPE_%": round(mape, 2),
        "total_median": int(merged["median"].sum()),
        "total_actual": int(merged["actual"].sum()),
        "bias_total": int(merged["median"].sum() - merged["actual"].sum()),
        "max_underestimate": int(merged["error"].min()),
        "max_overestimate": int(merged["error"].max()),
    }


def summarize(results: list[dict]) -> pd.DataFrame:
    rows = []
    for r in results:
        m = (r.get("validation") or {}).get("metrics") or {}
        si = m.get("solver_info") or {}
        rows.append({
            "label": r["label"],
            "mode": r["mode"],
            "run_ok": r["run_ok"],
            "is_valid": m.get("is_valid"),
            "req_hours": m.get("total_required_hours"),
            "assigned_hours": m.get("total_hours"),
            "shifts": m.get("total_shifts"),
            "exact": m.get("exact_coverage_slots"),
            "over": m.get("overstaffed_slots"),
            "under": m.get("understaffed_slots"),
            "too_much": m.get("too_much_overstaffed_slots"),
            "max_overstaff": m.get("max_overstaffing"),
            "total_overstaff": m.get("total_overstaffing"),
            "total_understaff": si.get("total_understaff") if isinstance(si, dict) else None,
            "cov_slots_%": (m.get("coverage_rate_slots") or 0) * 100,
            "cov_hours_%": (m.get("coverage_rate_hours") or 0) * 100,
            "used_emps": m.get("used_employees"),
            "unused": len(m.get("unused_employees") or []),
            "avg_priority": m.get("average_station_priority"),
            "solver_status": si.get("status") if isinstance(si, dict) else None,
            "solver_mode": m.get("solver_mode"),
            "wall_s": si.get("wall_time_seconds") if isinstance(si, dict) else None,
            "structural_inf": m.get("structural_infeasibility_detected"),
            "error": r.get("error"),
        })
    return pd.DataFrame(rows)


def default_weeks() -> list[tuple[str, list[str], dict | None]]:
    def week(start: str) -> list[str]:
        d0 = pd.to_datetime(start)
        return [(d0 + pd.Timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    return [
        ("past_2026-04-06", week("2026-04-06"), None),
        ("past_2026-04-13", week("2026-04-13"), None),
        ("past_2026-04-20", week("2026-04-20"), None),
        ("target_2026-04-27", week("2026-04-27"), {"2026-05-01": "вых"}),
    ]


def run_backtest(weeks=None, modes=("median", "actual")) -> pd.DataFrame:
    setup_logging()
    output_root = config.OUTPUT_DIR / "backtest"
    output_root.mkdir(parents=True, exist_ok=True)

    weeks = weeks or default_weeks()

    results: list[dict] = []
    forecasts_by_label: dict[str, dict[str, pd.DataFrame]] = {}

    for label, dates, holiday in weeks:
        for mode in modes:
            if mode == "actual" and label.startswith("target_"):
                logger.info("Skipping actual mode for target week (no future data).")
                continue
            logger.info("=" * 70)
            logger.info("BACKTEST: %s | mode=%s", label, mode)
            logger.info("=" * 70)
            r = run_one(label, dates, mode, output_root, holiday)
            results.append(r)
            if r["forecast_path"]:
                fc = pd.read_csv(r["forecast_path"])
                forecasts_by_label.setdefault(label, {})[mode] = fc

    accuracy: dict[str, dict] = {}
    for label, fc_map in forecasts_by_label.items():
        if "median" in fc_map and "actual" in fc_map:
            accuracy[label] = compute_forecast_accuracy(
                fc_map["median"], fc_map["actual"]
            )

    summary = summarize(results)
    summary.to_csv(output_root / "backtest_summary.csv", index=False)
    with open(output_root / "forecast_accuracy.json", "w", encoding="utf-8") as f:
        json.dump(accuracy, f, indent=2, ensure_ascii=False)

    print()
    print("=" * 110)
    print("BACKTEST SUMMARY")
    print("=" * 110)
    cols = [
        "label", "mode", "is_valid", "shifts", "req_hours", "assigned_hours",
        "exact", "over", "under", "too_much",
        "cov_slots_%", "cov_hours_%", "used_emps",
        "avg_priority", "solver_status", "wall_s",
    ]
    print(summary[cols].to_string(index=False))

    print()
    print("=" * 110)
    print("FORECAST ACCURACY (median fallback vs actual ground truth)")
    print("=" * 110)
    for label, m in accuracy.items():
        if "error" in m:
            print(f"  {label}: {m['error']}")
            continue
        print(
            f"  {label}: MAE={m['MAE']:.1f}, RMSE={m['RMSE']:.1f}, "
            f"MAPE={m['MAPE_%']:.1f}% | total median={m['total_median']}, "
            f"actual={m['total_actual']}, bias={m['bias_total']:+d}"
        )

    print()
    print(f"Files: {output_root}/")
    return summary


if __name__ == "__main__":
    run_backtest()
