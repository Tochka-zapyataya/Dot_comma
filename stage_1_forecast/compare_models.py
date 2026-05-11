"""
compare_models.py
-----------------
Runs baseline (v10) and improved (v11) models on the SAME 7-day hold-out
(2026-04-20 – 2026-04-26) and reports WAPE for each.

Train cutoff: 2022-09-01 (same as both models)
Hold-out    : last 7 available days in train.csv
"""

import warnings
warnings.filterwarnings("ignore")

import os, ssl, json, urllib.request
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBRegressor
import lightgbm as lgb
from statsmodels.tsa.holtwinters import ExponentialSmoothing

# ─────────────────────────────────────────────────────────
# SHARED CONFIG
# ─────────────────────────────────────────────────────────

DATA_FILE        = "./data/train.csv"
CUT_DATE         = "2022-09-01"
HOLDOUT_START    = "2026-04-20"
HOLDOUT_END      = "2026-04-26"
WORKING_HOURS    = list(range(7, 23))
HIGH_ERROR_HOURS = {7, 8, 9, 10}
LAT, LON         = 55.800, 37.529

_STATIC_HOLIDAYS_FIXED = {
    (1,1),(1,2),(1,3),(1,4),(1,5),(1,6),(1,7),(1,8),
    (2,23),(3,8),(5,1),(5,9),(6,12),(11,4),
}
_STATIC_EXTRA = {
    "2019-05-02","2019-05-03","2019-05-10","2020-03-09",
    "2021-02-22","2021-05-10","2022-03-07","2022-05-02",
    "2022-05-10","2023-02-24","2023-05-08","2024-04-29",
    "2024-04-30","2024-05-10","2025-04-30","2025-05-02",
    "2026-03-09","2026-05-04",
}
_CLIMATE = {
    1:{"t":-7.0},2:{"t":-6.0},3:{"t":-0.5},4:{"t":8.0},
    5:{"t":15.0},6:{"t":19.0},7:{"t":21.5},8:{"t":20.0},
    9:{"t":14.0},10:{"t":6.5},11:{"t":-0.5},12:{"t":-5.0},
}


def wape(y_true, y_pred):
    y_true, y_pred = np.array(y_true, float), np.array(y_pred, float)
    return np.sum(np.abs(y_true - y_pred)) / (np.sum(np.abs(y_true)) + 1e-9) * 100


def _http_get(url, timeout=10):
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "forecast"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return json.loads(r.read())
    except Exception:
        return None


def fetch_holidays(years):
    s = set()
    for y in years:
        data = _http_get(f"https://date.nager.at/api/v3/PublicHolidays/{y}/RU")
        if data:
            for item in data: s.add(item["date"])
        else:
            for m, d in _STATIC_HOLIDAYS_FIXED: s.add(f"{y}-{m:02d}-{d:02d}")
    return s | _STATIC_EXTRA


def fetch_weather(start, end):
    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={LAT}&longitude={LON}"
        f"&start_date={start}&end_date={end}"
        "&hourly=temperature_2m,precipitation&timezone=Europe%2FMoscow"
    )
    data = _http_get(url)
    if data and "hourly" in data:
        h  = data["hourly"]
        df = pd.DataFrame({"datetime": pd.to_datetime(h["time"]),
                           "temp_real": h["temperature_2m"],
                           "precip_mm": h["precipitation"]}).set_index("datetime")
        return df
    idx = pd.date_range(start, end, freq="h")
    return pd.DataFrame({
        "temp_real": [_CLIMATE[d.month]["t"] for d in idx],
        "precip_mm": 0.0
    }, index=idx)


def make_working_index(start, end):
    idx = []
    for d in pd.date_range(start, end, freq="D"):
        for h in WORKING_HOURS:
            idx.append(pd.Timestamp(d) + pd.Timedelta(hours=h))
    return pd.DatetimeIndex(idx)


# ─────────────────────────────────────────────────────────
# FEATURE BUILDER (shared, with toggle for extra lags)
# ─────────────────────────────────────────────────────────

