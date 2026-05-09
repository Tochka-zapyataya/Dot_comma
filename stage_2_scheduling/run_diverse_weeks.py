#!/usr/bin/env python3
"""
Выбор 10 максимально разнесённых по датам полных недель из train.csv
и запуск пайплайна расписания для каждой (fallback-прогноз из train).

Запуск из каталога stage_2_scheduling:
  python3 run_diverse_weeks.py
  python3 run_diverse_weeks.py --variant offset --output-subdir diverse_week_runs_batch2

Режимы выборки недель (--variant):
  even   — равномерная сетка по индексу (концы диапазона включены), по умолчанию
  offset — середины 10 интервалов (другой набор недель, без общих с even при достаточном m)
  random — 10 недель (seed=42)

Результаты: output/<output-subdir>/<week_slug>/ и summary.csv

Для скорости батча временно отключается тяжёлая «батарея»
run_feasibility_diagnostics_full; лимиты CP-SAT смягчены (см. константы ниже).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _select_diverse_weeks(
    train_csv: Path,
    n: int = 10,
    variant: str = "even",
) -> list[dict]:
    """Полные недели (≥7 календарных дат в данных), n штук по выбранной схеме."""
    train = pd.read_csv(train_csv, parse_dates=["sale_date"])
    train["guests_count"] = (
        pd.to_numeric(train["guests_count"], errors="coerce").fillna(0)
    )
    train["week_period"] = train["sale_date"].dt.to_period("W-MON")
    agg = train.groupby("week_period").agg(
        total_guests=("guests_count", "sum"),
        n_days=("sale_date", pd.Series.nunique),
    ).reset_index()
    complete = agg[agg["n_days"] >= 7].copy()
    complete["monday"] = complete["week_period"].map(
        lambda p: p.start_time.strftime("%Y-%m-%d"),
    )
    complete = complete.sort_values("monday").reset_index(drop=True)
    if complete.empty:
        raise ValueError("Нет недель с 7 различными датами в train.csv.")

    m = len(complete)
    if m < n:
        raise ValueError(f"Только {m} полных недель, нужно {n}.")

    if variant == "even":
        idx = [int(round(i * (m - 1) / max(n - 1, 1))) for i in range(n)]
    elif variant == "offset":
        # середины n равных отрезка — другая «сетка», чем even
        idx = [int(round((i + 0.5) * (m - 1) / n)) for i in range(n)]
    elif variant == "random":
        rng = random.Random(42)
        idx = sorted(rng.sample(range(m), n))
    else:
        raise ValueError(f"Неизвестный variant: {variant!r}")

    idx = sorted(set(idx))
    while len(idx) < n:
        for j in range(m):
            if j not in idx:
                idx.append(j)
            if len(idx) >= n:
                break
        idx = sorted(idx)[:n]

    chosen = complete.iloc[idx]
    rows: list[dict] = []
    for _, r in chosen.iterrows():
        rows.append(
            {
                "week_period": str(r["week_period"]),
                "monday": r["monday"],
                "total_guests": float(r["total_guests"]),
                "selection_variant": variant,
            },
        )
    return rows


def _week_dates_from_monday(monday_iso: str) -> list[str]:
    start = pd.Timestamp(monday_iso)
    dr = pd.date_range(start, periods=7, freq="D")
    return [x.strftime("%Y-%m-%d") for x in dr]


def main() -> int:
    parser = argparse.ArgumentParser(description="Батч: 10 недель из train → пайплайн расписания.")
    parser.add_argument(
        "--variant",
        choices=("even", "offset", "random"),
        default="even",
        help="Схема выбора недель (offset/random — другой набор относительно even)",
    )
    parser.add_argument(
        "--output-subdir",
        default="diverse_week_runs",
        help="Подкаталог в output/ для этого прогона",
    )
    parser.add_argument(
        "-n",
        "--weeks",
        type=int,
        default=10,
        help="Сколько недель (по умолчанию 10)",
    )
    args = parser.parse_args()

    from scheduling import config
    from scheduling.data_loader import _normalize_forecast, validate_forecast
    from scheduling.forecast_fallback import build_fallback_forecast
    from scheduling.logging_config import setup_logging

    setup_logging()

    fc_path = config.LOCAL_DATA_DIR / "forecast.csv"
    backup: bytes | None = fc_path.read_bytes() if fc_path.exists() else None

    out_root = config.OUTPUT_DIR / args.output_subdir
    out_root.mkdir(parents=True, exist_ok=True)

    selected = _select_diverse_weeks(
        config.TRAIN_CSV, n=args.weeks, variant=args.variant,
    )

    import scheduling.feasibility_diagnostics as fd

    _orig_full = fd.run_feasibility_diagnostics_full

    def _fast_full(*_a, **_k):
        return {}

    fd.run_feasibility_diagnostics_full = _fast_full

    _orig_out = config.OUTPUT_DIR
    _orig_target = list(config.TARGET_DATES)
    _orig_max_t = config.MAX_TIME_SECONDS
    _orig_relaxed = config.RELAXED_FEASIBILITY_DIAGNOSTIC_SECONDS

    config.MAX_TIME_SECONDS = 120
    config.RELAXED_FEASIBILITY_DIAGNOSTIC_SECONDS = 60

    summary_rows: list[dict] = []

    try:
        from scheduling.main import main as pipeline_main

        for meta in selected:
            monday_str = meta["monday"]
            target_dates = _week_dates_from_monday(monday_str)
            week_slug = target_dates[0] + "_" + target_dates[-1]
            run_dir = out_root / week_slug
            run_dir.mkdir(parents=True, exist_ok=True)

            config.TARGET_DATES = target_dates
            config.OUTPUT_DIR = run_dir.resolve()

            forecast_df, _mf = build_fallback_forecast(
                train_csv_path=config.TRAIN_CSV,
                target_dates=config.TARGET_DATES,
                hours=config.HOURS,
                history_weeks=config.FALLBACK_HISTORY_WEEKS,
                min_rows=config.FALLBACK_MIN_ROWS,
            )
            forecast_df = _normalize_forecast(forecast_df)
            validate_forecast(forecast_df)
            fc_path.parent.mkdir(parents=True, exist_ok=True)
            forecast_df.to_csv(fc_path, index=False)

            print(f"\n=== {week_slug} | W {meta['week_period']} | hist guests≈{meta['total_guests']:.0f} ===")
            rc = pipeline_main()

            vr_path = run_dir / "validation_report.json"
            row = {
                "selection_variant": meta.get("selection_variant", args.variant),
                "week_period": meta["week_period"],
                "monday": monday_str,
                "week_slug": week_slug,
                "train_week_total_guests": meta["total_guests"],
                "exit_code": rc,
            }
            if vr_path.exists():
                rep = json.loads(vr_path.read_text(encoding="utf-8"))
                row["is_valid"] = rep.get("is_valid")
                row["errors_count"] = len(rep.get("errors") or [])
                m = rep.get("metrics") or {}
                row["solver_mode"] = m.get("solver_mode")
                row["total_shifts"] = m.get("total_shifts")
                si = m.get("solver_info") or {}
                row["feasibility_status"] = (si.get("feasibility") or {}).get("status")
                row["optimize_status"] = (si.get("optimize") or {}).get("status")
            summary_rows.append(row)

    finally:
        fd.run_feasibility_diagnostics_full = _orig_full
        config.OUTPUT_DIR = _orig_out
        config.TARGET_DATES = _orig_target
        config.MAX_TIME_SECONDS = _orig_max_t
        config.RELAXED_FEASIBILITY_DIAGNOSTIC_SECONDS = _orig_relaxed
        if backup is not None:
            fc_path.write_bytes(backup)
        elif fc_path.exists():
            fc_path.unlink()

    summary_json = out_root / "summary.json"
    summary_json.write_text(
        json.dumps(summary_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pd.DataFrame(summary_rows).to_csv(out_root / "summary.csv", index=False)
    print(f"\nГотово: {summary_json} и {out_root / 'summary.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
