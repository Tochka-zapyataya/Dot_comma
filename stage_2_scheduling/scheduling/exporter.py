import json
import logging
from collections import defaultdict
from pathlib import Path

import pandas as pd

from . import config


logger = logging.getLogger(__name__)


def export_all(
    schedule_df: pd.DataFrame | None,
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    validation: dict,
    diagnostics: dict,
    forecast_df: pd.DataFrame,
    forecast_meta: dict,
    output_dir: Path | None = None,
    write_final_schedule_csv_xlsx: bool = True,
) -> None:
    out = output_dir or config.OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    stale_final_names = (
        "schedule.xlsx",
        "schedule.csv",
        "coverage_heatmap.csv",
        "employee_summary.csv",
        "timeline.json",
    )
    if not write_final_schedule_csv_xlsx:
        for fn in stale_final_names:
            p = out / fn
            if p.exists():
                p.unlink()

    sd = schedule_df
    sel_keys = (
        _schedule_selected_keys(sd) if sd is not None and not sd.empty else set()
    )

    requirements_df.to_csv(out / "requirements.csv", index=False)

    cands_export = candidates_df.copy()
    keys_c = list(zip(
        cands_export["ds"].astype(str),
        cands_export["station_key"].astype(str),
        cands_export["employee_id"].astype(int),
        cands_export["starttime"].astype(int),
        cands_export["finishtime"].astype(int),
    ))
    sf = [t in sel_keys for t in keys_c]
    cands_export["selected"] = [int(v) for v in sf]
    cands_export["selected_final"] = sf
    cands_export.to_csv(out / "candidates.csv", index=False)

    if sd is None or sd.empty:
        pass
    elif write_final_schedule_csv_xlsx:
        final = sd[["ds", "station_key", "employee_id", "starttime", "finishtime"]].copy()
        final.to_excel(out / "schedule.xlsx", index=False)
        final.to_csv(out / "schedule.csv", index=False)

        coverage_df = _build_coverage_heatmap(sd, requirements_df)
        coverage_df.to_csv(out / "coverage_heatmap.csv", index=False)

        employee_summary = _build_employee_summary(
            sd, requirements_df, candidates_df, forecast_df
        )
        employee_summary.to_csv(out / "employee_summary.csv", index=False)

        timeline = _build_timeline_json(sd, requirements_df, forecast_df)
        _save_json(timeline, out / "timeline.json")

    _save_json(validation, out / "validation_report.json")

    full_diag = {**diagnostics, "forecast_metadata": forecast_meta}
    _save_json(full_diag, out / "diagnostics.json")

    if write_final_schedule_csv_xlsx:
        logger.info("Exported FINAL schedule artifacts to %s", out)
    else:
        logger.info("Exported without final schedule.xlsx (invalid CP-SAT) to %s", out)



def _schedule_selected_keys(df: pd.DataFrame) -> set[tuple]:
    return set(zip(
        df["ds"].astype(str),
        df["station_key"].astype(str),
        df["employee_id"].astype(int),
        df["starttime"].astype(int),
        df["finishtime"].astype(int),
    ))


def _build_coverage_heatmap(
    schedule_df: pd.DataFrame,
    requirements_df: pd.DataFrame,
) -> pd.DataFrame:
    actual_counts: dict[tuple[str, int, str], int] = defaultdict(int)
    for r in schedule_df.itertuples():
        for h in range(int(r.starttime), int(r.finishtime)):
            actual_counts[(str(r.ds), int(h), str(r.station_key))] += 1

    rows = []
    for r in requirements_df.itertuples():
        key = (str(r.ds), int(r.hour), str(r.station_key))
        actual = actual_counts.get(key, 0)
        req_eff = max(int(r.required_labor), 1)
        diff = actual - req_eff
        if actual < req_eff:
            status = "under"
        elif diff == 0:
            status = "exact"
        elif diff <= 2:
            status = "over"
        else:
            status = "too_much"
        rows.append({
            "ds": r.ds,
            "hour": int(r.hour),
            "station_key": r.station_key,
            "guests_count": int(r.guests_count),
            "version": r.version,
            "required": req_eff,
            "actual": actual,
            "diff": diff,
            "status": status,
        })
    return pd.DataFrame(rows)


def _build_employee_summary(
    schedule_df: pd.DataFrame,
    requirements_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
) -> pd.DataFrame:
    if schedule_df.empty:
        return pd.DataFrame(columns=[
            "employee_id", "total_hours", "working_days",
            "stations_used", "avg_shift_duration", "shifts",
        ])
    agg = schedule_df.copy()
    agg["duration"] = agg["finishtime"] - agg["starttime"]
    grouped = agg.groupby("employee_id").agg(
        total_hours=("duration", "sum"),
        working_days=("ds", "nunique"),
        shifts=("ds", "count"),
        avg_shift_duration=("duration", "mean"),
    ).reset_index()
    stations_used = (
        agg.groupby("employee_id")["station_key"]
        .agg(lambda s: ",".join(sorted(set(s))))
        .reset_index(name="stations_used")
    )
    summary = grouped.merge(stations_used, on="employee_id", how="left")
    summary["avg_shift_duration"] = summary["avg_shift_duration"].round(2)
    summary["total_hours"] = summary["total_hours"].astype(int)
    summary["working_days"] = summary["working_days"].astype(int)
    summary["shifts"] = summary["shifts"].astype(int)
    return summary


def _build_timeline_json(
    schedule_df: pd.DataFrame,
    requirements_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
) -> list:
    forecast_lookup = {
        (str(r.sale_date), int(r.sale_hour)): int(r.guests_count)
        for r in forecast_df.itertuples()
    }
    actual_index: dict[tuple[str, int, str], list[int]] = defaultdict(list)
    for r in schedule_df.itertuples():
        for h in range(int(r.starttime), int(r.finishtime)):
            actual_index[(str(r.ds), int(h), str(r.station_key))].append(int(r.employee_id))

    requirements_index: dict[tuple[str, int, str], int] = {}
    for r in requirements_df.itertuples():
        requirements_index[(str(r.ds), int(r.hour), str(r.station_key))] = max(
            int(r.required_labor), 1
        )

    out = []
    for ds in config.TARGET_DATES:
        for hour in config.HOURS:
            stations = []
            for st in config.STATIONS:
                key = (ds, hour, st)
                req = requirements_index.get(key, 1)
                emps = sorted(actual_index.get(key, []))
                actual = len(emps)
                diff = actual - req
                if actual < req:
                    status = "under"
                elif diff == 0:
                    status = "exact"
                elif diff <= 2:
                    status = "over"
                else:
                    status = "too_much"
                stations.append({
                    "station_key": st,
                    "required": req,
                    "assigned": actual,
                    "employees": emps,
                    "status": status,
                })
            out.append({
                "date": ds,
                "hour": hour,
                "guests_count": forecast_lookup.get((ds, hour), 0),
                "stations": stations,
            })
    return out


def _save_json(obj, path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=_json_default)


def _json_default(o):
    import numpy as np
    if isinstance(o, (pd.Timestamp,)):
        return o.strftime("%Y-%m-%d")
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"Object of type {type(o)} is not JSON serializable")