def compute_features(df, holiday_set, weather_df, train_index=None, extra_lags=False):
    df = df.copy()
    df["hour"]       = df.index.hour
    df["dayofweek"]  = df.index.dayofweek
    df["month"]      = df.index.month
    df["quarter"]    = df.index.quarter
    df["is_weekend"] = (df["dayofweek"] >= 5).astype(int)
    df["hour_sin"]   = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"]   = np.cos(2 * np.pi * df["hour"] / 24)
    df["dow_sin"]    = np.sin(2 * np.pi * df["dayofweek"] / 7)
    df["dow_cos"]    = np.cos(2 * np.pi * df["dayofweek"] / 7)
    df["is_morning"] = (df["hour"] <= 10).astype(int)
    df["is_lunch"]   = df["hour"].isin([11,12,13,14]).astype(int)
    df["is_dinner"]  = df["hour"].isin([17,18,19,20]).astype(int)

    df["is_holiday"] = df.index.normalize().map(
        lambda x: int(x.strftime("%Y-%m-%d") in holiday_set))
    df["is_pre_holiday"] = (df.index.normalize() + pd.Timedelta(days=1)).map(
        lambda x: int(x.strftime("%Y-%m-%d") in holiday_set))
    df["is_post_holiday"] = (df.index.normalize() - pd.Timedelta(days=1)).map(
        lambda x: int(x.strftime("%Y-%m-%d") in holiday_set))

    if weather_df is not None:
        df = df.join(weather_df, how="left")
    df["temp_real"] = df["temp_real"].fillna(
        pd.Series([_CLIMATE[m]["t"] for m in df.index.month], index=df.index))
    df["precip_mm"] = df["precip_mm"].fillna(0)
    df["is_rainy"]  = (df["precip_mm"] > 0.5).astype(int)

    base_lags = [1, 2, 16, 32, 48, 80, 112, 224]
    all_lags  = base_lags + ([336, 448] if extra_lags else [])
    for lag in all_lags:
        df[f"lag_{lag}"] = df["guests_count"].shift(lag)

    base = df["guests_count"].shift(1)
    for w in [16, 32, 80, 112]:
        df[f"rolling_mean_{w}"] = base.rolling(w).mean()
        df[f"rolling_std_{w}"]  = base.rolling(w).std()

    slot_ewm4, slot_ewm8, slot_roll2, slot_roll4 = [], [], [], []
    for (h, d), grp in df.groupby(["hour", "dayofweek"]):
        g = grp.sort_index()["guests_count"].shift(1)
        slot_ewm4.append(g.ewm(span=4).mean())
        slot_ewm8.append(g.ewm(span=8).mean())
        slot_roll2.append(g.rolling(2).mean())
        slot_roll4.append(g.rolling(4).mean())
    df["slot_ewm4"] = pd.concat(slot_ewm4).sort_index()
    df["slot_ewm8"] = pd.concat(slot_ewm8).sort_index()
    df["slot_roll2"]= pd.concat(slot_roll2).sort_index()
    df["slot_roll4"]= pd.concat(slot_roll4).sort_index()
    df["slot_momentum"]     = df["slot_ewm4"] - df["slot_ewm8"]
    df["slot_acceleration"] = df["slot_roll2"] - df["slot_roll4"]
    df["lag1_vs_slot"]      = df["lag_1"] / (df["slot_ewm4"] + 1e-9)

    if train_index is not None:
        tr    = df.loc[df.index.isin(train_index) & df["guests_count"].notna()]
        me_hd = tr.groupby(["hour","dayofweek"])["guests_count"].mean()
        me_h  = tr.groupby(["hour"])["guests_count"].mean()
        df    = df.join(me_hd.rename("me_hour_dow"), on=["hour","dayofweek"])
        df    = df.join(me_h.rename("me_hour"), on=["hour"])
    else:
        df["me_hour_dow"] = 0
        df["me_hour"]     = 0

    return df


# ─────────────────────────────────────────────────────────
# BASELINE (v10)
# ─────────────────────────────────────────────────────────

