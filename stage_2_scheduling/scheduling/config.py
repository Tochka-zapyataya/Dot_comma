from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent

EXTERNAL_DATA_DIR = WORKSPACE_ROOT / "data_tech_and_point"
LOCAL_DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

TRAIN_CSV = EXTERNAL_DATA_DIR / "train.csv"
REQLABOR_CSV = EXTERNAL_DATA_DIR / "reqlabor.csv"
SCHED_CSV = EXTERNAL_DATA_DIR / "sched.csv"
STATION_PRIORITIES_CSV = EXTERNAL_DATA_DIR / "station_priorities.csv"
SHIFTS_CSV = EXTERNAL_DATA_DIR / "shifts.csv"
STAFF_LIMITS_CSV = EXTERNAL_DATA_DIR / "staff_limits.csv"

FORECAST_CANDIDATES = [
    EXTERNAL_DATA_DIR / "forecast.csv",
    EXTERNAL_DATA_DIR / "forecast.xlsx",
    LOCAL_DATA_DIR / "forecast.csv",
    LOCAL_DATA_DIR / "forecast.xlsx",
]

FALLBACK_FORECAST_PATH = LOCAL_DATA_DIR / "forecast.csv"
FALLBACK_FORECAST_BACKUP = OUTPUT_DIR / "forecast_baseline.csv"

TARGET_DATES: list[str] = [
    "2026-04-27",
    "2026-04-28",
    "2026-04-29",
    "2026-04-30",
    "2026-05-01",
    "2026-05-02",
    "2026-05-03",
]
OPEN_HOUR = 7
CLOSE_HOUR = 23
HOURS: list[int] = list(range(OPEN_HOUR, CLOSE_HOUR))
STATIONS: list[str] = ["BVR", "C", "FF", "K", "TS"]

STATION_NAMES = {
    "BVR": "Напитки",
    "C": "Прилавок",
    "FF": "Картофель",
    "K": "Кухня",
    "TS": "Зал",
}

HOLIDAY_VERSION_OVERRIDE: dict[str, str] = {
    "2026-05-01": "вых",
}

FALLBACK_HISTORY_WEEKS = 12
FALLBACK_MIN_ROWS = 7 * 16
FALLBACK_METHOD_NAME = "median_by_weekday_hour_last_12_weeks"

UNDERSTAFF_PENALTY = 1_000_000
OVERSTAFF_PENALTY = 10_000
UNUSED_EMPLOYEE_PENALTY = 5_000
STATION_PRIORITY_WEIGHT = 100
SHIFT_DURATION_WEIGHT = 100
DURATION_REWARD_WEIGHT = 1

SHIFT_DURATION_PENALTY: dict[int, int] = {
    9: 0,
    8: 0,
    7: 0,
    6: 50,
    5: 80,
    4: 30,
    3: 60,
}

MAX_TIME_SECONDS = 300
RANDOM_SEED = 42
NUM_SEARCH_WORKERS = max(1, os.cpu_count() or 1)
DETERMINISTIC = False

LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
