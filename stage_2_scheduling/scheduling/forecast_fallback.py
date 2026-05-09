import logging
import math
from pathlib import Path

import pandas as pd


logger = logging.getLogger(__name__)


def build_fallback_forecast(
    train_csv_path: Path,
    target_dates: list[str],
    hours: list[int],
    history_weeks: int = 12,
    min_rows: int = 112,
) -> tuple[pd.DataFrame, dict]:
    if not train_csv_path.exists():
        raise FileNotFoundError(
            f"train.csv not found at {train_csv_path}. "
            f"Cannot build fallback forecast."
        )

    train = pd.read_csv(train_csv_path)
    required_cols = {"sale_date", "sale_hour", "guests_count"}
    missing = required_cols - set(train.columns)
    if missing:
        raise ValueError(
            f"train.csv missing required columns: {missing}. "
            f"Got: {list(train.columns)}"
        )

    train["sale_date"] = pd.to_datetime(train["sale_date"], errors="coerce")
    train["sale_hour"] = pd.to_numeric(train["sale_hour"], errors="coerce")
    train["guests_count"] = pd.to_numeric(train["guests_count"], errors="coerce")

    n_before = len(train)
    train = train.dropna(subset=["sale_date", "sale_hour", "guests_count"])
    train = train[train["sale_hour"].between(min(hours), max(hours))]
    train = train[train["guests_count"] >= 0]
    train["sale_hour"] = train["sale_hour"].astype(int)
    train["guests_count"] = train["guests_count"].astype(int)
    n_dropped = n_before - len(train)
    if n_dropped > 0:
        logger.warning(
            "Dropped %d rows from train.csv during cleaning.", n_dropped,
        )

    if train.empty:
        raise ValueError("train.csv contains no valid rows after cleaning.")

    train_max_date = train["sale_date"].max()
    window_start = train_max_date - pd.Timedelta(weeks=history_weeks)
    history = train[train["sale_date"] >= window_start].copy()

    used_full_history = False
    if len(history) < min_rows:
        logger.warning(
            "Last %d weeks have only %d rows (< %d). "
            "Falling back to full train history.",
            history_weeks, len(history), min_rows,
        )
        history = train.copy()
        used_full_history = True
        window_start = history["sale_date"].min()

    history["weekday"] = history["sale_date"].dt.weekday + 1

    profile_wh = (
        history.groupby(["weekday", "sale_hour"])["guests_count"]
        .median()
        .rename("median_wh")
        .reset_index()
    )
    profile_h = (
        history.groupby("sale_hour")["guests_count"]
        .median()
        .rename("median_h")
        .reset_index()
    )
    overall_median = float(history["guests_count"].median())

    rows = []
    for ds in target_dates:
        weekday = pd.to_datetime(ds).weekday() + 1
        for h in hours:
            rows.append({"sale_date": ds, "sale_hour": int(h), "weekday": weekday})
    forecast = pd.DataFrame(rows)

    forecast = forecast.merge(profile_wh, on=["weekday", "sale_hour"], how="left")
    forecast = forecast.merge(profile_h, on=["sale_hour"], how="left")
    forecast["guests_count"] = (
        forecast["median_wh"]
        .fillna(forecast["median_h"])
        .fillna(overall_median)
    )
    forecast["guests_count"] = (
        forecast["guests_count"].clip(lower=0).map(math.ceil).astype(int)
    )

    forecast = forecast[["sale_date", "sale_hour", "guests_count"]].copy()

    expected_rows = len(target_dates) * len(hours)
    if len(forecast) != expected_rows:
        raise RuntimeError(
            f"Fallback forecast has {len(forecast)} rows, expected {expected_rows}."
        )
    if forecast["guests_count"].isna().any():
        raise RuntimeError("Fallback forecast contains NaN values.")

    metadata = {
        "fallback_forecast_used": True,
        "fallback_method": "median_by_weekday_hour_last_12_weeks",
        "train_max_date": train_max_date.strftime("%Y-%m-%d"),
        "history_window_start": window_start.strftime("%Y-%m-%d"),
        "history_window_end": train_max_date.strftime("%Y-%m-%d"),
        "history_weeks_requested": history_weeks,
        "rows_used_for_fallback": int(len(history)),
        "used_full_history_due_to_low_data": used_full_history,
        "overall_median_guests": overall_median,
    }

    logger.info(
        "Built fallback forecast: %d rows | window=%s..%s | n_history=%d",
        len(forecast),
        metadata["history_window_start"],
        metadata["history_window_end"],
        metadata["rows_used_for_fallback"],
    )
    return forecast, metadata


def save_fallback_forecast(
    forecast_df: pd.DataFrame,
    primary_path: Path,
    backup_path: Path,
) -> tuple[Path, Path]:
    primary_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    forecast_df.to_csv(primary_path, index=False)
    forecast_df.to_csv(backup_path, index=False)
    logger.info("Saved fallback forecast: %s and %s", primary_path, backup_path)
    return primary_path, backup_path
