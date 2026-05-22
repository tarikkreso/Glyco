from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.db import models
from app.ml.forecast_inference import get_forecast_service

HORIZONS = (60, 120, 180, 240)
MIN_CALIBRATION_COUNT = 5
MATCH_TOLERANCE_MINUTES = 45
CALIBRATION_BIAS_EMA_ALPHA = 0.2


def _as_mmol(value: float) -> float:
    """Normalize glucose values that may be stored as mg/dL or mmol/L."""
    return float(value) / 18.015 if float(value) > 40 else float(value)


def _forecast_prediction(row: models.GlucoseForecast, horizon: int) -> float | None:
    """Read a forecast prediction value for one supported horizon."""
    values = {
        60: row.prediction_60min,
        120: row.prediction_120min,
        180: row.prediction_180min,
        240: row.prediction_240min,
    }
    return values[horizon]


def _refresh_calibration(db: Session, user_id: int, horizon: int, model_version: str | None) -> None:
    """Recompute one calibration row from all stored forecast evaluations."""
    evaluations = (
        db.query(models.GlucoseForecastEvaluation)
        .filter(
            models.GlucoseForecastEvaluation.user_id == user_id,
            models.GlucoseForecastEvaluation.horizon_minutes == horizon,
            models.GlucoseForecastEvaluation.model_version == model_version,
        )
        .order_by(models.GlucoseForecastEvaluation.matched_at.asc(), models.GlucoseForecastEvaluation.id.asc())
        .all()
    )
    if not evaluations:
        return
    count = len(evaluations)
    mae = sum(item.absolute_error for item in evaluations) / count
    bias = float(evaluations[0].signed_error)
    for item in evaluations[1:]:
        # Bias uses an EMA so recent misses influence calibration faster than old data.
        bias = CALIBRATION_BIAS_EMA_ALPHA * float(item.signed_error) + (1 - CALIBRATION_BIAS_EMA_ALPHA) * bias
    row = (
        db.query(models.GlucoseForecastCalibration)
        .filter(
            models.GlucoseForecastCalibration.user_id == user_id,
            models.GlucoseForecastCalibration.horizon_minutes == horizon,
            models.GlucoseForecastCalibration.model_version == model_version,
        )
        .first()
    )
    if row is None:
        row = models.GlucoseForecastCalibration(
            user_id=user_id,
            horizon_minutes=horizon,
            model_version=model_version,
        )
        db.add(row)
    row.count = count
    row.mean_absolute_error = round(float(mae), 4)
    row.signed_bias = round(float(bias), 4)
    row.updated_at = datetime.utcnow()


def evaluate_forecasts_for_log(db: Session, log: models.HealthLog) -> int:
    """Match a new glucose log to pending forecast horizons and store errors."""
    actual_time = log.created_at or datetime.combine(log.log_date, datetime.min.time())
    actual_mmol = _as_mmol(log.glucose_level)
    start = actual_time - timedelta(minutes=max(HORIZONS) + MATCH_TOLERANCE_MINUTES)
    end = actual_time + timedelta(minutes=MATCH_TOLERANCE_MINUTES)
    forecasts = (
        db.query(models.GlucoseForecast)
        .filter(
            models.GlucoseForecast.user_id == log.user_id,
            models.GlucoseForecast.created_at >= start,
            models.GlucoseForecast.created_at <= end,
        )
        .all()
    )
    created = 0
    for forecast in forecasts:
        for horizon in HORIZONS:
            predicted = _forecast_prediction(forecast, horizon)
            if predicted is None:
                continue
            predicted_for = forecast.created_at + timedelta(minutes=horizon)
            if abs((actual_time - predicted_for).total_seconds()) > MATCH_TOLERANCE_MINUTES * 60:
                continue
            exists = (
                db.query(models.GlucoseForecastEvaluation)
                .filter(
                    models.GlucoseForecastEvaluation.forecast_id == forecast.id,
                    models.GlucoseForecastEvaluation.horizon_minutes == horizon,
                )
                .first()
            )
            if exists:
                continue
            signed_error = actual_mmol - float(predicted)
            db.add(
                models.GlucoseForecastEvaluation(
                    user_id=log.user_id,
                    forecast_id=forecast.id,
                    horizon_minutes=horizon,
                    predicted_for=predicted_for,
                    predicted_mmol=float(predicted),
                    actual_log_id=log.id,
                    actual_mmol=actual_mmol,
                    absolute_error=abs(signed_error),
                    signed_error=signed_error,
                    model_version=forecast.model_version,
                )
            )
            created += 1
    if created:
        touched = {
            (item.horizon_minutes, item.model_version)
            for item in db.new
            if isinstance(item, models.GlucoseForecastEvaluation)
        }
        db.flush()
        for horizon, model_version in touched:
            _refresh_calibration(db, log.user_id, int(horizon), model_version)
        db.commit()
    return created


