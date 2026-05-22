from __future__ import annotations

# Requirements: numpy, pandas, joblib, scikit-learn, lightgbm.

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

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


def _dataset_source_metadata() -> dict[str, object]:
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
    with zipfile.ZipFile(FULL_CGMACROS_ARCHIVE) as archive:
        names = archive.namelist()
    return {
        "dataset_source": "full_cgmacros_available_fallback_parser",
        "full_archive_valid": True,
        "full_archive_size_bytes": FULL_CGMACROS_ARCHIVE.stat().st_size,
        "full_archive_entries": len(names),
        "full_archive_sample": names[:20],
        "reason": "full archive validated; current trainer still uses normalized NPZ until archive schema parser is enabled",
    }


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
    df, feature_columns, target_columns = _flatten_dataset()
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
        "model_version": "cgmacros-postprandial-lgbm-0.1",
        "source": "ULM-DS-Lab/postprandial-glucose derived from CGMacros PhysioNet v1.0.0",
        **_dataset_source_metadata(),
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
