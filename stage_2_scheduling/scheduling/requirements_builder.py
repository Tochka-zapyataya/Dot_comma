import logging

import pandas as pd

from . import config


logger = logging.getLogger(__name__)


def build_requirements(
    forecast_df: pd.DataFrame,
    reqlabor_df: pd.DataFrame,
) -> pd.DataFrame:
    scale = float(getattr(config, "FORECAST_GUESTS_SCALE", 1.0))
    forecast_lookup = {
        (str(r.sale_date), int(r.sale_hour)): max(
            int(round(int(r.guests_count) * scale)), 0
        )
        for r in forecast_df.itertuples()
    }
    if scale != 1.0:
        logger.info(
            "Applied FORECAST_GUESTS_SCALE=%.3f to forecast guests_count.", scale,
        )

    rows = []
    n_above_max = 0
    for ds in config.TARGET_DATES:
        weekday = pd.to_datetime(ds).weekday() + 1
        for hour in config.HOURS:
            guests = forecast_lookup[(ds, hour)]
            day_type_default = "будни" if weekday <= 5 else "вых"
            day_type = config.HOLIDAY_VERSION_OVERRIDE.get(ds, day_type_default)
            menu_type = "утр." if hour < 10 else "осн."
            version = f"{day_type}/{menu_type}"

            for station in config.STATIONS:
                req, above_max = _lookup_reqlabor(
                    reqlabor_df, station, version, guests
                )
                if above_max:
                    n_above_max += 1
                req_eff = max(int(req), 1)
                rows.append({
                    "ds": ds,
                    "hour": int(hour),
                    "station_key": station,
                    "required_labor": req_eff,
                    "raw_reqlabor": int(req),
                    "guests_count": int(guests),
                    "version": version,
                    "weekday": int(weekday),
                })

    df = pd.DataFrame(rows)
    expected = len(config.TARGET_DATES) * len(config.HOURS) * len(config.STATIONS)
    if len(df) != expected:
        raise RuntimeError(f"requirements has {len(df)} rows, expected {expected}")

    if n_above_max > 0:
        logger.warning(
            "%d slots had guests_count above max threshold; "
            "used max reqlabor for those.", n_above_max,
        )
    logger.info(
        "Built requirements: %d rows | total person-hours required >= %d",
        len(df), int(df["required_labor"].sum()),
    )
    return df


def _lookup_reqlabor(
    reqlabor_df: pd.DataFrame,
    station: str,
    version: str,
    guests: int,
) -> tuple[int, bool]:
    sub = reqlabor_df[
        (reqlabor_df["station_key"] == station)
        & (reqlabor_df["version"] == version)
    ].sort_values("guests_count")
    if sub.empty:
        raise ValueError(
            f"No reqlabor entries for station={station}, version={version}"
        )

    matches = sub[sub["guests_count"] >= guests]
    if not matches.empty:
        return int(matches.iloc[0]["reqlabor"]), False

    return int(sub.iloc[-1]["reqlabor"]), True
