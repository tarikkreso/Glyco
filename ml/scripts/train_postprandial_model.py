from __future__ import annotations

# Requirements: numpy, pandas, joblib, scikit-learn, lightgbm.

import json
import io
import re
import struct
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator
import zlib

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = ROOT / "data" / "raw" / "postprandial_glucose" / "dexcom_binned_prediction.npz"
FULL_CGMACROS_ARCHIVE = ROOT / "data" / "raw" / "CGMacros_dateshifted365.zip"
PROCESSED_DIR = ROOT / "data" / "processed"
ARTIFACTS_DIR = ROOT / "ml" / "artifacts"
FEATURE_PATH = PROCESSED_DIR / "postprandial_features.csv"
METADATA_PATH = ARTIFACTS_DIR / "postprandial_forecast_metadata.json"
HORIZONS = [30, 60, 120]
DIAGNOSIS_T2D = 2
RANDOM_STATE = 42
MEAL_TARGET_TOLERANCE_MINUTES = 20


def _iter_local_cgmacros_csvs() -> Iterator[tuple[str, bytes]]:
    """Yield participant CSV files by scanning local ZIP headers directly."""
    with FULL_CGMACROS_ARCHIVE.open("rb") as handle:
        position = 0
        while True:
            handle.seek(position)
            if handle.read(4) != b"PK\x03\x04":
                break
            header = handle.read(26)
            if len(header) != 26:
                break
            _, _, compression, _, _, _, compressed_size, _, name_len, extra_len = struct.unpack("<HHHHHIIIHH", header)
            name = handle.read(name_len).decode("utf-8", errors="replace")
            handle.read(extra_len)
            data_position = handle.tell()
            if name.endswith(".csv") and re.search(r"CGMacros-\d{3}/CGMacros-\d{3}\.csv$", name):
                payload = handle.read(compressed_size)
                if compression == 8:
                    # CGMacros stores raw deflate streams in local headers.
                    payload = zlib.decompress(payload, -15)
                yield name, payload
            position = data_position + compressed_size


def _nearest_glucose(series: pd.Series, timestamp: pd.Timestamp, tolerance_minutes: int) -> float | None:
    """Return the nearest glucose value around a target timestamp within tolerance."""
    if series.empty:
        return None
    indexer = series.index.get_indexer([timestamp], method="nearest", tolerance=pd.Timedelta(minutes=tolerance_minutes))
    if indexer[0] < 0:
        return None
    value = series.iloc[int(indexer[0])]
    return None if pd.isna(value) else float(value)


def _meal_value(row: pd.Series, column: str) -> float:
    """Return a numeric meal field value with missing entries treated as zero."""
    value = row.get(column, 0.0)
    return 0.0 if pd.isna(value) else float(value)


def _meal_rows_from_participant(name: str, payload: bytes) -> list[dict[str, float | int | str]]:
    """Create post-meal supervised rows from one full CGMacros participant CSV."""
    participant = re.search(r"(CGMacros-\d{3})", name)
    participant_id = participant.group(1) if participant else Path(name).stem
    df = pd.read_csv(io.BytesIO(payload))
    df.columns = [str(column).strip() for column in df.columns]
    if "Timestamp" not in df:
        return []
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    for column in ("Dexcom GL", "Libre GL", "Calories", "Carbs", "Protein", "Fat", "Fiber"):
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    glucose_column = "Dexcom GL" if "Dexcom GL" in df and df["Dexcom GL"].notna().sum() else "Libre GL"
    glucose = df.dropna(subset=["Timestamp", glucose_column]).sort_values("Timestamp").set_index("Timestamp")[glucose_column] / 18.015
    meal_mask = pd.Series(False, index=df.index)
    if "Meal Type" in df:
        meal_mask = meal_mask | df["Meal Type"].notna()
    for column in ("Calories", "Carbs"):
        if column in df:
            meal_mask = meal_mask | df[column].fillna(0).gt(0)
    rows: list[dict[str, float | int | str]] = []
    for _, meal in df.loc[meal_mask].dropna(subset=["Timestamp"]).iterrows():
        meal_time = pd.Timestamp(meal["Timestamp"])
        current = _nearest_glucose(glucose, meal_time, MEAL_TARGET_TOLERANCE_MINUTES)
        target_values = {
            horizon: _nearest_glucose(glucose, meal_time + pd.Timedelta(minutes=horizon), MEAL_TARGET_TOLERANCE_MINUTES)
            for horizon in HORIZONS
        }
        if current is None or any(value is None for value in target_values.values()):
            continue
        prior_30 = _nearest_glucose(glucose, meal_time - pd.Timedelta(minutes=30), 20) or current
        prior_60 = _nearest_glucose(glucose, meal_time - pd.Timedelta(minutes=60), 20) or prior_30
        rows.append(
            {
                "participant_id": participant_id,
                "diagnosis": DIAGNOSIS_T2D,
                "glucose_current": current,
                "glucose_lag_30min": prior_30,
                "glucose_lag_60min": prior_60,
                "premeal_roc_30": current - prior_30,
                "premeal_roc_60": current - prior_60,
                "meal_calories": _meal_value(meal, "Calories"),
                "meal_carbs": _meal_value(meal, "Carbs"),
                "meal_protein": _meal_value(meal, "Protein"),
                "meal_fat": _meal_value(meal, "Fat"),
                "meal_fiber": _meal_value(meal, "Fiber"),
                "hour_of_day": float(meal_time.hour),
                "time_of_day_sin": float(np.sin(2 * np.pi * meal_time.hour / 24)),
                "time_of_day_cos": float(np.cos(2 * np.pi * meal_time.hour / 24)),
                "is_fasting": 0.0,
                "last_reading_is_post_meal": 1.0,
                "minutes_since_last_post_meal": 0.0,
                "recent_post_meal_readings_4h": 1.0,
                "post_meal_delta": 0.0,
                **{f"target_{horizon}min": float(target_values[horizon]) for horizon in HORIZONS},
            }
        )
    return rows


