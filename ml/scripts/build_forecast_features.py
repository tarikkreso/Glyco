from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
CLEAN_PATH = PROCESSED_DIR / "cgm_clean.csv"
FEATURE_PATH = PROCESSED_DIR / "cgm_features.csv"
METADATA_PATH = PROCESSED_DIR / "forecast_feature_metadata.json"

LAG_STEPS = [1, 2, 3, 4, 6, 8, 12]
TARGET_HORIZONS = [60, 120, 180, 240]


def _median_interval_minutes(df: pd.DataFrame) -> float:
    """Compute the median inter-reading interval across all patients."""
    deltas = (
        df.sort_values(["patient_id", "timestamp"])
        .groupby("patient_id")["timestamp"]
        .diff()
        .dropna()
        .dt.total_seconds()
        .div(60.0)
    )
    return float(deltas.median()) if not deltas.empty else 60.0


def _shift_steps(median_interval_minutes: float) -> dict[str, int]:
    """Map target horizons in minutes to patient-reading shift counts."""
    return {
        str(horizon): max(1, round(horizon / median_interval_minutes))
        for horizon in TARGET_HORIZONS
    }


def _build_patient_features(patient_df: pd.DataFrame, shifts: dict[str, int]) -> pd.DataFrame:
    """Build lag, rate, rolling, time, context, and target features for one patient."""
    rows = patient_df.sort_values("timestamp").copy()
    glucose = rows["glucose_mmol"]
    for lag in LAG_STEPS:
        rows[f"lag_{lag}"] = glucose.shift(lag)
    rows["roc_1"] = rows["glucose_mmol"] - rows["lag_1"]
    rows["roc_2"] = rows["glucose_mmol"] - rows["lag_2"]
    rows["roc_3"] = rows["lag_1"] - rows["lag_3"]
    rows["acceleration"] = rows["roc_1"] - rows["roc_2"]
    rows["roll_mean_6"] = glucose.rolling(6).mean()
    rows["roll_std_6"] = glucose.rolling(6).std()
    rows["roll_min_6"] = glucose.rolling(6).min()
    rows["roll_max_6"] = glucose.rolling(6).max()
    rows["roll_range_6"] = rows["roll_max_6"] - rows["roll_min_6"]
    rows["roll_mean_12"] = glucose.rolling(12).mean()
    rows["roll_std_12"] = glucose.rolling(12).std()
    rows["glucose_current"] = rows["glucose_mmol"]
    for horizon, shift in shifts.items():
        rows[f"target_{horizon}min"] = glucose.shift(-shift)
    return rows


def build_forecast_features() -> dict[str, object]:
    """Create supervised forecast rows from the cleaned CGM table."""
    df = pd.read_csv(CLEAN_PATH, parse_dates=["timestamp"])
    median_interval = _median_interval_minutes(df)
    shifts = _shift_steps(median_interval)
    lag_minutes = {f"lag_{lag}": round(lag * median_interval, 2) for lag in LAG_STEPS}
    print(f"Median interval minutes: {median_interval:.2f}")
    print(f"Lag interpretation for this dataset: {lag_minutes}")

    frames = [_build_patient_features(patient_df, shifts) for _, patient_df in df.groupby("patient_id", sort=True)]
    features = pd.concat(frames, ignore_index=True)
    lag_columns = [f"lag_{lag}" for lag in LAG_STEPS]
    target_columns = [f"target_{horizon}min" for horizon in TARGET_HORIZONS]
    feature_columns = [
        *lag_columns,
        "roc_1",
        "roc_2",
        "roc_3",
        "acceleration",
        "roll_mean_6",
        "roll_std_6",
        "roll_min_6",
        "roll_max_6",
        "roll_range_6",
        "roll_mean_12",
        "roll_std_12",
        "hour_of_day",
        "time_of_day_sin",
        "time_of_day_cos",
        "day_of_week",
        "is_weekend",
        "patient_baseline_offset",
        "glucose_current",
    ]
    before_drop = len(features)
    features = features.dropna(subset=lag_columns + target_columns).copy()
    dropped_nan = int(before_drop - len(features))
    features.to_csv(FEATURE_PATH, index=False)

    print(f"Final feature count: {len(features)}")
    print(f"Feature columns: {feature_columns}")
    print("Target distribution stats per horizon:")
    for target in target_columns:
        print(target)
        print(features[target].describe())
    print(f"Rows dropped due to NaN: {dropped_nan}")

    metadata = {
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "shift_steps": shifts,
        "median_interval_minutes": median_interval,
        "n_patients": int(features["patient_id"].nunique()),
        "n_rows": int(len(features)),
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    """Run the forecast feature engineering command-line entry point."""
    metadata = build_forecast_features()
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
