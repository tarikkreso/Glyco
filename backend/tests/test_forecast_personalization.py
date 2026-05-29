import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db import models
from app.db.database import SessionLocal
from app.main import _ensure_lightweight_schema_updates
from app.services.forecast_learning import apply_calibration


def test_forecast_personalization_toggle_disables_calibration() -> None:
    """Users can opt out of forecast calibration while still receiving forecasts."""
    _ensure_lightweight_schema_updates()
    db = SessionLocal()
    existing = db.query(models.User).filter(models.User.email_or_demo_id == "forecast-toggle-test").first()
    if existing is not None:
        db.query(models.GlucoseForecastCalibration).filter(models.GlucoseForecastCalibration.user_id == existing.id).delete()
        db.query(models.Profile).filter(models.Profile.user_id == existing.id).delete()
        db.query(models.User).filter(models.User.id == existing.id).delete()
        db.commit()
    user = models.User(full_name="Forecast Toggle", email_or_demo_id="forecast-toggle-test")
    user_id: int | None = None
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        db.add(
            models.Profile(
                user_id=user.id,
                age=55,
                sex="Female",
                height_cm=168,
                weight_kg=86,
                bmi=30.5,
                high_bp=True,
                high_chol=True,
                smoker=False,
                phys_activity=True,
                fruits=True,
                veggies=True,
                general_health=3,
                stroke_history=False,
                heart_disease_history=False,
                difficulty_walking=False,
                family_history_diabetes=True,
                forecast_personalization_enabled=False,
            )
        )
        db.add(
            models.GlucoseForecastCalibration(
                user_id=user.id,
                horizon_minutes=60,
                count=8,
                mean_absolute_error=0.7,
                signed_bias=1.4,
                model_version="test-forecast",
            )
        )
        db.commit()

        result = apply_calibration(
            db,
            {
                "user_id": user.id,
                "current_glucose": 7.0,
                "predictions": {"60": 7.0, "120": 7.0, "180": 7.0, "240": 7.0},
                "confidence_intervals": {
                    "60": {"low": 6.0, "high": 8.0},
                    "120": {"low": 6.0, "high": 8.0},
                    "180": {"low": 6.0, "high": 8.0},
                    "240": {"low": 6.0, "high": 8.0},
                },
                "trend_direction": "stable",
                "predicted_low_alert": False,
                "predicted_high_alert": False,
                "recommendation": "Forecast generated.",
                "model_version": "test-forecast",
                "used_fallback": False,
                "horizon_minutes": [60, 120, 180, 240],
            },
        )

        assert result["predictions"]["60"] == 7.0
        assert result["calibration_applied"] is False
        assert result["personalization_enabled"] is False
        assert result["forecast_quality"] == "personalization_off"
    finally:
        db.rollback()
        if user_id is not None:
            db.query(models.GlucoseForecastCalibration).filter(models.GlucoseForecastCalibration.user_id == user_id).delete()
            db.query(models.Profile).filter(models.Profile.user_id == user_id).delete()
            db.query(models.User).filter(models.User.id == user_id).delete()
            db.commit()
        db.close()
