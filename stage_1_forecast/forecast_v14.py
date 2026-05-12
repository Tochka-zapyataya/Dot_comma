# ============================================================
# FORECAST MODEL v14
# ETS(sp=112) + XGBoost(MAE) + LightGBM(MAE) + Analog Ensemble
#
# CHANGES vs v13:
# [1] Morning downweight: часы 7-10 получают vol_w × 0.3 при обучении —
#     модель фокусируется на пиковых часах с высоким вкладом в WAPE.
#
# MAIN METRIC: WAPE
# ============================================================

import warnings
warnings.filterwarnings("ignore")

import bisect
import os
import ssl
import json
import urllib.request

import numpy as np
import pandas as pd

from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit

from xgboost import XGBRegressor
import lightgbm as lgb
from statsmodels.tsa.holtwinters import ExponentialSmoothing

# ============================================================
# CONFIG
# ============================================================

WORKING_HOURS   = list(range(7, 23))
HOURS_PER_DAY   = 16

LAT = 55.800
LON = 37.529

DATA_DIR = "./data"

FORECAST_START = "2026-04-27"
FORECAST_END   = "2026-05-03"

CUT_DATE = "2022-09-01"

HIGH_ERROR_HOURS = {7, 8, 9, 10}

# ============================================================
# METRIC
# ============================================================

def wape(y_true, y_pred):
    y_true = np.array(y_true, dtype=float)
    y_pred = np.array(y_pred, dtype=float)
    return np.sum(np.abs(y_true - y_pred)) / (np.sum(np.abs(y_true)) + 1e-9) * 100


# ============================================================
# HOLIDAYS
# ============================================================

_STATIC_HOLIDAYS_FIXED = {
    (1,1),(1,2),(1,3),(1,4),(1,5),(1,6),(1,7),(1,8),
    (2,23),(3,8),(5,1),(5,9),(6,12),(11,4),
}

_STATIC_EXTRA = {
    "2019-05-02","2019-05-03","2019-05-10",
    "2020-03-09",
    "2021-02-22","2021-05-10",
    "2022-03-07","2022-05-02","2022-05-10",
    "2023-02-24","2023-05-08",
    "2024-04-29","2024-04-30","2024-05-10",
    "2025-04-30","2025-05-02",
    "2026-03-09","2026-05-04",
}

# ============================================================
# WEATHER FALLBACK
# ============================================================

_CLIMATE_FALLBACK = {
    1: {"t": -7.0, "p": 40},
    2: {"t": -6.0, "p": 35},
    3: {"t": -0.5, "p": 35},
    4: {"t":  8.0, "p": 40},
    5: {"t": 15.0, "p": 50},
    6: {"t": 19.0, "p": 70},
    7: {"t": 21.5, "p": 75},
    8: {"t": 20.0, "p": 70},
    9: {"t": 14.0, "p": 55},
    10:{"t":  6.5, "p": 55},
    11:{"t": -0.5, "p": 45},
    12:{"t": -5.0, "p": 45},
}

# ============================================================
# HTTP
# ============================================================

def _http_get(url, timeout=10):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode   = ssl.CERT_NONE
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "forecast-model"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return json.loads(r.read())
    except Exception:
        return None


# ============================================================
# HOLIDAYS API
# ============================================================

def fetch_holidays_api(years):
    holiday_dates = set()
    for year in years:
        url  = f"https://date.nager.at/api/v3/PublicHolidays/{year}/RU"
        data = _http_get(url)
        if data:
            for item in data:
                holiday_dates.add(item["date"])
        else:
            for m, d in _STATIC_HOLIDAYS_FIXED:
                holiday_dates.add(f"{year}-{m:02d}-{d:02d}")
    holiday_dates |= _STATIC_EXTRA
    return holiday_dates


# ============================================================
# WEATHER API
# ============================================================