def _dataset_source_metadata(source: str, rows: int, csv_count: int = 0) -> dict[str, object]:
    """Describe whether the full CGMacros archive is available for training."""
    if not FULL_CGMACROS_ARCHIVE.exists():
        return {"dataset_source": "fallback_npz", "full_archive_valid": False, "reason": "full archive missing"}
    if not zipfile.is_zipfile(FULL_CGMACROS_ARCHIVE):
        return {
            "dataset_source": "fallback_npz",
            "full_archive_valid": False,
            "full_archive_size_bytes": FULL_CGMACROS_ARCHIVE.stat().st_size,
            "reason": "full archive is incomplete or invalid",
        }
    local_csvs = [name for name, _ in _iter_local_cgmacros_csvs()]
    return {
        "dataset_source": source,
        "full_archive_valid": True,
        "full_archive_size_bytes": FULL_CGMACROS_ARCHIVE.stat().st_size,
        "full_archive_csv_entries": csv_count or len(local_csvs),
        "full_archive_sample": local_csvs[:20],
        "training_rows": rows,
        "reason": "trained from recovered full CGMacros participant CSVs" if source == "full_cgmacros_archive" else "full archive unavailable for direct training; fallback NPZ used",
    }


def _flatten_full_archive_dataset() -> tuple[pd.DataFrame, list[str], list[str], dict[str, object]] | None:
    """Build postprandial training rows directly from the full CGMacros archive."""
    if not FULL_CGMACROS_ARCHIVE.exists() or not zipfile.is_zipfile(FULL_CGMACROS_ARCHIVE):
        return None
    frames: list[dict[str, float | int | str]] = []
    csv_count = 0
    for name, payload in _iter_local_cgmacros_csvs():
        csv_count += 1
        frames.extend(_meal_rows_from_participant(name, payload))
    if not frames:
        return None
    df = pd.DataFrame(frames)
    target_columns = [f"target_{horizon}min" for horizon in HORIZONS]
    feature_columns = [column for column in df.columns if column not in {"participant_id", "diagnosis", *target_columns}]
    metadata = _dataset_source_metadata("full_cgmacros_archive", len(df), csv_count)
    return df, feature_columns, target_columns, metadata


def _flatten_dataset() -> tuple[pd.DataFrame, list[str], list[str]]:
    """Flatten the preprocessed CGMacros meal windows into tabular features."""
    data = np.load(RAW_PATH, allow_pickle=True)
    temporal = data["X"]
    static = data["static"]
    targets = data["y"] / 18.015
    participant_ids = data["participant_id"].astype(str)
    diagnosis = data["diagnosis"].astype(int)
    rows: list[dict[str, float | int | str]] = []
    for index in range(len(participant_ids)):
        row: dict[str, float | int | str] = {
            "participant_id": participant_ids[index],
            "diagnosis": int(diagnosis[index]),
        }
        for step in range(temporal.shape[1]):
            for channel in range(temporal.shape[2]):
                row[f"temporal_{step}_{channel}"] = float(temporal[index, step, channel])
        for column in range(static.shape[1]):
            row[f"static_{column}"] = float(static[index, column])
        for target_index, horizon in enumerate(HORIZONS):
            row[f"target_{horizon}min"] = float(targets[index, target_index])
        rows.append(row)
    df = pd.DataFrame(rows)
    feature_columns = [column for column in df.columns if column.startswith("temporal_") or column.startswith("static_")]
    target_columns = [f"target_{horizon}min" for horizon in HORIZONS]
    return df, feature_columns, target_columns


