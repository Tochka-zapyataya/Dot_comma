import logging
from pathlib import Path

import pandas as pd

from . import config
from .forecast_fallback import build_fallback_forecast, save_fallback_forecast


logger = logging.getLogger(__name__)


def load_data() -> dict:
    data: dict = {}
    data["reqlabor"] = _load_reqlabor(config.REQLABOR_CSV)
    data["sched"] = _load_sched(config.SCHED_CSV)
    data["station_priorities"] = _load_station_priorities(config.STATION_PRIORITIES_CSV)
    data["shifts"] = _load_shifts(config.SHIFTS_CSV)
    data["staff_limits"] = _load_staff_limits(config.STAFF_LIMITS_CSV)

    forecast_df, forecast_meta = _load_or_build_forecast()
    data["forecast"] = forecast_df
    data["forecast_meta"] = forecast_meta

    _cross_validate_consistency(data)
    return data


def _load_reqlabor(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"station_key", "version", "guests_count", "reqlabor"}
    _check_required_columns(df, required, path)
    df["guests_count"] = df["guests_count"].astype(int)
    df["reqlabor"] = df["reqlabor"].astype(int)
    df["station_key"] = df["station_key"].astype(str)
    df["version"] = df["version"].astype(str)
    logger.info("Loaded reqlabor: %d rows", len(df))
    return df


def _load_sched(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"employee_id", "day", "starttime", "finishtime"}
    _check_required_columns(df, required, path)
    df = df.astype({
        "employee_id": int,
        "day": int,
        "starttime": int,
        "finishtime": int,
    })

    n_clipped_high = int((df["finishtime"] > config.CLOSE_HOUR).sum())
    n_clipped_low = int((df["starttime"] < config.OPEN_HOUR).sum())
    df["finishtime"] = df["finishtime"].clip(upper=config.CLOSE_HOUR)
    df["starttime"] = df["starttime"].clip(lower=config.OPEN_HOUR)
    if n_clipped_high or n_clipped_low:
        logger.warning(
            "Normalized sched windows: %d finishtime>%d, %d starttime<%d",
            n_clipped_high, config.CLOSE_HOUR, n_clipped_low, config.OPEN_HOUR,
        )

    n_before = len(df)
    df = df[(df["finishtime"] - df["starttime"]) >= 3].reset_index(drop=True)
    if (n_before - len(df)) > 0:
        logger.warning(
            "Dropped %d sched rows with window < 3 hours",
            n_before - len(df),
        )

    if not df["day"].between(1, 7).all():
        raise ValueError(
            f"sched.csv contains invalid day values "
            f"(must be 1..7): {sorted(df['day'].unique())}"
        )
    logger.info("Loaded sched: %d rows after normalization", len(df))
    return df


def _load_station_priorities(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"employee_id", "station_key", "station_priority"}
    _check_required_columns(df, required, path)
    df = df.astype({"employee_id": int, "station_priority": int})
    df["station_key"] = df["station_key"].astype(str)
    if not df["station_priority"].between(1, 4).all():
        raise ValueError("station_priority must be in 1..4")
    logger.info("Loaded station_priorities: %d rows", len(df))
    return df


def _load_shifts(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"shift_duration", "shift_priority"}
    _check_required_columns(df, required, path)
    df = df.astype({"shift_duration": int, "shift_priority": int})
    if not df["shift_duration"].between(1, 24).all():
        raise ValueError("shift_duration out of valid range")
    logger.info("Loaded shifts: %d rows | durations=%s",
                len(df), sorted(df["shift_duration"].tolist()))
    return df


def _load_staff_limits(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"employee_id", "worktime_limit", "shift_limit"}
    _check_required_columns(df, required, path)
    df = df.astype({
        "employee_id": int,
        "worktime_limit": int,
        "shift_limit": int,
    })
    if (df["shift_limit"] <= 0).any():
        raise ValueError("shift_limit must be positive")
    if (df["worktime_limit"] <= 0).any():
        raise ValueError("worktime_limit must be positive")
    logger.info("Loaded staff_limits: %d employees", len(df))
    return df


