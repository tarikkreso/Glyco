from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS_DIR = ROOT / "ml" / "artifacts"
HORIZONS = [60, 120, 180, 240]
DEFAULT_THRESHOLDS = {
    "hypo_mmol": 3.9,
    "target_low_mmol": 4.0,
    "target_high_mmol": 10.0,
    "hyper_mmol": 13.9,
}


def _as_mmol(value: float) -> float:
    """Normalize glucose values that may arrive from legacy mg/dL health logs."""
    return float(value) / 18.015 if float(value) > 40 else float(value)


class GlucoseForecastService:
    """
    Bridge trained LightGBM glucose forecast artifacts to Glyco backend callers.

    The service loads the four horizon models and shared metadata when present.
    If artifacts are unavailable, it returns a conservative rule-based forecast
    so product flows remain usable during local setup and demos.
    """

    def __init__(self) -> None:
        """Load forecast metadata and horizon-specific LightGBM model artifacts."""
        self.metadata: dict[str, Any] = {}
        self.models: dict[str, Any] = {}
        self.model_available = False
        self.feature_columns: list[str] = []
        self.shift_steps: dict[str, int] = {}
        self.thresholds: dict[str, float] = DEFAULT_THRESHOLDS.copy()
        self.mae_per_horizon: dict[str, float] = {str(horizon): 1.5 for horizon in HORIZONS}
        self.model_version = "rules-forecast-fallback-0.1"
        self.fallback_model_version = "rules-forecast-fallback-0.1"
        self.postprandial_metadata: dict[str, Any] = {}
        self.postprandial_available = False
        self.postprandial_model_version = "cgmacros-postprandial-population-0.1"
        self.postprandial_mae_per_horizon: dict[str, float] = {str(horizon): 1.5 for horizon in HORIZONS}
        self.postprandial_drift_ratios: dict[str, float] = {
            "60": 1.02,
            "120": 1.01,
            "180": 0.99,
            "240": 0.98,
        }
        self._load_artifacts()

    def _load_artifacts(self) -> None:
        """Load metadata and all four horizon models, logging any missing artifact."""
        metadata_path = ARTIFACTS_DIR / "forecast_metadata.json"
        failed: list[str] = []
        try:
            self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.feature_columns = list(self.metadata.get("feature_columns", []))
            self.shift_steps = {str(key): int(value) for key, value in self.metadata.get("shift_steps", {}).items()}
            self.thresholds = {**DEFAULT_THRESHOLDS, **self.metadata.get("glucose_thresholds", {})}
            self.mae_per_horizon = {
                str(key): float(value)
                for key, value in self.metadata.get("mae_per_horizon", self.mae_per_horizon).items()
            }
            self.model_version = str(self.metadata.get("model_version", self.model_version))
        except Exception as exc:
            failed.append(f"{metadata_path.name}: {exc}")

        for horizon in HORIZONS:
            path = ARTIFACTS_DIR / f"forecast_model_{horizon}min.pkl"
            try:
                self.models[str(horizon)] = joblib.load(path)
            except Exception as exc:
                failed.append(f"{path.name}: {exc}")
        self.model_available = not failed and len(self.models) == len(HORIZONS)
        if failed:
            logger.warning("Forecast artifacts unavailable: %s", "; ".join(failed))
        self._load_postprandial_metadata()

    def _load_postprandial_metadata(self) -> None:
        """Load CGMacros-derived post-meal population metadata for sparse/manual forecasts."""
        metadata_path = ARTIFACTS_DIR / "postprandial_forecast_metadata.json"
        try:
            self.postprandial_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.postprandial_model_version = (
                f"{self.postprandial_metadata.get('model_version', self.postprandial_model_version)}-population-drift"
            )
            ratios = self.postprandial_metadata.get("t2d_postmeal_drift_ratios", {})
            self.postprandial_drift_ratios = {
                str(horizon): float(ratios.get(str(horizon), self.postprandial_drift_ratios[str(horizon)]))
                for horizon in HORIZONS
            }
            mae = self.postprandial_metadata.get("mae_per_horizon", {})
            self.postprandial_mae_per_horizon = {
                "60": float(mae.get("60", 1.5)),
                "120": float(mae.get("120", 1.8)),
                # CGMacros metadata has 30/60/120-minute targets; wider intervals keep longer estimates cautious.
                "180": float(mae.get("120", 1.8)) + 0.4,
                "240": float(mae.get("120", 1.8)) + 0.7,
            }
            self.postprandial_available = True
        except Exception as exc:
            self.postprandial_available = False
            logger.warning("Postprandial forecast metadata unavailable: %s", exc)

    def _median_gap_minutes(self, logs: list[dict]) -> float | None:
        """Return the median gap between recent readings in minutes."""
        timestamps = pd.to_datetime(
            [item.get("timestamp") for item in logs if item.get("timestamp") is not None],
            errors="coerce",
            utc=False,
        )
        valid = pd.Series(timestamps).dropna().sort_values()
        if len(valid) < 2:
            return None
        gaps = valid.diff().dropna().dt.total_seconds().div(60.0)
        return float(gaps.median()) if not gaps.empty else None

    def _is_cgm_like_cadence(self, logs: list[dict]) -> bool:
        """Decide whether recent logs are dense enough for the trained CGM model."""
        median_gap = self._median_gap_minutes(logs)
        if median_gap is None:
            return False
        return median_gap < 10.0

    def _meal_context_features(self, logs: list[dict], last_timestamp: pd.Timestamp, current: float) -> dict[str, float]:
        """Build fasting and post-meal context features from recent app logs."""
        ordered = sorted(
            (
                {**item, "timestamp": pd.to_datetime(item.get("timestamp"), errors="coerce", utc=False)}
                for item in logs
            ),
            key=lambda item: item["timestamp"] if pd.notna(item["timestamp"]) else pd.Timestamp.min,
        )
        valid = [item for item in ordered if pd.notna(item["timestamp"])]
        last = valid[-1] if valid else {}
        last_is_fasting = bool(last.get("is_fasting", True))
        post_meal_logs = [item for item in valid if item.get("is_fasting") is False]
        recent_post_meal = [
            item
            for item in post_meal_logs
            if 0 <= (last_timestamp - item["timestamp"]).total_seconds() <= 4 * 60 * 60
        ]
        fasting_values = [
            _as_mmol(float(item.get("glucose_mmol", item.get("glucose_level", np.nan))))
            for item in valid
            if item.get("is_fasting") is True and pd.notna(item.get("glucose_mmol", item.get("glucose_level", np.nan)))
        ]
        last_post_time = post_meal_logs[-1]["timestamp"] if post_meal_logs else None
        minutes_since_post = 720.0
        if last_post_time is not None:
            # A capped value keeps old meals from dominating the model input scale.
            minutes_since_post = min(720.0, max(0.0, (last_timestamp - last_post_time).total_seconds() / 60.0))
        baseline = float(np.mean(fasting_values)) if fasting_values else current
        return {
            "is_fasting": float(last_is_fasting),
            "last_reading_is_post_meal": float(not last_is_fasting),
            "minutes_since_last_post_meal": float(minutes_since_post),
            "recent_post_meal_readings_4h": float(len(recent_post_meal)),
            "post_meal_delta": float(current - baseline),
        }

    def _build_feature_row(self, logs: list[dict]) -> dict[str, float] | None:
        """
        Build a single feature row from a list of recent glucose logs.

        Each log dict must have at minimum:
          - timestamp (str or datetime)
          - glucose_mmol (float)

        Returns None if there are fewer than 4 logs (insufficient history).
        Uses linear interpolation to fill missing 5-minute slots if logs
        are dense enough, otherwise uses available readings directly.
        """
        if len(logs) < 4:
            return None
        df = pd.DataFrame(logs)
        if "timestamp" not in df or "glucose_mmol" not in df:
            logger.warning("Forecast feature construction missing timestamp or glucose_mmol")
            return None
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=False)
        df["glucose_mmol"] = pd.to_numeric(df["glucose_mmol"], errors="coerce").map(_as_mmol)
        df = df.dropna(subset=["timestamp", "glucose_mmol"]).sort_values("timestamp")
        if len(df) < 4:
            return None

        series = pd.Series(df["glucose_mmol"].to_numpy(), index=df["timestamp"])
        gaps = series.index.to_series().diff().dropna().dt.total_seconds().div(60.0)
        if not gaps.empty and float(gaps.median()) < 10:
            # Dense CGM-like inputs are regularized to match the training grid.
            series = series.resample("5min").mean().interpolate(method="time").ffill(limit=4)
        values = series.dropna().astype(float)
        if len(values) < 4:
            return None

        current = float(values.iloc[-1])
        feature_row: dict[str, float] = {}
        for lag in (1, 2, 3, 4, 6, 8, 12):
            if len(values) <= lag:
                logger.warning("Not enough glucose history to compute lag_%s", lag)
                return None
            feature_row[f"lag_{lag}"] = float(values.iloc[-lag - 1])

        feature_row["roc_1"] = current - feature_row["lag_1"]
        feature_row["roc_2"] = current - feature_row["lag_2"]
        feature_row["roc_3"] = feature_row["lag_1"] - feature_row["lag_3"]
        feature_row["acceleration"] = feature_row["roc_1"] - feature_row["roc_2"]
        last_6 = values.iloc[-6:]
        last_12 = values.iloc[-12:]
        if len(last_6) < 6 or len(last_12) < 12:
            logger.warning("Not enough glucose history to compute rolling forecast features")
            return None
        feature_row["roll_mean_6"] = float(last_6.mean())
        feature_row["roll_std_6"] = float(last_6.std())
        feature_row["roll_min_6"] = float(last_6.min())
        feature_row["roll_max_6"] = float(last_6.max())
        feature_row["roll_range_6"] = feature_row["roll_max_6"] - feature_row["roll_min_6"]
        feature_row["roll_mean_12"] = float(last_12.mean())
        feature_row["roll_std_12"] = float(last_12.std())
        last_timestamp = values.index[-1]
        feature_row["hour_of_day"] = float(last_timestamp.hour)
        feature_row["time_of_day_sin"] = float(np.sin(2 * np.pi * last_timestamp.hour / 24))
        feature_row["time_of_day_cos"] = float(np.cos(2 * np.pi * last_timestamp.hour / 24))
        feature_row["day_of_week"] = float(last_timestamp.dayofweek)
        feature_row["is_weekend"] = float(last_timestamp.dayofweek in {5, 6})
        feature_row.update(self._meal_context_features(logs, last_timestamp, current))
        feature_row["patient_baseline_offset"] = 0.0
        feature_row["glucose_current"] = current
        return {name: float(feature_row.get(name, 0.0)) for name in self.feature_columns}

    def _rule_based_fallback(self, logs: list[dict]) -> dict[str, Any]:
        """
        Fallback forecast when model artifacts are unavailable or when
        there is insufficient log history for feature construction.

        Uses the last known glucose value and applies population-average
        hourly drift rates to project forward.
        """
        ordered = sorted(logs, key=lambda item: str(item.get("timestamp", "")))
        last = ordered[-1] if ordered else {"glucose_mmol": 7.0}
        last_glucose = _as_mmol(float(last.get("glucose_mmol", last.get("glucose_level", 7.0))))
        # Conservative drifts avoid overconfident swings when no trained model output is available.
        multipliers = (
            {"60": 1.01, "120": 1.00, "180": 0.99, "240": 0.98}
            if last.get("is_fasting", True)
            else {"60": 1.02, "120": 1.01, "180": 0.99, "240": 0.98}
        )
        predictions = {horizon: round(last_glucose * multiplier, 2) for horizon, multiplier in multipliers.items()}
        confidence = {
            horizon: {"low": round(value - 1.5, 2), "high": round(value + 1.5, 2)}
            for horizon, value in predictions.items()
        }
        trend = self._trend_direction(predictions["60"], last_glucose)
        low_alert = any(value < self.thresholds["hypo_mmol"] for value in predictions.values())
        high_alert = any(value > self.thresholds["target_high_mmol"] for value in predictions.values())
        return {
            "current_glucose": round(last_glucose, 2),
            "predictions": predictions,
            "confidence_intervals": confidence,
            "trend_direction": trend,
            "predicted_low_alert": low_alert,
            "predicted_high_alert": high_alert,
            "recommendation": self.generate_recommendation(predictions, last_glucose, trend, low_alert, high_alert),
            "model_version": self.fallback_model_version,
            "used_fallback": True,
            "horizon_minutes": HORIZONS,
        }

    def _postprandial_population_forecast(self, logs: list[dict]) -> dict[str, Any] | None:
        """
        Forecast sparse/manual logs using CGMacros-derived Type 2 post-meal drift.

        The app does not yet collect full meal macro context, so this method uses
        population drift ratios learned from the trained CGMacros postprandial
        model metadata instead of pretending per-meal LightGBM features exist.
        """
        if not self.postprandial_available or not logs:
            return None
        ordered = sorted(logs, key=lambda item: str(item.get("timestamp", "")))
        last = ordered[-1]
        last_glucose = _as_mmol(float(last.get("glucose_mmol", last.get("glucose_level", 7.0))))
        last_is_fasting = bool(last.get("is_fasting", True))
        drift_ratios = self.postprandial_drift_ratios
        if last_is_fasting:
            # Fasting readings should not inherit full post-meal CGMacros excursion drift.
            drift_ratios = {"60": 1.01, "120": 1.00, "180": 0.99, "240": 0.98}
        predictions = {
            str(horizon): round(last_glucose * drift_ratios[str(horizon)], 2)
            for horizon in HORIZONS
        }
        confidence = {}
        for horizon, prediction in predictions.items():
            # Sparse/manual logs need wider intervals than dense CGM model predictions.
            mae = max(1.5, float(self.postprandial_mae_per_horizon.get(horizon, 1.5)))
            confidence[horizon] = {"low": round(prediction - mae, 2), "high": round(prediction + mae, 2)}
        trend = self._trend_direction(predictions["60"], last_glucose)
        low_alert = any(value < self.thresholds["hypo_mmol"] for value in predictions.values())
        high_alert = any(value > self.thresholds["target_high_mmol"] for value in predictions.values())
        return {
            "current_glucose": round(last_glucose, 2),
            "predictions": predictions,
            "confidence_intervals": confidence,
            "trend_direction": trend,
            "predicted_low_alert": low_alert,
            "predicted_high_alert": high_alert,
            "recommendation": self.generate_recommendation(predictions, last_glucose, trend, low_alert, high_alert),
            "model_version": self.postprandial_model_version,
            "used_fallback": False,
            "horizon_minutes": HORIZONS,
        }

    def _trend_direction(self, prediction_60min: float, current_glucose: float) -> str:
        """Classify the near-term forecast as rising, falling, or stable."""
        if prediction_60min > current_glucose + 0.5:
            return "rising"
        if prediction_60min < current_glucose - 0.5:
            return "falling"
        return "stable"

    def predict(self, user_id: int, logs: list[dict]) -> dict[str, Any]:
        """
        Main prediction method. Returns a forecast result dict.
        """
        if len(logs) < 4:
            result = self._rule_based_fallback(logs)
            return {"user_id": int(user_id), **result}
        if not self._is_cgm_like_cadence(logs):
            result = self._postprandial_population_forecast(logs) or self._rule_based_fallback(logs)
            return {"user_id": int(user_id), **result}
        if not self.model_available:
            result = self._rule_based_fallback(logs)
            return {"user_id": int(user_id), **result}
        feature_row = self._build_feature_row(logs)
        if feature_row is None:
            result = self._rule_based_fallback(logs)
            return {"user_id": int(user_id), **result}

        frame = pd.DataFrame([feature_row], columns=self.feature_columns)
        predictions = {
            str(horizon): round(float(self.models[str(horizon)].predict(frame)[0]), 2)
            for horizon in HORIZONS
        }
        confidence = {}
        for horizon, prediction in predictions.items():
            mae = float(self.mae_per_horizon.get(horizon, 1.5))
            confidence[horizon] = {"low": round(prediction - mae, 2), "high": round(prediction + mae, 2)}
        current = float(feature_row["glucose_current"])
        trend = self._trend_direction(predictions["60"], current)
        low_alert = any(value < self.thresholds["hypo_mmol"] for value in predictions.values())
        high_alert = any(value > self.thresholds["target_high_mmol"] for value in predictions.values())
        return {
            "user_id": int(user_id),
            "current_glucose": round(current, 2),
            "predictions": predictions,
            "confidence_intervals": confidence,
            "trend_direction": trend,
            "predicted_low_alert": low_alert,
            "predicted_high_alert": high_alert,
            "recommendation": self.generate_recommendation(predictions, current, trend, low_alert, high_alert),
            "model_version": self.model_version,
            "used_fallback": False,
            "horizon_minutes": HORIZONS,
        }

    def generate_recommendation(
        self,
        predictions: dict[str, float],
        current: float,
        trend: str,
        low_alert: bool,
        high_alert: bool,
    ) -> str:
        """
        Generate a plain-language recommendation based on forecast output.
        Not a medical recommendation — educational and supportive only.
        """
        if low_alert:
            return (
                "Glucose is predicted to approach the lower boundary in the next few hours. "
                "Consider a small snack and check again soon. Contact your doctor if you feel unwell."
            )
        if high_alert and trend == "rising":
            return (
                "Glucose is trending upward and may exceed the upper boundary. "
                "Light activity (a 15-minute walk) often helps. Stay hydrated."
            )
        if high_alert:
            return "A high glucose reading is predicted. Review recent meals and activity. Consult your care plan."
        rate = current - float(predictions.get("60", current))
        if trend == "falling" and rate > 1.5:
            return (
                "Glucose is falling quickly. Keep a fast-acting carbohydrate nearby and monitor more frequently."
            )
        if trend == "stable" and 4.5 <= current <= 8.0:
            return "Glucose looks stable. Keep up your current routine."
        return "Forecast generated. Continue monitoring as usual."


@lru_cache(maxsize=1)
def get_forecast_service() -> GlucoseForecastService:
    """Return a cached forecast service instance for API and agent callers."""
    return GlucoseForecastService()
