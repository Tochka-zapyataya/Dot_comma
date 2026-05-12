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

MIN_REST_DAYS_PER_EMPLOYEE = 2
MAX_WORKING_DAYS_PER_EMPLOYEE = max(
    0, len(TARGET_DATES) - MIN_REST_DAYS_PER_EMPLOYEE
)

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

FORECAST_GUESTS_SCALE = 1

FALLBACK_HISTORY_WEEKS = 12
FALLBACK_MIN_ROWS = 7 * 16
FALLBACK_METHOD_NAME = "median_by_weekday_hour_last_12_weeks"

STATION_PRIORITY_WEIGHT = 1_000
OVERSTAFF_WEIGHT = 600
SHIFT_PRIORITY_WEIGHT = 40
SHIFT_COUNT_WEIGHT = 150
HOUR_BALANCE_WEIGHT = 4

GREEDY_DURATION_BIAS = 2


FILTER_DOMINATED_PRIO4_STATION_CANDIDATES = False

MAX_TIME_SECONDS = 900
UNUSED_EMPLOYEE_SOFT_WEIGHT = 25_000

RANDOM_SEED = 42
NUM_SEARCH_WORKERS = 8

DETERMINISTIC = False

ALLOW_RELAX_UNUSED_EMPLOYEES_RETRY = False

LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