def _load_or_build_forecast() -> tuple[pd.DataFrame, dict]:
    for path in config.FORECAST_CANDIDATES:
        if path.exists():
            logger.info("Loading forecast from %s", path)
            if path.suffix == ".xlsx":
                df = pd.read_excel(path)
            else:
                df = pd.read_csv(path)
            df = _normalize_forecast(df)
            validate_forecast(df)
            meta = {
                "fallback_forecast_used": False,
                "source": str(path.relative_to(config.WORKSPACE_ROOT)),
            }
            return df, meta

    logger.warning(
        "Final forecast file not found. "
        "Building fallback baseline forecast from train.csv "
        "using median by weekday+hour over the last %d weeks.",
        config.FALLBACK_HISTORY_WEEKS,
    )
    forecast_df, meta = build_fallback_forecast(
        train_csv_path=config.TRAIN_CSV,
        target_dates=config.TARGET_DATES,
        hours=config.HOURS,
        history_weeks=config.FALLBACK_HISTORY_WEEKS,
        min_rows=config.FALLBACK_MIN_ROWS,
    )
    save_fallback_forecast(
        forecast_df,
        primary_path=config.FALLBACK_FORECAST_PATH,
        backup_path=config.FALLBACK_FORECAST_BACKUP,
    )
    forecast_df = _normalize_forecast(forecast_df)
    validate_forecast(forecast_df)
    return forecast_df, meta


def _normalize_forecast(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["sale_date"] = pd.to_datetime(df["sale_date"]).dt.strftime("%Y-%m-%d")
    df["sale_hour"] = df["sale_hour"].astype(int)
    df["guests_count"] = df["guests_count"].astype(int)
    df = df[["sale_date", "sale_hour", "guests_count"]].sort_values(
        ["sale_date", "sale_hour"]
    ).reset_index(drop=True)
    return df


def validate_forecast(df: pd.DataFrame) -> None:
    required = {"sale_date", "sale_hour", "guests_count"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"forecast missing columns: {missing}")

    expected_dates = set(config.TARGET_DATES)
    actual_dates = set(df["sale_date"].astype(str).unique().tolist())
    if expected_dates != actual_dates:
        raise ValueError(
            f"forecast dates mismatch:\n"
            f"  missing: {sorted(expected_dates - actual_dates)}\n"
            f"  extra:   {sorted(actual_dates - expected_dates)}"
        )

    extra_hours = set(df["sale_hour"].unique()) - set(config.HOURS)
    if extra_hours:
        raise ValueError(f"forecast contains hours outside {config.HOURS}: {extra_hours}")

    if df.duplicated(subset=["sale_date", "sale_hour"]).any():
        raise ValueError("forecast contains duplicate (sale_date, sale_hour) rows")

    if (df["guests_count"] < 0).any():
        raise ValueError("forecast contains negative guests_count")

    expected_rows = len(config.TARGET_DATES) * len(config.HOURS)
    if len(df) != expected_rows:
        raise ValueError(
            f"forecast has {len(df)} rows, expected {expected_rows}"
        )


def _check_required_columns(df: pd.DataFrame, required: set[str], path: Path) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} missing required columns: {missing}")


def _cross_validate_consistency(data: dict) -> None:
    staff_emps = set(data["staff_limits"]["employee_id"].tolist())
    sched_emps = set(data["sched"]["employee_id"].tolist())
    prio_emps = set(data["station_priorities"]["employee_id"].tolist())

    extra_in_sched = sched_emps - staff_emps
    if extra_in_sched:
        raise ValueError(
            f"sched.csv has employees not in staff_limits: {sorted(extra_in_sched)}"
        )
    extra_in_prio = prio_emps - staff_emps
    if extra_in_prio:
        raise ValueError(
            f"station_priorities.csv has employees not in staff_limits: "
            f"{sorted(extra_in_prio)}"
        )

    versions_required = {"будни/осн.", "будни/утр.", "вых/осн.", "вых/утр."}
    versions_actual = set(data["reqlabor"]["version"].unique())
    if not versions_required.issubset(versions_actual):
        raise ValueError(
            f"reqlabor.csv missing versions: "
            f"{sorted(versions_required - versions_actual)}"
        )

    stations_required = set(config.STATIONS)
    for version in versions_required:
        sub = data["reqlabor"][data["reqlabor"]["version"] == version]
        stations_in_v = set(sub["station_key"].unique())
        missing = stations_required - stations_in_v
        if missing:
            raise ValueError(
                f"reqlabor.csv missing stations {missing} for version={version}"
            )
