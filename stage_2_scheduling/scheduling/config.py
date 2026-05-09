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
    "2026-04-06",
    "2026-04-07",
    "2026-04-08",
    "2026-04-09",
    "2026-04-10",
    "2026-04-11",
    "2026-04-12",
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

# Множитель для значений guests_count из прогноза.
# Применяется в requirements_builder перед маппингом гостей в reqlabor.
# 1.0 = прогноз без изменений; 0.8 = на 20% меньше гостей.
FORECAST_GUESTS_SCALE = 0.8

FALLBACK_HISTORY_WEEKS = 12
FALLBACK_MIN_ROWS = 7 * 16
FALLBACK_METHOD_NAME = "median_by_weekday_hour_last_12_weeks"

STATION_PRIORITY_WEIGHT = 1_000
OVERSTAFF_WEIGHT = 600
SHIFT_PRIORITY_WEIGHT = 40
SHIFT_COUNT_WEIGHT = 150
HOUR_BALANCE_WEIGHT = 4

GREEDY_DURATION_BIAS = 2

ALLOW_GREEDY_FALLBACK = False

RELAXED_FEASIBILITY_DIAGNOSTIC_SECONDS = 120

FEAS_RELAXATION_TEST_SECONDS = 60

MAX_TIME_SECONDS = 300
RANDOM_SEED = 42
NUM_SEARCH_WORKERS = max(1, os.cpu_count() or 1)
DETERMINISTIC = False

LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
