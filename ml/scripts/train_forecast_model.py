from __future__ import annotations

# Requirements: pandas, numpy, joblib, scikit-learn, lightgbm.

import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
ARTIFACTS_DIR = ROOT / "ml" / "artifacts"
FEATURE_PATH = PROCESSED_DIR / "cgm_features.csv"
FEATURE_METADATA_PATH = PROCESSED_DIR / "forecast_feature_metadata.json"
FORECAST_METADATA_PATH = ARTIFACTS_DIR / "forecast_metadata.json"
HORIZONS = [60, 120, 180, 240]
RANDOM_STATE = 42


def _patient_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
    """Split forecast rows by patient so test data is patient-held-out."""
    patients = sorted(str(patient) for patient in df["patient_id"].unique())
    if len(patients) <= 5:
        test_patients = [patients[-1]]
        train_patients = patients[:-1]
    else:
        train_patients, test_patients = train_test_split(patients, test_size=0.2, random_state=RANDOM_STATE)
    train_df = df[df["patient_id"].astype(str).isin(train_patients)].copy()
    test_df = df[df["patient_id"].astype(str).isin(test_patients)].copy()
    return train_df, test_df, sorted(train_patients), sorted(test_patients)


def _model() -> LGBMRegressor:
    """Create the configured LightGBM regressor for every forecast horizon."""
    return LGBMRegressor(
        n_estimators=500,
        learning_rate=0.05,
        max_depth=6,
        num_leaves=31,
        min_child_samples=5,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=0.1,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )


def _top_gain_features(model: LGBMRegressor, feature_columns: list[str]) -> list[tuple[str, float]]:
    """Return the top gain-based LightGBM feature importances."""
    gains = model.booster_.feature_importance(importance_type="gain")
    ranked = sorted(zip(feature_columns, gains), key=lambda item: float(item[1]), reverse=True)
    return [(name, float(gain)) for name, gain in ranked[:10]]


def train_forecast_models() -> dict[str, object]:
    """Train one LightGBM model for each requested forecast horizon."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(FEATURE_PATH)
    feature_metadata = json.loads(FEATURE_METADATA_PATH.read_text(encoding="utf-8"))
    feature_columns = list(feature_metadata["feature_columns"])
    target_columns = list(feature_metadata["target_columns"])
    train_df, test_df, train_patients, test_patients = _patient_split(df)
    print(f"Test patients: {test_patients}")

    mae_per_horizon: dict[str, float] = {}
    rmse_per_horizon: dict[str, float] = {}
    r2_per_horizon: dict[str, float] = {}
    for horizon in HORIZONS:
        target = f"target_{horizon}min"
        if target not in target_columns:
            raise ValueError(f"Missing target column from metadata: {target}")
        model = _model()
        x_train = train_df[feature_columns]
        y_train = train_df[target]
        x_test = test_df[feature_columns]
        y_test = test_df[target]
        model.fit(x_train, y_train)
        predictions = model.predict(x_test)
        mae = float(mean_absolute_error(y_test, predictions))
        rmse = float(np.sqrt(mean_squared_error(y_test, predictions)))
        r2 = float(r2_score(y_test, predictions))
        mae_per_horizon[str(horizon)] = mae
        rmse_per_horizon[str(horizon)] = rmse
        r2_per_horizon[str(horizon)] = r2
        print(f"{horizon} min MAE={mae:.3f} RMSE={rmse:.3f} R2={r2:.3f}")
        print(f"Top 10 gain features for {horizon} min:")
        for name, gain in _top_gain_features(model, feature_columns):
            print(f"  {name}: {gain:.2f}")
        joblib.dump(model, ARTIFACTS_DIR / f"forecast_model_{horizon}min.pkl")

    metadata = {
        "model_version": "lgbm-forecast-0.2",
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "shift_steps": feature_metadata["shift_steps"],
        "median_interval_minutes": float(feature_metadata["median_interval_minutes"]),
        "horizons_minutes": HORIZONS,
        "mae_per_horizon": mae_per_horizon,
        "rmse_per_horizon": rmse_per_horizon,
        "r2_per_horizon": r2_per_horizon,
        "trained_on_patients": train_patients,
        "tested_on_patients": test_patients,
        "training_date": datetime.now(UTC).isoformat(),
        "glucose_thresholds": {
            "hypo_mmol": 3.9,
            "target_low_mmol": 4.0,
            "target_high_mmol": 10.0,
            "hyper_mmol": 13.9,
        },
    }
    FORECAST_METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    """Run the forecast model training command-line entry point."""
    metadata = train_forecast_models()
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
