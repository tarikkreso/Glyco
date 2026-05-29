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
        n_estimators=300,
        learning_rate=0.04,
        max_depth=3,
        num_leaves=7,
        min_child_samples=40,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_alpha=0.4,
        reg_lambda=0.8,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbose=-1,
    )


def _top_gain_features(model: LGBMRegressor, feature_columns: list[str]) -> list[tuple[str, float]]:
    """Return the top gain-based LightGBM feature importances."""
    gains = model.booster_.feature_importance(importance_type="gain")
    ranked = sorted(zip(feature_columns, gains), key=lambda item: float(item[1]), reverse=True)
    return [(name, float(gain)) for name, gain in ranked[:10]]


def _strategy_predictions(frame: pd.DataFrame, strategy: str) -> pd.Series:
    """Return baseline forecast predictions from already-built feature rows."""
    current = frame["glucose_current"]
    if strategy == "persistence":
        return current
    if strategy == "last_delta":
        return current + (current - frame["lag_1"])
    if strategy == "half_delta":
        return current + 0.5 * (current - frame["lag_1"])
    if strategy == "rolling_mean_6":
        return frame["roll_mean_6"]
    raise ValueError(f"Unknown forecast strategy: {strategy}")


def _regression_metrics(y_true: pd.Series, y_pred) -> dict[str, float]:
    """Compute the standard forecast metrics used across model and baselines."""
    y_pred_series = pd.Series(y_pred, index=y_true.index)
    valid = np.isfinite(y_true) & np.isfinite(y_pred_series)
    if not bool(valid.any()):
        raise ValueError("Cannot compute forecast metrics without finite prediction pairs.")
    return {
        "mae": float(mean_absolute_error(y_true[valid], y_pred_series[valid])),
        "rmse": float(np.sqrt(mean_squared_error(y_true[valid], y_pred_series[valid]))),
        "r2": float(r2_score(y_true[valid], y_pred_series[valid])),
    }


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
    model_metrics_per_horizon: dict[str, dict[str, float]] = {}
    baseline_metrics_per_horizon: dict[str, dict[str, dict[str, float]]] = {}
    deployment_strategy_per_horizon: dict[str, str] = {}
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
        model_metrics = _regression_metrics(y_test, predictions)
        baselines = {
            strategy: _regression_metrics(y_test, _strategy_predictions(test_df, strategy))
            for strategy in ("persistence", "last_delta", "half_delta", "rolling_mean_6")
        }
        candidates = {"lgbm": model_metrics, **baselines}
        selected_strategy, selected_metrics = min(candidates.items(), key=lambda item: item[1]["mae"])
        mae = selected_metrics["mae"]
        rmse = selected_metrics["rmse"]
        r2 = selected_metrics["r2"]
        mae_per_horizon[str(horizon)] = mae
        rmse_per_horizon[str(horizon)] = rmse
        r2_per_horizon[str(horizon)] = r2
        model_metrics_per_horizon[str(horizon)] = model_metrics
        baseline_metrics_per_horizon[str(horizon)] = baselines
        deployment_strategy_per_horizon[str(horizon)] = selected_strategy
        print(f"{horizon} min MAE={mae:.3f} RMSE={rmse:.3f} R2={r2:.3f}")
        print(f"Selected deployment strategy for {horizon} min: {selected_strategy}")
        print(f"Top 10 gain features for {horizon} min:")
        for name, gain in _top_gain_features(model, feature_columns):
            print(f"  {name}: {gain:.2f}")
        joblib.dump(model, ARTIFACTS_DIR / f"forecast_model_{horizon}min.pkl")

    metadata = {
        "model_version": "hybrid-lgbm-baseline-forecast-0.3",
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "shift_steps": feature_metadata["shift_steps"],
        "median_interval_minutes": float(feature_metadata["median_interval_minutes"]),
        "horizons_minutes": HORIZONS,
        "mae_per_horizon": mae_per_horizon,
        "rmse_per_horizon": rmse_per_horizon,
        "r2_per_horizon": r2_per_horizon,
        "model_metrics_per_horizon": model_metrics_per_horizon,
        "baseline_metrics_per_horizon": baseline_metrics_per_horizon,
        "deployment_strategy_per_horizon": deployment_strategy_per_horizon,
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
