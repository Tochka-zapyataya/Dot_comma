"""
compare_v13.py
--------------
Runs v12 and v13 on the SAME 7-day hold-out (2026-04-20 – 2026-04-26)
and reports WAPE for each. Run from the stage_1_forecast/ directory.
"""

import warnings
warnings.filterwarnings("ignore")

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

import numpy as np
import pandas as pd

import forecast_v12 as v12
import forecast_v13 as v13

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

    holdout_df = train_raw_full[
        (train_raw_full["sale_date"] >= HOLDOUT_START)
        & (train_raw_full["sale_date"] <= HOLDOUT_END)
    ].copy()

    years       = list(range(train_raw_full["sale_date"].dt.year.min(), 2027))
    holiday_set = v12.fetch_holidays_api(years)
    weather_df  = v12.fetch_weather_api(
        train_raw_full["sale_date"].min().strftime("%Y-%m-%d"), HOLDOUT_END
    )

    # ── V12 ──────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("V12")
    print("=" * 55)
    wape_v12, fc_v12 = v12.evaluate_on_holdout(
        train_raw_full, holiday_set, weather_df,
        holdout_start=HOLDOUT_START, holdout_end=HOLDOUT_END,
    )

    # ── V13 ──────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("V13")
    print("=" * 55)
    wape_v13, fc_v13 = v13.evaluate_on_holdout(
        train_raw_full, holiday_set, weather_df,
        holdout_start=HOLDOUT_START, holdout_end=HOLDOUT_END,
    )

    # ── SUMMARY ──────────────────────────────────────────────
    delta = wape_v13 - wape_v12
    sign  = "↓ BETTER" if delta < 0 else "↑ WORSE"

    print("\n" + "=" * 55)
    print("SUMMARY")
    print("=" * 55)
    print(f"  v12 Hold-out WAPE : {wape_v12:.3f}%")
    print(f"  v13 Hold-out WAPE : {wape_v13:.3f}%")
    print(f"  Delta             : {delta:+.3f}%  {sign}")

    # Per-hour breakdown
    fc_v12r = fc_v12.rename(columns={"guests_count": "pred_v12"})
    fc_v13r = fc_v13.rename(columns={"guests_count": "pred_v13"})
    for fc in [fc_v12r, fc_v13r]:
        fc["sale_date"] = pd.to_datetime(fc["sale_date"])

    merged = holdout_df.merge(fc_v12r, on=["sale_date", "sale_hour"])
    merged = merged.merge(fc_v13r, on=["sale_date", "sale_hour"])

    def hour_wape(df, pred_col):
        return df.groupby("sale_hour").apply(
            lambda x: np.sum(np.abs(x["guests_count"] - x[pred_col]))
                      / np.sum(np.abs(x["guests_count"])) * 100
        ).round(2)

    hw12 = hour_wape(merged, "pred_v12").rename("v12")
    hw13 = hour_wape(merged, "pred_v13").rename("v13")
    cmp  = pd.concat([hw12, hw13], axis=1)
    cmp["delta"] = (cmp["v13"] - cmp["v12"]).round(2)
    cmp["result"] = cmp["delta"].apply(lambda d: "↓" if d < 0 else ("↑" if d > 0 else "="))
    print("\nWAPE by hour:")
    print(cmp.to_string())

    # Per-date breakdown
    def date_wape(df, pred_col):
        return df.groupby("sale_date").apply(
            lambda x: np.sum(np.abs(x["guests_count"] - x[pred_col]))
                      / np.sum(np.abs(x["guests_count"])) * 100
        ).round(2)

    dw12 = date_wape(merged, "pred_v12").rename("v12")
    dw13 = date_wape(merged, "pred_v13").rename("v13")
    dcmp = pd.concat([dw12, dw13], axis=1)
    dcmp["delta"] = (dcmp["v13"] - dcmp["v12"]).round(2)
    dcmp["result"] = dcmp["delta"].apply(lambda d: "↓" if d < 0 else ("↑" if d > 0 else "="))
    print("\nWAPE by date:")
    print(dcmp.to_string())
