"""
multi_holdout_compare.py
------------------------
Сравнение v13 vs v14 на 3 разных holdout-окнах (апрель / февраль / ноябрь).
Средний WAPE — надёжная оценка, устойчивая к шуму одной недели.

Для обеих моделей на каждом окне:
  weather known_cutoff = holdout_start - 1 day  →  нет утечки данных.
"""
import warnings; warnings.filterwarnings("ignore")
import os, sys, numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE); sys.path.insert(0, HERE)

import forecast_v13 as v13
import forecast_v14 as v14

DATA_FILE = "./data/train.csv"
CUT_DATE  = "2022-09-01"

# Три непересекающихся окна: весна / зима / осень
HOLDOUTS = [
    ("2026-04-20", "2026-04-26", "весна-2026 (апрель)"),
    ("2026-02-02", "2026-02-08", "зима-2026  (февраль)"),
    ("2025-10-27", "2025-11-02", "осень-2025 (октябрь-ноябрь)"),
]


def wape(a, b):
    a, b = np.array(a, float), np.array(b, float)
    return np.sum(np.abs(a - b)) / (np.sum(np.abs(a)) + 1e-9) * 100


def run_holdout(mod, mod_name, train_full, holiday_set, weather_df, h_start, h_end):
    """Запускает evaluate_on_holdout модуля mod с переданным weather_df."""
    print(f"\n  [{mod_name}] holdout {h_start} – {h_end}")
    hw, fc = mod.evaluate_on_holdout(
        train_full, holiday_set, weather_df,
        holdout_start=h_start, holdout_end=h_end,
    )
    return hw, fc


if __name__ == "__main__":

    print("Loading data…")
    train_full = pd.read_csv(DATA_FILE)
    train_full["sale_date"] = pd.to_datetime(train_full["sale_date"])
    train_full = train_full[train_full["sale_date"] >= CUT_DATE].copy()

    years = list(range(train_full["sale_date"].dt.year.min(), 2027))
    holiday_set = v14.fetch_holidays_api(years)

    results = {}   # {model_name: [wape1, wape2, wape3]}

    for h_start, h_end, label in HOLDOUTS:
        print(f"\n{'='*60}")
        print(f"HOLDOUT: {label}  ({h_start} – {h_end})")
        print("=" * 60)

        # Погода без утечки: архив до holdout_start-1, дальше климат-фолбек
        cutoff = str((pd.Timestamp(h_start) - pd.Timedelta(days=1)).date())
        weather = v14.fetch_weather_api(
            train_full["sale_date"].min().strftime("%Y-%m-%d"),
            h_end,
            known_cutoff=cutoff,
        )
        print(f"  Weather cutoff: {cutoff} (no leakage)")

        # v13
        w13, _ = run_holdout(v13, "V13", train_full, holiday_set, weather, h_start, h_end)
        results.setdefault("v13", []).append(w13)

        # v14
        w14, _ = run_holdout(v14, "V14", train_full, holiday_set, weather, h_start, h_end)
        results.setdefault("v14", []).append(w14)

        delta = w14 - w13
        sign  = "↓" if delta < 0 else "↑"
        print(f"  >>> {label}: v13={w13:.3f}%  v14={w14:.3f}%  Δ={delta:+.3f}% {sign}")

    # ── ИТОГОВАЯ ТАБЛИЦА ─────────────────────────────────────
    print(f"\n{'='*60}")
    print("ИТОГ по всем holdout-окнам")
    print("=" * 60)

    header = f"{'Окно':<30} {'v13':>8} {'v14':>8} {'Δ':>8}"
    print(header)
    print("-" * 60)

    w13_all = results["v13"]
    w14_all = results["v14"]

    for i, (_, _, label) in enumerate(HOLDOUTS):
        d = w14_all[i] - w13_all[i]
        s = "↓" if d < 0 else "↑"
        print(f"  {label:<28} {w13_all[i]:>7.3f}% {w14_all[i]:>7.3f}% {d:>+7.3f}% {s}")

    print("-" * 60)
    avg13 = np.mean(w13_all)
    avg14 = np.mean(w14_all)
    d_avg = avg14 - avg13
    print(f"  {'СРЕДНЕЕ':<28} {avg13:>7.3f}% {avg14:>7.3f}% {d_avg:>+7.3f}%")

    wins14 = sum(w14 < w13 for w13, w14 in zip(w13_all, w14_all))
    print(f"\n  v14 лучше на {wins14}/{len(HOLDOUTS)} окнах")
    print(f"\n{'='*60}")
    if d_avg < 0:
        print(f"✓ v14 ЛУЧШЕ в среднем на {abs(d_avg):.3f}% — принимаем")
    else:
        print(f"✗ v14 ХУЖЕ в среднем на {abs(d_avg):.3f}% — откат к v13")
    print("=" * 60)