def run_baseline(train_raw, holiday_set, weather_df, fc_start, fc_end):
    """Original model: ETS(sp=16) + XGB(pseudoHuber) + hardcoded YoY."""

    # ETS
    df = train_raw.copy()
    df["datetime"] = df["sale_date"] + pd.to_timedelta(df["sale_hour"], unit="h")
    df = df.set_index("datetime")
    wi = make_working_index(df.index.min().date(), df.index.max().date())
    df = df.reindex(wi)
    df["guests_count"] = df["guests_count"].interpolate(method="time")

    ets_model = ExponentialSmoothing(
        df["guests_count"], trend="add", seasonal="add",
        seasonal_periods=16, damped_trend=True,
    )
    ets_fit = ets_model.fit(optimized=True)

    forecast_index = make_working_index(fc_start, fc_end)
    future_df = pd.DataFrame({"guests_count": np.nan}, index=forecast_index)
    full_df   = pd.concat([df, future_df])
    full_fe   = compute_features(
        full_df, holiday_set, weather_df,
        train_index=df.index, extra_lags=False
    )

    EXCLUDE     = {"guests_count","sale_hour","sale_date","datetime"}
    feature_cols= [c for c in full_fe.select_dtypes(include=[np.number]).columns
                   if c not in EXCLUDE]
    scaler = StandardScaler()
    scaler.fit(full_fe[feature_cols].fillna(0))
    full_fe_sc = full_fe.copy()
    full_fe_sc[feature_cols] = scaler.transform(full_fe[feature_cols].fillna(0))

    train_fe    = full_fe_sc.loc[full_fe_sc.index.isin(df.index)].copy()
    forecast_fe = full_fe_sc.loc[full_fe_sc.index.isin(forecast_index)].copy()

    ets_fitted = ets_fit.fittedvalues
    common_idx = train_fe.index.intersection(ets_fitted.index)
    boost_df   = train_fe.loc[common_idx].copy()
    boost_df["ets_residual"] = (
        df.loc[common_idx, "guests_count"] - ets_fitted.loc[common_idx]
    )
    for lag in [1,2,16,32,48,80,112]:
        boost_df[f"res_lag_{lag}"] = boost_df["ets_residual"].shift(lag)
    boost_df["residual_momentum"] = boost_df["res_lag_1"] - boost_df["res_lag_16"]
    boost_df = boost_df.dropna()

    res_lag_cols = [c for c in boost_df.columns if c.startswith("res_lag")]
    res_lag_cols.append("residual_momentum")
    res_scaler = StandardScaler()
    boost_df[res_lag_cols] = res_scaler.fit_transform(boost_df[res_lag_cols])

    xgb_features = feature_cols + res_lag_cols
    X, y = boost_df[xgb_features], boost_df["ets_residual"]

    # 5-fold CV
    tscv = TimeSeriesSplit(n_splits=5)
    best_iters, cv_wapes = [], []
    for fold, (tr_i, val_i) in enumerate(tscv.split(X)):
        m = XGBRegressor(
            n_estimators=2500, learning_rate=0.012, max_depth=5,
            subsample=0.85, colsample_bytree=0.85, min_child_weight=2,
            gamma=0.03, reg_alpha=0.1, reg_lambda=1.2,
            objective="reg:pseudohubererror", eval_metric="mae",
            random_state=42, n_jobs=-1, early_stopping_rounds=60,
        )
        m.fit(X.iloc[tr_i], y.iloc[tr_i],
              eval_set=[(X.iloc[val_i], y.iloc[val_i])], verbose=False)
        best_iters.append(m.best_iteration + 1)
        pred   = m.predict(X.iloc[val_i])
        hybrid = np.maximum(ets_fit.fittedvalues.loc[X.iloc[val_i].index].values + pred, 0)
        real   = df.loc[X.iloc[val_i].index, "guests_count"]
        fw     = wape(real, hybrid)
        cv_wapes.append(fw)

    # Final model
    best_n = int(np.median(best_iters))
    xgb_final = XGBRegressor(
        n_estimators=best_n, learning_rate=0.012, max_depth=5,
        subsample=0.85, colsample_bytree=0.85, min_child_weight=2,
        gamma=0.03, reg_alpha=0.1, reg_lambda=1.2,
        objective="reg:pseudohubererror", random_state=42, n_jobs=-1,
    )
    xgb_final.fit(X, y)

    # Forecast
    ets_fc  = ets_fit.forecast(len(forecast_index))
    X_fc    = forecast_fe[feature_cols].copy()
    zero_df = pd.DataFrame(np.zeros((len(X_fc), len(res_lag_cols))),
                           columns=res_lag_cols)
    z_sc    = res_scaler.transform(zero_df)
    for i, col in enumerate(res_lag_cols):
        X_fc[col] = z_sc[:, i]
    for col in xgb_features:
        if col not in X_fc.columns:
            X_fc[col] = 0

    res_pred   = xgb_final.predict(X_fc[xgb_features])
    ml_forecast = np.maximum(ets_fc.values + res_pred, 0)

    # Analog
    YOY_TREND     = 1.067
    analog_values = []
    for ts in forecast_index:
        h = ts.hour; vals = []
        d2025 = str(ts.date()).replace(str(ts.year), "2025")
        m25 = train_raw[
            (train_raw["sale_date"] == pd.Timestamp(d2025))
            & (train_raw["sale_hour"] == h)
        ]
        if len(m25): vals.append(m25["guests_count"].iloc[0] * YOY_TREND)
        wm = train_raw[
            (train_raw["sale_hour"] == h)
            & (train_raw["sale_date"].dt.dayofweek == ts.dayofweek)
        ].tail(4)
        if len(wm): vals.append(wm["guests_count"].mean())
        analog_values.append(np.mean(vals) if vals else np.nan)

    analog_values = np.array(analog_values)
    alpha_ml = np.where(forecast_index.hour <= 10, 0.25, 0.45)
    final    = ml_forecast.copy()
    mask     = ~np.isnan(analog_values)
    final[mask] = alpha_ml[mask]*ml_forecast[mask] + (1-alpha_ml[mask])*analog_values[mask]

    hh = train_raw.groupby("sale_hour")["guests_count"].median()
    for i, ts in enumerate(forecast_index):
        if ts.strftime("%Y-%m-%d") in holiday_set: final[i] *= 0.82
        fl  = 0.55 if ts.hour in HIGH_ERROR_HOURS else 0.40
        final[i] = max(final[i], hh[ts.hour]*fl)

    final = np.round(final).astype(int)

    result = pd.DataFrame({
        "sale_date": [str(ts.date()) for ts in forecast_index],
        "sale_hour": forecast_index.hour,
        "guests_count": final,
    })
    return result, float(np.mean(cv_wapes))