def calibration_snapshot(db: Session, user_id: int, model_version: str | None) -> dict[str, dict[str, float | int]]:
    """Return per-horizon calibration rows for a user and model version."""
    rows = (
        db.query(models.GlucoseForecastCalibration)
        .filter(
            models.GlucoseForecastCalibration.user_id == user_id,
            models.GlucoseForecastCalibration.model_version == model_version,
        )
        .all()
    )
    return {
        str(row.horizon_minutes): {
            "count": int(row.count),
            "mae": float(row.mean_absolute_error),
            "bias": float(row.signed_bias),
        }
        for row in rows
    }


def apply_calibration(db: Session, result: dict[str, Any]) -> dict[str, Any]:
    """Apply learned user calibration to a forecast result when enough data exists."""
    calibrated = {**result, "predictions": dict(result["predictions"]), "confidence_intervals": dict(result["confidence_intervals"])}
    snapshot = calibration_snapshot(db, int(result["user_id"]), result.get("model_version"))
    applied = False
    personal_mae: dict[str, float] = {}
    for horizon in ("60", "120", "180", "240"):
        row = snapshot.get(horizon)
        if not row:
            continue
        personal_mae[horizon] = float(row["mae"])
        if int(row["count"]) < MIN_CALIBRATION_COUNT:
            continue
        applied = True
        original_prediction = float(calibrated["predictions"][horizon])
        original_interval = dict(calibrated["confidence_intervals"][horizon])
        original_width = max(
            original_prediction - float(original_interval["low"]),
            float(original_interval["high"]) - original_prediction,
        )
        calibrated["predictions"][horizon] = round(float(calibrated["predictions"][horizon]) + float(row["bias"]), 2)
        width = max(float(row["mae"]), original_width)
        calibrated["confidence_intervals"][horizon] = {
            "low": round(calibrated["predictions"][horizon] - width, 2),
            "high": round(calibrated["predictions"][horizon] + width, 2),
        }
    current = float(calibrated["current_glucose"])
    service = get_forecast_service()
    calibrated["trend_direction"] = service._trend_direction(float(calibrated["predictions"]["60"]), current)
    calibrated["predicted_low_alert"] = any(value < service.thresholds["hypo_mmol"] for value in calibrated["predictions"].values())
    calibrated["predicted_high_alert"] = any(value > service.thresholds["target_high_mmol"] for value in calibrated["predictions"].values())
    calibrated["recommendation"] = service.generate_recommendation(
        calibrated["predictions"],
        current,
        calibrated["trend_direction"],
        calibrated["predicted_low_alert"],
        calibrated["predicted_high_alert"],
    )
    calibrated["calibration_applied"] = applied
    calibrated["personal_mae_per_horizon"] = personal_mae or None
    calibrated["forecast_quality"] = "calibrated" if applied else "learning" if personal_mae else "needs_more_data"
    return calibrated


def forecast_accuracy_summary(db: Session, user_id: int) -> dict[str, Any]:
    """Return aggregate forecast accuracy and recent evaluation rows for a user."""
    evaluations = (
        db.query(models.GlucoseForecastEvaluation)
        .filter(models.GlucoseForecastEvaluation.user_id == user_id)
        .order_by(models.GlucoseForecastEvaluation.matched_at.desc())
        .all()
    )
    by_horizon: dict[str, dict[str, float | int]] = {}
    for horizon in HORIZONS:
        rows = [item for item in evaluations if item.horizon_minutes == horizon]
        if not rows:
            by_horizon[str(horizon)] = {"count": 0, "mae": 0.0, "bias": 0.0}
            continue
        by_horizon[str(horizon)] = {
            "count": len(rows),
            "mae": round(sum(item.absolute_error for item in rows) / len(rows), 3),
            "bias": round(sum(item.signed_error for item in rows) / len(rows), 3),
        }
    return {
        "user_id": user_id,
        "total_evaluations": len(evaluations),
        "per_horizon": by_horizon,
        "latest": [
            {
                "forecast_id": item.forecast_id,
                "horizon_minutes": item.horizon_minutes,
                "predicted_for": item.predicted_for,
                "predicted_mmol": item.predicted_mmol,
                "actual_mmol": item.actual_mmol,
                "absolute_error": item.absolute_error,
                "signed_error": item.signed_error,
                "matched_at": item.matched_at,
            }
            for item in evaluations[:10]
        ],
    }