def fetch_weather_api(start_date, end_date, known_cutoff=None):
    arch_end = str(end_date)
    if known_cutoff and str(known_cutoff) < str(end_date):
        arch_end = str(known_cutoff)

    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={LAT}&longitude={LON}"
        f"&start_date={start_date}&end_date={arch_end}"
        "&hourly=temperature_2m,precipitation"
        "&timezone=Europe%2FMoscow"
    )
    data = _http_get(url)
    if data is None or "hourly" not in data:
        idx = pd.date_range(start_date, arch_end, freq="h")
        arch_df = pd.DataFrame(index=idx)
        arch_df["temp_real"] = [_CLIMATE_FALLBACK[d.month]["t"] for d in idx]
        arch_df["precip_mm"] = 0.0
    else:
        h = data["hourly"]
        arch_df = pd.DataFrame({
            "datetime":  pd.to_datetime(h["time"]),
            "temp_real": h["temperature_2m"],
            "precip_mm": h["precipitation"],
        }).set_index("datetime")

    if known_cutoff and str(end_date) > str(known_cutoff):
        future_start = (
            pd.Timestamp(known_cutoff) + pd.Timedelta(days=1)
        ).strftime("%Y-%m-%d")
        fi = pd.date_range(future_start, end_date, freq="h")
        fd = pd.DataFrame(index=fi)
        fd["temp_real"] = [_CLIMATE_FALLBACK[d.month]["t"] for d in fi]
        fd["precip_mm"] = 0.0
        return pd.concat([arch_df, fd])

    return arch_df


# ============================================================
# INDEX
# ============================================================

def make_working_index(start_date, end_date):
    days = pd.date_range(start_date, end_date, freq="D")
    idx  = []
    for d in days:
        for h in WORKING_HOURS:
            idx.append(pd.Timestamp(d) + pd.Timedelta(hours=h))
    return pd.DatetimeIndex(idx)


# ============================================================
# YoY TREND — monthly median (same as v12, more robust)
# ============================================================

def estimate_yoy_trend(train_raw):
    df = train_raw.copy()
    df["year"]  = df["sale_date"].dt.year
    df["month"] = df["sale_date"].dt.month
    monthly = (
        df.groupby(["year", "month"])["guests_count"]
        .sum()
        .unstack(0)
    )
    years = sorted(monthly.columns)
    if len(years) < 2:
        return 1.067
    y2, y1 = years[-1], years[-2]
    overlap = monthly[[y1, y2]].dropna()
    if len(overlap) < 3:
        return 1.067
    trend = (overlap[y2] / overlap[y1]).median()
    print(f"[v13] Estimated YoY trend {y1}→{y2}: {trend:.4f}")
    return float(trend)


# ============================================================
# HOLIDAY RATIO BY HOUR (data-driven, from v12)
# ============================================================

def compute_holiday_ratio_by_hour(train_raw, holiday_set):
    df = train_raw.copy()
    df["is_hol"] = df["sale_date"].map(
        lambda x: x.strftime("%Y-%m-%d") in holiday_set
    )
    non_hol_mean = df[~df["is_hol"]].groupby("sale_hour")["guests_count"].mean()
    hol_mean     = df[ df["is_hol"]].groupby("sale_hour")["guests_count"].mean()
    ratio = (hol_mean / non_hol_mean).reindex(range(7, 23)).fillna(0.82)
    return ratio


# ============================================================
# FEATURES (+slot_ewm12 vs v12)
# ============================================================