# ─────────────────────────────────────────────────────────
# V11 MODEL
# ─────────────────────────────────────────────────────────

def estimate_yoy(train_raw):
    df = train_raw.copy()
    df["year"]  = df["sale_date"].dt.year
    df["month"] = df["sale_date"].dt.month
    monthly = df.groupby(["year","month"])["guests_count"].sum().unstack(0)
    years   = sorted(monthly.columns)
    if len(years) < 2:
        return 1.067
    y2, y1  = years[-1], years[-2]
    overlap = monthly[[y1, y2]].dropna()
    if len(overlap) < 3:
        return 1.067
    return float((overlap[y2] / overlap[y1]).median())


def run_v11(train_raw, holiday_set, weather_df, fc_start, fc_end):
    """Improved model: ETS(sp=112) + XGB(MAE) + LGB(MAE) + fixes."""

    # ETS with sp=112, fallback sp=16
    df = train_raw.copy()
    df["datetime"] = df["sale_date"] + pd.to_timedelta(df["sale_hour"], unit="h")
    df = df.set_index("datetime")
    wi = make_working_index(df.index.min().date(), df.index.max().date())
    df = df.reindex(wi)
    df["guests_count"] = df["guests_count"].interpolate(method="time")

    ets_fit = None
    for sp in [112, 16]:
        try:
            ets_fit = ExponentialSmoothing(
                df["guests_count"], trend="add", seasonal="add",
                seasonal_periods=sp, damped_trend=True,
                initialization_method="estimated",
            ).fit(optimized=True)
            print(f"  [v11] ETS sp={sp} OK")
            break
        except Exception as e:
            print(f"  [v11] ETS sp={sp} failed: {e}")
    if ets_fit is None:
        raise RuntimeError("ETS fitting failed")

    forecast_index = make_working_index(fc_start, fc_end)
    future_df = pd.DataFrame({"guests_count": np.nan}, index=forecast_index)
    full_df   = pd.concat([df, future_df])
    full_fe   = compute_features(
        full_df, holiday_set, weather_df,
        train_index=df.index, extra_lags=True   # [P1] lag_336, lag_448
    )

    EXCLUDE     = {"guests_count","sale_hour","sale_date","datetime"}
    feature_cols= [c for c in full_fe.select_dtypes(include=[np.number]).columns
                   if c not in EXCLUDE]
    scaler = StandardScaler()
    scaler.fit(full_fe[feature_cols].fillna(0))
    full_fe_sc = full_fe.copy()
    full_fe_sc[feature_cols] = scaler.transform(full_fe[feature_cols].fillna(0))

    train_fe    = full_fe_sc.loc[full_fe_sc.index.isin(df.index)].copy()
    forecast_fe = full_fe_sc.loc[full_fe_sc.index.isin(forecast_index)].copy()

    ets_fitted = ets_fit.fittedvalues
    common_idx = train_fe.index.intersection(ets_fitted.index)
    boost_df   = train_fe.loc[common_idx].copy()
    boost_df["ets_residual"] = (
        df.loc[common_idx, "guests_count"] - ets_fitted.loc[common_idx]
    )
    for lag in [1,2,16,32,48,80,112]:
        boost_df[f"res_lag_{lag}"] = boost_df["ets_residual"].shift(lag)
    boost_df["residual_momentum"] = boost_df["res_lag_1"] - boost_df["res_lag_16"]
    boost_df = boost_df.dropna()

    res_lag_cols = [c for c in boost_df.columns if c.startswith("res_lag")]
    res_lag_cols.append("residual_momentum")
    res_scaler = StandardScaler()
    boost_df[res_lag_cols] = res_scaler.fit_transform(boost_df[res_lag_cols])

    xgb_features = feature_cols + res_lag_cols
    X, y = boost_df[xgb_features], boost_df["ets_residual"]

    tscv = TimeSeriesSplit(n_splits=5)
    best_iters_xgb, best_iters_lgb, cv_wapes = [], [], []

    for fold, (tr_i, val_i) in enumerate(tscv.split(X)):
        X_tr, X_val = X.iloc[tr_i], X.iloc[val_i]
        y_tr, y_val = y.iloc[tr_i], y.iloc[val_i]

        # XGB MAE
        xgb_m = XGBRegressor(
            n_estimators=2500, learning_rate=0.012, max_depth=5,
            subsample=0.85, colsample_bytree=0.85, min_child_weight=2,
            gamma=0.03, reg_alpha=0.1, reg_lambda=1.2,
            objective="reg:absoluteerror", eval_metric="mae",
            random_state=42, n_jobs=-1, early_stopping_rounds=60,
        )
        xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
        best_iters_xgb.append(xgb_m.best_iteration + 1)

        # LGB L1
        lgb_m = lgb.LGBMRegressor(
            n_estimators=2500, learning_rate=0.012, max_depth=5,
            num_leaves=31, subsample=0.85, colsample_bytree=0.85,
            min_child_samples=10, reg_alpha=0.1, reg_lambda=1.2,
            objective="regression_l1", random_state=42, n_jobs=-1, verbose=-1,
        )
        lgb_m.fit(
            X_tr, y_tr, eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(60, verbose=False), lgb.log_evaluation(-1)],
        )
        best_iters_lgb.append(lgb_m.best_iteration_ + 1)

        pred   = 0.5*xgb_m.predict(X_val) + 0.5*lgb_m.predict(X_val)
        hybrid = np.maximum(ets_fit.fittedvalues.loc[X_val.index].values + pred, 0)
        real   = df.loc[X_val.index, "guests_count"]
        fw     = wape(real, hybrid)
        cv_wapes.append(fw)

    # Final models
    best_n_xgb = int(np.median(best_iters_xgb))
    best_n_lgb = int(np.median(best_iters_lgb))

    xgb_final = XGBRegressor(
        n_estimators=best_n_xgb, learning_rate=0.012, max_depth=5,
        subsample=0.85, colsample_bytree=0.85, min_child_weight=2,
        gamma=0.03, reg_alpha=0.1, reg_lambda=1.2,
        objective="reg:absoluteerror", random_state=42, n_jobs=-1,
    )
    xgb_final.fit(X, y)

    lgb_final = lgb.LGBMRegressor(
        n_estimators=best_n_lgb, learning_rate=0.012, max_depth=5,
        num_leaves=31, subsample=0.85, colsample_bytree=0.85,
        min_child_samples=10, reg_alpha=0.1, reg_lambda=1.2,
        objective="regression_l1", random_state=42, n_jobs=-1, verbose=-1,
    )
    lgb_final.fit(X, y)

    # Forecast with real residual lags [P0]
    ets_fc = ets_fit.forecast(len(forecast_index))
    X_fc   = forecast_fe[feature_cols].copy()

    ets_residuals = boost_df["ets_residual"]  # training residuals only
    lag_filled    = {}
    for col in res_lag_cols:
        if col.startswith("res_lag_"):
            lag_k = int(col.replace("res_lag_", ""))
            vals  = []
            full_wh = ets_residuals.index
            for ts in forecast_index:
                pos     = full_wh.searchsorted(ts)    # past end of train index
                src_pos = pos - lag_k
                if 0 <= src_pos < len(full_wh):
                    vals.append(float(ets_residuals.iloc[src_pos]))
                else:
                    vals.append(0.0)
            lag_filled[col] = np.array(vals)

    # residual_momentum
    if "residual_momentum" in res_lag_cols:
        lag_filled["residual_momentum"] = (
            lag_filled.get("res_lag_1",  np.zeros(len(forecast_index)))
            - lag_filled.get("res_lag_16", np.zeros(len(forecast_index)))
        )

    raw_df = pd.DataFrame(
        {c: lag_filled.get(c, np.zeros(len(forecast_index))) for c in res_lag_cols}
    )
    scaled = res_scaler.transform(raw_df)
    for i, col in enumerate(res_lag_cols):
        X_fc[col] = scaled[:, i]

    for col in xgb_features:
        if col not in X_fc.columns:
            X_fc[col] = 0

    res_pred    = 0.5*xgb_final.predict(X_fc[xgb_features]) + \
                  0.5*lgb_final.predict(X_fc[xgb_features])
    ml_forecast = np.maximum(ets_fc.values + res_pred, 0)

    # Analog with EWM [P1] + data-driven YoY [P1]
    YOY_TREND     = estimate_yoy(train_raw)
    analog_values = []
    for ts in forecast_index:
        h = ts.hour; vals = []
        d_prev = str(ts.date()).replace(str(ts.year), str(ts.year - 1))
        mp = train_raw[
            (train_raw["sale_date"] == pd.Timestamp(d_prev))
            & (train_raw["sale_hour"] == h)
        ]
        if len(mp): vals.append(mp["guests_count"].iloc[0] * YOY_TREND)

        wm = train_raw[
            (train_raw["sale_hour"] == h)
            & (train_raw["sale_date"].dt.dayofweek == ts.dayofweek)
        ].sort_values("sale_date")
        if len(wm):
            n = len(wm)
            weights = 0.95 ** np.arange(n-1, -1, -1)
            vals.append(np.average(wm["guests_count"].values, weights=weights))
        analog_values.append(np.mean(vals) if vals else np.nan)

    analog_values = np.array(analog_values)
    alpha_ml = np.where(forecast_index.hour <= 10, 0.25, 0.45)
    final    = ml_forecast.copy()
    mask     = ~np.isnan(analog_values)
    final[mask] = alpha_ml[mask]*ml_forecast[mask] + (1-alpha_ml[mask])*analog_values[mask]

    hh = train_raw.groupby("sale_hour")["guests_count"].median()
    for i, ts in enumerate(forecast_index):
        if ts.strftime("%Y-%m-%d") in holiday_set: final[i] *= 0.82
        fl     = 0.55 if ts.hour in HIGH_ERROR_HOURS else 0.40
        final[i] = max(final[i], hh[ts.hour]*fl)

    final = np.round(final).astype(int)
    result = pd.DataFrame({
        "sale_date": [str(ts.date()) for ts in forecast_index],
        "sale_hour": forecast_index.hour,
        "guests_count": final,
    })
    return result, float(np.mean(cv_wapes))


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":

    # Load data
    train_raw = pd.read_csv(DATA_FILE)
    train_raw["sale_date"] = pd.to_datetime(train_raw["sale_date"])
    train_raw = train_raw[train_raw["sale_date"] >= CUT_DATE].copy()
    print(f"Loaded: {len(train_raw)} rows | "
          f"{train_raw['sale_date'].min().date()} – {train_raw['sale_date'].max().date()}")

    # Split
    train_cut  = train_raw[train_raw["sale_date"] < HOLDOUT_START].copy()
    holdout_df = train_raw[
        (train_raw["sale_date"] >= HOLDOUT_START)
        & (train_raw["sale_date"] <= HOLDOUT_END)
    ].copy()
    print(f"Train (before holdout): {len(train_cut)} rows")
    print(f"Hold-out ({HOLDOUT_START}–{HOLDOUT_END}): {len(holdout_df)} rows\n")

    years       = list(range(train_cut["sale_date"].dt.year.min(), 2027))
    holiday_set = fetch_holidays(years)
    weather_df  = fetch_weather(
        train_cut["sale_date"].min().strftime("%Y-%m-%d"), HOLDOUT_END
    )

    # ── BASELINE (v10) ──────────────────────────────────
    print("=" * 55)
    print("BASELINE (v10)")
    print("=" * 55)
    fc_base, cv_wape_base = run_baseline(
        train_cut, holiday_set, weather_df, HOLDOUT_START, HOLDOUT_END
    )
    pred_base = fc_base.rename(columns={"guests_count": "pred"})
    pred_base["sale_date"] = pd.to_datetime(pred_base["sale_date"])
    merged_base = pd.merge(holdout_df, pred_base, on=["sale_date","sale_hour"])
    holdout_wape_base = wape(merged_base["guests_count"], merged_base["pred"])
    print(f"\n  CV WAPE   (v10): {cv_wape_base:.3f}%")
    print(f"  Hold-out WAPE (v10): {holdout_wape_base:.3f}%")

    # ── V11 ─────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("IMPROVED (v11)")
    print("=" * 55)
    fc_v11, cv_wape_v11 = run_v11(
        train_cut, holiday_set, weather_df, HOLDOUT_START, HOLDOUT_END
    )
    pred_v11 = fc_v11.rename(columns={"guests_count": "pred"})
    pred_v11["sale_date"] = pd.to_datetime(pred_v11["sale_date"])
    merged_v11 = pd.merge(holdout_df, pred_v11, on=["sale_date","sale_hour"])
    holdout_wape_v11 = wape(merged_v11["guests_count"], merged_v11["pred"])
    print(f"\n  CV WAPE   (v11): {cv_wape_v11:.3f}%")
    print(f"  Hold-out WAPE (v11): {holdout_wape_v11:.3f}%")

    # ── SUMMARY ──────────────────────────────────────────
    delta_cv      = cv_wape_v11      - cv_wape_base
    delta_holdout = holdout_wape_v11 - holdout_wape_base
    sign_cv  = "↑ WORSE" if delta_cv > 0 else "↓ better"
    sign_ho  = "↑ WORSE" if delta_holdout > 0 else "↓ better"

    print("\n" + "=" * 55)
    print("SUMMARY")
    print("=" * 55)
    print(f"  CV WAPE   : v10={cv_wape_base:.3f}%  v11={cv_wape_v11:.3f}%  Δ={delta_cv:+.3f}% {sign_cv}")
    print(f"  Hold-out  : v10={holdout_wape_base:.3f}%  v11={holdout_wape_v11:.3f}%  Δ={delta_holdout:+.3f}% {sign_ho}")

    if holdout_wape_v11 < holdout_wape_base:
        print("\n✅  v11 is BETTER on the hold-out — keeping improvements.")
    else:
        print("\n❌  v11 is WORSE on the hold-out — baseline (v10) is preferred.")