def _load_training_dataset() -> tuple[pd.DataFrame, list[str], list[str], dict[str, object]]:
    """Prefer the full CGMacros archive and fall back to the normalized NPZ."""
    full = _flatten_full_archive_dataset()
    if full is not None:
        return full
    df, feature_columns, target_columns = _flatten_dataset()
    return df, feature_columns, target_columns, _dataset_source_metadata("fallback_npz", len(df))


def _patient_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
    """Hold out a deterministic participant subset for patient-level testing."""
    patients = sorted(str(patient) for patient in df["participant_id"].unique())
    rng = np.random.default_rng(RANDOM_STATE)
    shuffled = list(rng.permutation(patients))
    test_count = max(1, round(len(shuffled) * 0.2))
    test_patients = sorted(shuffled[:test_count])
    train_patients = sorted(patient for patient in patients if patient not in test_patients)
    train_df = df[df["participant_id"].isin(train_patients)].copy()
    test_df = df[df["participant_id"].isin(test_patients)].copy()
    return train_df, test_df, train_patients, test_patients


def _model() -> LGBMRegressor:
    """Create the configured LightGBM regressor for post-meal horizons."""
    return LGBMRegressor(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=4,
        num_leaves=15,
        min_child_samples=8,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_alpha=0.1,
        reg_lambda=0.2,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbose=-1,
    )


def _t2d_drift_metadata(df: pd.DataFrame) -> dict[str, float]:
    """Derive Type 2 post-meal population drift ratios for sparse app forecasts."""
    t2d = df[df["diagnosis"] == DIAGNOSIS_T2D].copy()
    if t2d.empty:
        t2d = df.copy()
    baseline = t2d["target_30min"].replace(0, np.nan)
    ratios = {
        "60": float((t2d["target_60min"] / baseline).median()),
        "120": float((t2d["target_120min"] / baseline).median()),
    }
    # CGMacros provides 30/60/120 minute meal targets; 180/240 are conservative extrapolations.
    ratios["180"] = max(0.90, ratios["120"] - 0.03)
    ratios["240"] = max(0.88, ratios["120"] - 0.05)
    ratios["30"] = 1.0
    return ratios


def train_postprandial_models() -> dict[str, object]:
    """Train CGMacros-derived postprandial LightGBM models and metadata."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    df, feature_columns, target_columns, source_metadata = _load_training_dataset()
    df.to_csv(FEATURE_PATH, index=False)
    train_df, test_df, train_patients, test_patients = _patient_split(df)
    print(f"Postprandial rows: {len(df)}; test patients: {test_patients}")

    mae_per_horizon: dict[str, float] = {}
    rmse_per_horizon: dict[str, float] = {}
    r2_per_horizon: dict[str, float] = {}
    for horizon in HORIZONS:
        target = f"target_{horizon}min"
        model = _model()
        model.fit(train_df[feature_columns], train_df[target])
        predictions = model.predict(test_df[feature_columns])
        mae = float(mean_absolute_error(test_df[target], predictions))
        rmse = float(np.sqrt(mean_squared_error(test_df[target], predictions)))
        r2 = float(r2_score(test_df[target], predictions))
        mae_per_horizon[str(horizon)] = mae
        rmse_per_horizon[str(horizon)] = rmse
        r2_per_horizon[str(horizon)] = r2
        print(f"{horizon} min postprandial MAE={mae:.3f} RMSE={rmse:.3f} R2={r2:.3f}")
        joblib.dump(model, ARTIFACTS_DIR / f"postprandial_model_{horizon}min.pkl")

    metadata = {
        "model_version": "cgmacros-postprandial-lgbm-0.2",
        "source": "ULM-DS-Lab/postprandial-glucose derived from CGMacros PhysioNet v1.0.0",
        **source_metadata,
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "horizons_minutes": HORIZONS,
        "mae_per_horizon": mae_per_horizon,
        "rmse_per_horizon": rmse_per_horizon,
        "r2_per_horizon": r2_per_horizon,
        "trained_on_patients": train_patients,
        "tested_on_patients": test_patients,
        "diagnosis_counts": {str(key): int(value) for key, value in df["diagnosis"].value_counts().sort_index().items()},
        "t2d_postmeal_drift_ratios": _t2d_drift_metadata(df),
        "training_date": datetime.now(UTC).isoformat(),
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    """Run postprandial model training from the CGMacros-derived NPZ."""
    metadata = train_postprandial_models()
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