def compute_features(df, holiday_set, weather_df, train_index=None):
    df = df.copy()

    # — time —
    df["hour"]       = df.index.hour
    df["dayofweek"]  = df.index.dayofweek
    df["month"]      = df.index.month
    df["quarter"]    = df.index.quarter
    df["is_weekend"] = (df["dayofweek"] >= 5).astype(int)

    # — cyclical —
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["dow_sin"]  = np.sin(2 * np.pi * df["dayofweek"] / 7)
    df["dow_cos"]  = np.cos(2 * np.pi * df["dayofweek"] / 7)

    # — business slots —
    df["is_morning"] = (df["hour"] <= 10).astype(int)
    df["is_lunch"]   = df["hour"].isin([11, 12, 13, 14]).astype(int)
    df["is_dinner"]  = df["hour"].isin([17, 18, 19, 20]).astype(int)

    # — holiday flags —
    df["is_holiday"] = df.index.normalize().map(
        lambda x: int(x.strftime("%Y-%m-%d") in holiday_set)
    )
    df["is_pre_holiday"] = (df.index.normalize() + pd.Timedelta(days=1)).map(
        lambda x: int(x.strftime("%Y-%m-%d") in holiday_set)
    )
    df["is_post_holiday"] = (df.index.normalize() - pd.Timedelta(days=1)).map(
        lambda x: int(x.strftime("%Y-%m-%d") in holiday_set)
    )

    holiday_ts_sorted = sorted([pd.Timestamp(h) for h in holiday_set])

    def _days_to_nearest(ts_date):
        pos = bisect.bisect_left(holiday_ts_sorted, ts_date)
        cands = []
        if pos < len(holiday_ts_sorted):
            cands.append(abs((ts_date - holiday_ts_sorted[pos]).days))
        if pos > 0:
            cands.append(abs((ts_date - holiday_ts_sorted[pos - 1]).days))
        return int(min(cands)) if cands else 30

    normalized_dates = df.index.normalize()
    df["days_to_holiday"] = [_days_to_nearest(d) for d in normalized_dates]
    df["is_holiday_week"]  = (df["days_to_holiday"] <= 3).astype(int)

    # — weather —
    if weather_df is not None:
        df = df.join(weather_df, how="left")
    temp_fallback = pd.Series(
        [_CLIMATE_FALLBACK[m]["t"] for m in df.index.month], index=df.index
    )
    df["temp_real"] = df["temp_real"].fillna(temp_fallback)
    df["precip_mm"] = df["precip_mm"].fillna(0)
    df["is_rainy"]  = (df["precip_mm"] > 0.5).astype(int)

    # — lags —
    for lag in [1, 2, 16, 32, 48, 80, 112, 224, 336, 448]:
        df[f"lag_{lag}"] = df["guests_count"].shift(lag)

    # — rolling —
    base = df["guests_count"].shift(1)
    for w in [16, 32, 80, 112]:
        df[f"rolling_mean_{w}"] = base.rolling(w).mean()
        df[f"rolling_std_{w}"]  = base.rolling(w).std()

    # — slot features (+ ewm12 vs v12) —
    slot_ewm4, slot_ewm8, slot_ewm12, slot_roll2, slot_roll4 = [], [], [], [], []
    for (h, d), grp in df.groupby(["hour", "dayofweek"]):
        g = grp.sort_index()["guests_count"].shift(1)
        slot_ewm4.append(g.ewm(span=4).mean())
        slot_ewm8.append(g.ewm(span=8).mean())
        slot_ewm12.append(g.ewm(span=12).mean())   # [NEW v13]
        slot_roll2.append(g.rolling(2).mean())
        slot_roll4.append(g.rolling(4).mean())

    df["slot_ewm4"]  = pd.concat(slot_ewm4).sort_index()
    df["slot_ewm8"]  = pd.concat(slot_ewm8).sort_index()
    df["slot_ewm12"] = pd.concat(slot_ewm12).sort_index()  # [NEW v13]
    df["slot_roll2"] = pd.concat(slot_roll2).sort_index()
    df["slot_roll4"] = pd.concat(slot_roll4).sort_index()

    df["slot_momentum"]     = df["slot_ewm4"] - df["slot_ewm8"]
    df["slot_acceleration"] = df["slot_roll2"] - df["slot_roll4"]
    df["lag1_vs_slot"]      = df["lag_1"] / (df["slot_ewm4"] + 1e-9)
    df["ewm4_vs_ewm12"]     = df["slot_ewm4"] - df["slot_ewm12"]  # [NEW v13]

    # — mean encoding —
    if train_index is not None:
        tr    = df.loc[df.index.isin(train_index) & df["guests_count"].notna()]
        me_hd = tr.groupby(["hour", "dayofweek"])["guests_count"].mean()
        me_h  = tr.groupby(["hour"])["guests_count"].mean()
        df = df.join(me_hd.rename("me_hour_dow"), on=["hour", "dayofweek"])
        df = df.join(me_h.rename("me_hour"),      on=["hour"])
    else:
        df["me_hour_dow"] = 0
        df["me_hour"]     = 0

    return df


