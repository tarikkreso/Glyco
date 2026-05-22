from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = ROOT / "data" / "raw" / "iglu_t2d_cgm.csv"
PROCESSED_DIR = ROOT / "data" / "processed"
CLEAN_PATH = PROCESSED_DIR / "cgm_clean.csv"
REPORT_PATH = PROCESSED_DIR / "cgm_cleaning_report.json"


def _infer_standard_columns(df: pd.DataFrame) -> dict[str, str]:
    """Infer raw patient, timestamp, and glucose columns from the loaded CSV."""
    lower_map = {column.lower(): column for column in df.columns}
    patient_candidates = ["patient_id", "id", "subject", "subject_id"]
    timestamp_candidates = ["timestamp", "time", "datetime", "date_time"]
    glucose_candidates = ["glucose_mgdl", "gl", "glucose", "value"]
    inferred: dict[str, str] = {}
    for standard, candidates in {
        "patient_id": patient_candidates,
        "timestamp": timestamp_candidates,
        "glucose_mgdl": glucose_candidates,
    }.items():
        for candidate in candidates:
            if candidate in lower_map:
                inferred[lower_map[candidate]] = standard
                break
        if standard not in inferred.values():
            raise ValueError(f"Could not infer required column for {standard}; found {list(df.columns)}")
    return inferred


def _interval_summary(df: pd.DataFrame) -> tuple[float, float, float]:
    """Return median, 95th percentile, and maximum inter-reading gap in minutes."""
    deltas = (
        df.sort_values(["patient_id", "timestamp"])
        .groupby("patient_id")["timestamp"]
        .diff()
        .dropna()
        .dt.total_seconds()
        .div(60.0)
    )
    if deltas.empty:
        return 0.0, 0.0, 0.0
    return float(deltas.median()), float(deltas.quantile(0.95)), float(deltas.max())


def _resample_patient(patient_df: pd.DataFrame) -> pd.DataFrame:
    """Resample one patient's dense CGM readings to a regular 5-minute grid."""
    patient_id = patient_df["patient_id"].iloc[0]
    indexed = patient_df.set_index("timestamp").sort_index()
    grid = indexed[["glucose_mgdl", "glucose_mmol"]].resample("5min").mean()
    grid["patient_id"] = patient_id
    # A 5-minute grid has four intervals in 20 minutes, so limit=4 keeps only short gaps filled.
    grid[["glucose_mgdl", "glucose_mmol"]] = grid[["glucose_mgdl", "glucose_mmol"]].ffill(limit=4)
    return grid.reset_index()


def _add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add cyclical and calendar features derived from the reading timestamp."""
    result = df.copy()
    result["hour_of_day"] = result["timestamp"].dt.hour.astype(int)
    result["minute_of_day"] = (result["timestamp"].dt.hour * 60 + result["timestamp"].dt.minute).astype(int)
    result["day_of_week"] = result["timestamp"].dt.dayofweek.astype(int)
    result["is_weekend"] = result["day_of_week"].isin([5, 6])
    result["time_of_day_sin"] = np.sin(2 * np.pi * result["hour_of_day"] / 24)
    result["time_of_day_cos"] = np.cos(2 * np.pi * result["hour_of_day"] / 24)
    return result


def _add_patient_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """Join full-history patient glucose statistics back to each reading row."""
    global_mean = float(df["glucose_mmol"].mean())
    stats = (
        df.groupby("patient_id")["glucose_mmol"]
        .agg(patient_mean_glucose="mean", patient_std_glucose="std")
        .reset_index()
    )
    stats["patient_std_glucose"] = stats["patient_std_glucose"].fillna(0.0)
    stats["patient_baseline_offset"] = stats["patient_mean_glucose"] - global_mean
    return df.merge(stats, on="patient_id", how="left")


def clean_cgm_data() -> dict[str, object]:
    """Clean the raw iglu Type 2 CGM export and write processed artifacts."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(RAW_PATH)
    original_rows = int(len(df))
    print(f"Shape before cleaning: {df.shape}")

    rename_map = _infer_standard_columns(df)
    df = df.rename(columns=rename_map)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=False)
    df = df.dropna(subset=["timestamp"]).copy()
    df["glucose_mgdl"] = pd.to_numeric(df["glucose_mgdl"], errors="coerce")
    df = df.dropna(subset=["glucose_mgdl"]).copy()
    df = df.sort_values(["patient_id", "timestamp"]).reset_index(drop=True)

    glucose_mean = float(df["glucose_mgdl"].mean())
    if glucose_mean > 50:
        df["glucose_mmol"] = df["glucose_mgdl"] / 18.015
    else:
        # The source is already in mmol/L, so preserve it while still keeping the standard column.
        df["glucose_mmol"] = df["glucose_mgdl"]

    before_possible = len(df)
    df = df[(df["glucose_mmol"] >= 1.5) & (df["glucose_mmol"] <= 30.0)].copy()
    dropped_impossible = int(before_possible - len(df))
    print(f"Dropped physiologically impossible values: {dropped_impossible}")

    before_duplicates = len(df)
    df = df.drop_duplicates(subset=["patient_id", "timestamp"], keep="first").copy()
    dropped_duplicates = int(before_duplicates - len(df))
    print(f"Dropped duplicate patient/timestamp rows: {dropped_duplicates}")

    median_interval, p95_interval, max_gap = _interval_summary(df)
    print(
        "Interval summary minutes: "
        f"median={median_interval:.2f}, p95={p95_interval:.2f}, max_gap={max_gap:.2f}"
    )
    if median_interval < 10:
        frames = [_resample_patient(patient_df) for _, patient_df in df.groupby("patient_id", sort=True)]
        df = pd.concat(frames, ignore_index=True).sort_values(["patient_id", "timestamp"]).reset_index(drop=True)
    else:
        # Manual logging intervals are sparse enough that resampling would invent too much structure.
        print("Median interval is >= 10 minutes; keeping manual logging cadence without resampling.")

    df = _add_time_features(df)
    df = _add_patient_statistics(df)

    final_null_counts = df.isna().sum()
    per_patient_counts = df.groupby("patient_id").size()
    print(f"Final shape: {df.shape}")
    print("Final null counts:")
    print(final_null_counts)
    print("Per-patient row counts:")
    print(per_patient_counts)

    df.to_csv(CLEAN_PATH, index=False)
    report = {
        "original_rows": original_rows,
        "final_rows": int(len(df)),
        "dropped_impossible_values": dropped_impossible,
        "dropped_duplicates": dropped_duplicates,
        "patients": int(df["patient_id"].nunique()),
        "median_interval_minutes": median_interval,
        "glucose_mean_mmol": float(df["glucose_mmol"].mean()),
        "glucose_std_mmol": float(df["glucose_mmol"].std()),
        "glucose_min_mmol": float(df["glucose_mmol"].min()),
        "glucose_max_mmol": float(df["glucose_mmol"].max()),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    """Run the CGM cleaning command-line entry point."""
    report = clean_cgm_data()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
