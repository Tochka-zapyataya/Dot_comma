"""
compare_v12.py
--------------
Runs v11 and v12 on the SAME 7-day hold-out (2026-04-20 – 2026-04-26)
and reports WAPE for each.  Run from the stage_1_forecast/ directory.
"""

import warnings
warnings.filterwarnings("ignore")

import os
import sys

# Ensure we run from the forecast directory so ./data/ paths resolve
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

import numpy as np
import pandas as pd

import forecast_v11 as v11
import forecast_v12 as v12

# ─── shared config ───────────────────────────────────────────
DATA_FILE     = "./data/train.csv"
CUT_DATE      = "2022-09-01"
HOLDOUT_START = "2026-04-20"
HOLDOUT_END   = "2026-04-26"


def wape(y_true, y_pred):
    y_true = np.array(y_true, float)
    y_pred = np.array(y_pred, float)
    return np.sum(np.abs(y_true - y_pred)) / (np.sum(np.abs(y_true)) + 1e-9) * 100


if __name__ == "__main__":

    print("Loading data…")
    train_raw_full = pd.read_csv(DATA_FILE)
    train_raw_full["sale_date"] = pd.to_datetime(train_raw_full["sale_date"])
    train_raw_full = train_raw_full[
        train_raw_full["sale_date"] >= CUT_DATE
    ].copy()

    # Hold-out split (just for WAPE evaluation — models train on train_cut internally)
    holdout_df = train_raw_full[
        (train_raw_full["sale_date"] >= HOLDOUT_START)
        & (train_raw_full["sale_date"] <= HOLDOUT_END)
    ].copy()

    years       = list(range(train_raw_full["sale_date"].dt.year.min(), 2027))
    holiday_set = v11.fetch_holidays_api(years)
    weather_df  = v11.fetch_weather_api(
        train_raw_full["sale_date"].min().strftime("%Y-%m-%d"), HOLDOUT_END
    )

    # ── V11 ──────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("V11")
    print("=" * 55)
    wape_v11, fc_v11 = v11.evaluate_on_holdout(
        train_raw_full, holiday_set, weather_df,
        holdout_start=HOLDOUT_START, holdout_end=HOLDOUT_END,
    )

    # ── V12 ──────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("V12")
    print("=" * 55)
    wape_v12, fc_v12 = v12.evaluate_on_holdout(
        train_raw_full, holiday_set, weather_df,
        holdout_start=HOLDOUT_START, holdout_end=HOLDOUT_END,
    )

    # ── SUMMARY ──────────────────────────────────────────────
    delta = wape_v12 - wape_v11
    sign  = "↓ BETTER" if delta < 0 else "↑ WORSE"

    print("\n" + "=" * 55)
    print("SUMMARY")
    print("=" * 55)
    print(f"  v11 Hold-out WAPE : {wape_v11:.3f}%")
    print(f"  v12 Hold-out WAPE : {wape_v12:.3f}%")
    print(f"  Delta             : {delta:+.3f}%  {sign}")

    # Per-hour breakdown
    fc_v11 = fc_v11.rename(columns={"guests_count": "pred_v11"})
    fc_v12 = fc_v12.rename(columns={"guests_count": "pred_v12"})
    for fc in [fc_v11, fc_v12]:
        fc["sale_date"] = pd.to_datetime(fc["sale_date"])

    merged = holdout_df.merge(fc_v11, on=["sale_date", "sale_hour"])
    merged = merged.merge(fc_v12, on=["sale_date", "sale_hour"])

    def hour_wape(df, pred_col):
        return df.groupby("sale_hour").apply(
            lambda x: np.sum(np.abs(x["guests_count"] - x[pred_col]))
                      / np.sum(np.abs(x["guests_count"])) * 100
        ).round(2)

    hw11 = hour_wape(merged, "pred_v11").rename("v11")
    hw12 = hour_wape(merged, "pred_v12").rename("v12")
    cmp  = pd.concat([hw11, hw12], axis=1)
    cmp["delta"] = (cmp["v12"] - cmp["v11"]).round(2)
    cmp["result"] = cmp["delta"].apply(lambda d: "↓" if d < 0 else ("↑" if d > 0 else "="))
    print("\nWAPE by hour:")
    print(cmp.to_string())