# ============================================================
# ETS
# ============================================================

def prepare_ets(train_raw):
    df = train_raw.copy()
    df["datetime"] = df["sale_date"] + pd.to_timedelta(df["sale_hour"], unit="h")
    df = df.set_index("datetime")

    wi = make_working_index(df.index.min().date(), df.index.max().date())
    df = df.reindex(wi)
    df["guests_count"] = df["guests_count"].interpolate(method="time")

    train_ets = df["guests_count"]

    for sp in [112, 16]:
        try:
            model = ExponentialSmoothing(
                train_ets,
                trend="add",
                seasonal="add",
                seasonal_periods=sp,
                damped_trend=True,
                initialization_method="estimated",
            )
            fit = model.fit(optimized=True)
            print(f"[v13] ETS fitted with seasonal_periods={sp}")
            return df, train_ets, fit
        except Exception as e:
            print(f"[v13] ETS sp={sp} failed: {e}. Trying next…")

    raise RuntimeError("ETS fitting failed")


# ============================================================
# MODEL
# ============================================================

def build_model(train_raw, holiday_set, weather_df):

    df_working, train_ets, ets_fit = prepare_ets(train_raw)

    forecast_index = make_working_index(FORECAST_START, FORECAST_END)
    future_df = pd.DataFrame({"guests_count": np.nan}, index=forecast_index)

    full_df = pd.concat([df_working, future_df])
    full_fe = compute_features(
        full_df, holiday_set, weather_df, train_index=df_working.index
    )

    EXCLUDE = {"guests_count", "sale_hour", "sale_date", "datetime"}
    feature_cols = [
        c for c in full_fe.select_dtypes(include=[np.number]).columns
        if c not in EXCLUDE
    ]

    scaler = StandardScaler()
    scaler.fit(full_fe[feature_cols].fillna(0))

    full_fe_sc = full_fe.copy()
    full_fe_sc[feature_cols] = scaler.transform(full_fe[feature_cols].fillna(0))

    train_fe    = full_fe_sc.loc[full_fe_sc.index.isin(df_working.index)].copy()
    forecast_fe = full_fe_sc.loc[full_fe_sc.index.isin(forecast_index)].copy()

    ets_fitted  = ets_fit.fittedvalues
    common_idx  = train_fe.index.intersection(ets_fitted.index)

    boost_df = train_fe.loc[common_idx].copy()
    boost_df["ets_residual"] = (
        df_working.loc[common_idx, "guests_count"] - ets_fitted.loc[common_idx]
    )

    for lag in [1, 2, 16, 32, 48, 80, 112]:
        boost_df[f"res_lag_{lag}"] = boost_df["ets_residual"].shift(lag)
    boost_df["residual_momentum"] = boost_df["res_lag_1"] - boost_df["res_lag_16"]
    boost_df = boost_df.dropna()

    res_lag_cols = [c for c in boost_df.columns if c.startswith("res_lag")]
    res_lag_cols.append("residual_momentum")

    res_scaler = StandardScaler()
    boost_df[res_lag_cols] = res_scaler.fit_transform(boost_df[res_lag_cols])

    xgb_features = feature_cols + res_lag_cols

    X = boost_df[xgb_features]
    y = boost_df["ets_residual"]

    # [v13] Recency weights + volume weights
    most_recent_ts = boost_df.index.max()
    elapsed_days   = np.array(
        (most_recent_ts - boost_df.index).total_seconds(), dtype=float
    ) / 86400.0
    sw_recency = np.exp(-elapsed_days / 548.0)
    sw_recency = sw_recency / sw_recency.mean()

    # volume weight: пиковые часы (12-19) вносят больше в WAPE
    hour_mean_volume = (
        train_raw.groupby("sale_hour")["guests_count"].mean()
    )
    global_mean_volume = train_raw["guests_count"].mean()
    vol_w = boost_df.index.hour.map(
        lambda h: 1.0 + 0.5 * (
            hour_mean_volume.get(h, global_mean_volume) / global_mean_volume - 1.0
        )
    ).values

    # [v14] Morning downweight: часы 7-10 уже плохо предсказываются,
    # снижаем их вес чтобы модель концентрировалась на пиковых часах
    morning_mask = np.isin(boost_df.index.hour, list(HIGH_ERROR_HOURS))
    vol_w = np.where(morning_mask, vol_w * 0.3, vol_w)

    sw_all = sw_recency * vol_w
    sw_all = sw_all / sw_all.mean()
    sample_weights = pd.Series(sw_all, index=boost_df.index)

    # CV by (hour, dow)
    recent_for_cv = train_raw[train_raw["sale_date"] >= pd.Timestamp("2023-01-01")].copy()
    recent_for_cv["dow"] = recent_for_cv["sale_date"].dt.dayofweek
    cv_by_slot = (
        recent_for_cv.groupby(["sale_hour", "dow"])["guests_count"].std() /
        recent_for_cv.groupby(["sale_hour", "dow"])["guests_count"].mean()
    ).fillna(0.20)

    holiday_ratio_by_hour = compute_holiday_ratio_by_hour(train_raw, holiday_set)

    tscv = TimeSeriesSplit(n_splits=5)
    cv_wape, best_estimators_xgb, best_estimators_lgb = [], [], []

    for fold, (tr_idx, val_idx) in enumerate(tscv.split(X)):
        X_tr, X_val = X.iloc[tr_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[tr_idx], y.iloc[val_idx]
        sw_tr       = sample_weights.iloc[tr_idx].values

        xgb_m = XGBRegressor(
            n_estimators=2500,
            learning_rate=0.012,
            max_depth=5,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_weight=2,
            gamma=0.03,
            reg_alpha=0.1,
            reg_lambda=1.2,
            objective="reg:absoluteerror",
            eval_metric="mae",
            random_state=42,
            n_jobs=-1,
            early_stopping_rounds=60,
        )
        xgb_m.fit(
            X_tr, y_tr,
            sample_weight=sw_tr,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )
        best_estimators_xgb.append(xgb_m.best_iteration + 1)

        lgb_m = lgb.LGBMRegressor(
            n_estimators=2500,
            learning_rate=0.012,
            max_depth=5,
            num_leaves=31,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_samples=10,
            reg_alpha=0.1,
            reg_lambda=1.2,
            objective="regression_l1",
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )
        lgb_m.fit(
            X_tr, y_tr,
            sample_weight=sw_tr,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(60, verbose=False), lgb.log_evaluation(-1)],
        )
        best_estimators_lgb.append(lgb_m.best_iteration_ + 1)

        pred_res = 0.5 * xgb_m.predict(X_val) + 0.5 * lgb_m.predict(X_val)

        val_dates  = X_val.index
        ets_pred   = ets_fit.fittedvalues.loc[val_dates]
        hybrid     = np.maximum(ets_pred.values + pred_res, 0)
        real       = df_working.loc[val_dates, "guests_count"]

        fold_wape = wape(real, hybrid)
        cv_wape.append(fold_wape)
        print(f"  fold {fold+1} | WAPE={fold_wape:.3f}%")

    print(f"\n  CV WAPE (v13): {np.mean(cv_wape):.3f}%")

    best_n_xgb = int(np.median(best_estimators_xgb))
    best_n_lgb = int(np.median(best_estimators_lgb))

    xgb_final = XGBRegressor(
        n_estimators=best_n_xgb,
        learning_rate=0.012,
        max_depth=5,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=2,
        gamma=0.03,
        reg_alpha=0.1,
        reg_lambda=1.2,
        objective="reg:absoluteerror",
        random_state=42,
        n_jobs=-1,
    )
    xgb_final.fit(X, y, sample_weight=sample_weights.values)

    lgb_final = lgb.LGBMRegressor(
        n_estimators=best_n_lgb,
        learning_rate=0.012,
        max_depth=5,
        num_leaves=31,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_samples=10,
        reg_alpha=0.1,
        reg_lambda=1.2,
        objective="regression_l1",
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    lgb_final.fit(X, y, sample_weight=sample_weights.values)

    importance = pd.DataFrame({
        "feature":    xgb_features,
        "importance": xgb_final.feature_importances_,
    }).sort_values("importance", ascending=False)

    return {
        "xgb":                   xgb_final,
        "lgb":                   lgb_final,
        "ets_fit":               ets_fit,
        "forecast_fe":           forecast_fe,
        "forecast_index":        forecast_index,
        "feature_cols":          feature_cols,
        "xgb_features":          xgb_features,
        "res_lag_cols":          res_lag_cols,
        "res_scaler":            res_scaler,
        "df_working":            df_working,
        "importance":            importance,
        "train_raw":             train_raw,
        "ets_residuals":         boost_df["ets_residual"],
        "cv_by_slot":            cv_by_slot,
        "holiday_ratio_by_hour": holiday_ratio_by_hour,
    }


# ============================================================
# FILL RESIDUAL LAGS
# ============================================================

def fill_residual_lags_for_forecast(
    forecast_index,
    residual_series,
    res_lag_cols,
    res_scaler,
):
    full_wh_idx = residual_series.index

    lag_nums = []
    for col in res_lag_cols:
        if col.startswith("res_lag_"):
            lag_nums.append((col, int(col.replace("res_lag_", ""))))
        else:
            lag_nums.append((col, None))

    filled = {}
    for col, lag_k in lag_nums:
        if lag_k is None:
            continue
        values = []
        for ts in forecast_index:
            pos     = full_wh_idx.searchsorted(ts)
            src_pos = pos - lag_k
            if 0 <= src_pos < len(full_wh_idx):
                src_ts = full_wh_idx[src_pos]
                values.append(float(residual_series.get(src_ts, 0.0)))
            else:
                values.append(0.0)
        filled[col] = np.array(values)

    if "residual_momentum" in res_lag_cols:
        filled["residual_momentum"] = (
            filled.get("res_lag_1",  np.zeros(len(forecast_index)))
            - filled.get("res_lag_16", np.zeros(len(forecast_index)))
        )

    raw_df = pd.DataFrame(
        {col: filled.get(col, np.zeros(len(forecast_index))) for col in res_lag_cols},
    )
    scaled = res_scaler.transform(raw_df)
    return pd.DataFrame(scaled, columns=res_lag_cols)


# ============================================================
# FORECAST
# ============================================================

def make_forecast(artifacts, holiday_set):

    xgb              = artifacts["xgb"]
    lgb_m            = artifacts["lgb"]
    ets_fit          = artifacts["ets_fit"]
    forecast_fe      = artifacts["forecast_fe"]
    forecast_index   = artifacts["forecast_index"]
    feature_cols     = artifacts["feature_cols"]
    xgb_features     = artifacts["xgb_features"]
    res_lag_cols     = artifacts["res_lag_cols"]
    res_scaler       = artifacts["res_scaler"]
    train_raw        = artifacts["train_raw"]
    ets_residuals    = artifacts["ets_residuals"]
    cv_by_slot       = artifacts["cv_by_slot"]
    holiday_ratio_by_hour = artifacts["holiday_ratio_by_hour"]
    ets_forecast = ets_fit.forecast(len(forecast_index))

    X_fc = forecast_fe[feature_cols].copy()

    res_lag_filled = fill_residual_lags_for_forecast(
        forecast_index, ets_residuals, res_lag_cols, res_scaler
    )
    for col in res_lag_cols:
        X_fc[col] = res_lag_filled[col].values

    for col in xgb_features:
        if col not in X_fc.columns:
            X_fc[col] = 0

    res_pred_xgb = xgb.predict(X_fc[xgb_features])
    res_pred_lgb = lgb_m.predict(X_fc[xgb_features])
    res_pred     = 0.5 * res_pred_xgb + 0.5 * res_pred_lgb

    ml_forecast = np.maximum(ets_forecast.values + res_pred, 0)

    # Adaptive blend weights by (hour, dow) CV
    cv_min = cv_by_slot.min()
    cv_max = cv_by_slot.max()
    alpha_ml = np.array([
        0.40 + 0.10 * np.clip(
            (cv_by_slot.get((ts.hour, ts.dayofweek), 0.20) - cv_min)
            / (cv_max - cv_min + 1e-9),
            0, 1
        )
        for ts in forecast_index
    ])
    alpha_analog = 1.0 - alpha_ml

    # ========================================================
    # ANALOG ENSEMBLE
    # [v13] holiday YoY cap: hol_yoy = min(YOY_TREND, 1.0)
    # ========================================================

    YOY_TREND = estimate_yoy_trend(train_raw)

    analog_values        = []
    used_holiday_pool_arr = []

    for ts in forecast_index:
        hour        = ts.hour
        ts_date_str = ts.strftime("%Y-%m-%d")
        is_ts_hol   = ts_date_str in holiday_set
        values            = []
        used_holiday_pool = False

        if is_ts_hol:
            same_day = train_raw[
                (train_raw["sale_date"].dt.month == ts.month) &
                (train_raw["sale_date"].dt.day   == ts.day)   &
                (train_raw["sale_hour"]           == hour)
            ].sort_values("sale_date")

            if len(same_day) >= 2:
                n = len(same_day)
                w = 0.90 ** np.arange(n - 1, -1, -1)
                hol_val = np.average(same_day["guests_count"].values, weights=w)
                # [v13] Holiday YoY cap: не применяем положительный тренд к праздникам
                hol_yoy = min(YOY_TREND, 1.0)
                hol_val *= (1.0 + 0.5 * (hol_yoy - 1.0))
                values.append(hol_val)
                used_holiday_pool = True

        if not used_holiday_pool:
            d_prev = str(ts.date()).replace(str(ts.year), str(ts.year - 1))
            m_prev = train_raw[
                (train_raw["sale_date"] == pd.Timestamp(d_prev))
                & (train_raw["sale_hour"] == hour)
            ]
            if len(m_prev):
                values.append(m_prev["guests_count"].iloc[0] * YOY_TREND)

            weekday_rows = train_raw[
                (train_raw["sale_hour"] == hour) &
                (train_raw["sale_date"].dt.dayofweek == ts.dayofweek)
            ]
            if is_ts_hol:
                weekday_rows = weekday_rows[
                    ~(
                        (weekday_rows["sale_date"].dt.month == ts.month) &
                        (weekday_rows["sale_date"].dt.day   == ts.day)
                    )
                ]
            weekday_rows = weekday_rows.sort_values("sale_date")
            if len(weekday_rows):
                n = len(weekday_rows)
                w = 0.95 ** np.arange(n - 1, -1, -1)
                values.append(np.average(weekday_rows["guests_count"].values, weights=w))

        analog_values.append(np.mean(values) if values else np.nan)
        used_holiday_pool_arr.append(used_holiday_pool)

    analog_values         = np.array(analog_values)
    used_holiday_pool_arr = np.array(used_holiday_pool_arr)

    # Blend ML + analog
    # [v13] Holiday alpha boost: для праздников с historical pool
    # используем alpha_analog=0.85 — ML слабо знает праздничный паттерн
    final = ml_forecast.copy()
    mask  = ~np.isnan(analog_values)
    for i in np.where(mask)[0]:
        if used_holiday_pool_arr[i]:
            a_ml = 0.15
        else:
            a_ml = alpha_ml[i]
        final[i] = a_ml * ml_forecast[i] + (1.0 - a_ml) * analog_values[i]

    # Holiday correction + floor clipping
    holiday_hours = train_raw.groupby("sale_hour")["guests_count"].median()

    for i, ts in enumerate(forecast_index):
        ds = ts.strftime("%Y-%m-%d")

        if ds in holiday_set and not used_holiday_pool_arr[i]:
            ratio    = float(holiday_ratio_by_hour.get(ts.hour, 0.82))
            final[i] *= ratio

        floor_mul = 0.55 if ts.hour in HIGH_ERROR_HOURS else 0.40
        floor_val = holiday_hours[ts.hour] * floor_mul
        final[i]  = max(final[i], floor_val)

    final = np.round(final).astype(int)

    result_std = pd.DataFrame({
        "sale_date":    [str(ts.date()) for ts in forecast_index],
        "sale_hour":    forecast_index.hour,
        "guests_count": final,
    })
    result_kaggle = pd.DataFrame({
        "ID":           [f"{ts.date()}-{ts.hour:02d}" for ts in forecast_index],
        "guests_count": final,
    })
    return result_std, result_kaggle


# ============================================================
# HOLD-OUT EVALUATION
# ============================================================

def evaluate_on_holdout(
    train_raw_full,
    holiday_set,
    weather_df,
    holdout_start="2026-04-20",
    holdout_end="2026-04-26",
):
    print(f"\n[eval] Hold-out: {holdout_start} – {holdout_end}")

    train_cut = train_raw_full[
        train_raw_full["sale_date"] < pd.Timestamp(holdout_start)
    ].copy()

    holdout_df = train_raw_full[
        (train_raw_full["sale_date"] >= pd.Timestamp(holdout_start))
        & (train_raw_full["sale_date"] <= pd.Timestamp(holdout_end))
    ].copy()

    print(f"[eval] Train rows: {len(train_cut)}  |  Holdout rows: {len(holdout_df)}")

    import forecast_v14 as _self
    orig_start, orig_end = _self.FORECAST_START, _self.FORECAST_END
    _self.FORECAST_START = holdout_start
    _self.FORECAST_END   = holdout_end

    arts = build_model(train_cut, holiday_set, weather_df)
    result_std, _ = make_forecast(arts, holiday_set)

    _self.FORECAST_START = orig_start
    _self.FORECAST_END   = orig_end

    pred = result_std.rename(columns={"guests_count": "pred"})
    pred["sale_date"] = pd.to_datetime(pred["sale_date"])
    merged = pd.merge(holdout_df, pred, on=["sale_date", "sale_hour"], how="inner")
    hw = wape(merged["guests_count"].values, merged["pred"].values)
    print(f"[eval] Hold-out WAPE (v13): {hw:.3f}%")
    return hw, result_std


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    os.makedirs("./output", exist_ok=True)

    train_raw = pd.read_csv(f"{DATA_DIR}/train.csv")
    train_raw["sale_date"] = pd.to_datetime(train_raw["sale_date"])
    train_raw = train_raw.loc[train_raw["sale_date"] >= CUT_DATE].copy()

    print(
        f"Train after cut: {len(train_raw)} rows | "
        f"{train_raw['sale_date'].min().date()} – "
        f"{train_raw['sale_date'].max().date()}"
    )

    years       = list(range(train_raw["sale_date"].dt.year.min(), 2027))
    holiday_set = fetch_holidays_api(years)
    weather_df  = fetch_weather_api(
        train_raw["sale_date"].min().strftime("%Y-%m-%d"), FORECAST_END
    )

    print("\n[v13] Building final model…")
    artifacts = build_model(train_raw, holiday_set, weather_df)
    result_std, result_kaggle = make_forecast(artifacts, holiday_set)

    result_std.to_excel("./output/forecast_standard_v14.xlsx", index=False)
    result_kaggle.to_csv("./output/forecast_kaggle_v14.csv", index=False)

    print("\nDONE")
    print("\n--- Forecast (first 10 rows) ---")
    print(result_std.head(10).to_string(index=False))
    print("\n--- Top Features ---")
    print(artifacts["importance"].head(20).to_string(index=False))
