from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db import models
from app.ml.forecast_inference import get_forecast_service
from app.services.forecast_learning import apply_calibration
from app.reports.generator import build_report


def create_report_for_agent(db: Session, user_id: int, report_type: str = "doctor") -> dict[str, Any]:
    """Create and persist a report from current model state for proactive agent actions."""
    normalized = report_type if report_type in {"doctor", "family", "weekly"} else "doctor"
    user = db.get(models.User, user_id)
    risk = db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user_id).order_by(models.RiskAssessment.created_at.desc()).first()
    monitoring = db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user_id).order_by(models.MonitoringAssessment.created_at.desc()).first()
    logs = db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id).order_by(models.HealthLog.log_date.asc()).all()
    content = build_report(normalized, user, risk, monitoring, logs)
    row = models.Report(user_id=user_id, report_type=normalized, content_json=content)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"report_id": row.id, "report_type": row.report_type, "created_at": row.created_at.isoformat()}


def _as_mmol(value: float) -> float:
    """Normalize glucose values to mmol/L for the sustained high-glucose threshold."""
    return value / 18.0 if value > 40 else value


def _forecast_logs(db: Session, user_id: int) -> list[dict[str, Any]]:
    """Load recent logs for appending forecast context to proactive anomalies."""
    rows = (
        db.query(models.HealthLog)
        .filter(models.HealthLog.user_id == user_id)
        .order_by(models.HealthLog.created_at.desc(), models.HealthLog.log_date.desc())
        .limit(48)
        .all()
    )
    return [
        {"timestamp": row.created_at or row.log_date, "glucose_mmol": _as_mmol(row.glucose_level), "is_fasting": bool(row.is_fasting)}
        for row in reversed(rows)
        if row.glucose_level is not None
    ]


def detect_sustained_glucose_anomaly_and_report(db: Session, user_id: int) -> dict[str, Any]:
    """Detect sustained high fasting glucose and create a doctor report plus alert."""
    logs = (
        db.query(models.HealthLog)
        .filter(models.HealthLog.user_id == user_id, models.HealthLog.is_fasting.is_(True))
        .order_by(models.HealthLog.log_date.desc())
        .limit(3)
        .all()
    )
    if len(logs) < 3 or not all(_as_mmol(row.fasting_glucose) > 7.0 for row in logs):
        return {"proactive_alert": False}

    title = "Sustained elevated fasting glucose"
    existing = (
        db.query(models.AgentAlert)
        .filter(
            models.AgentAlert.user_id == user_id,
            models.AgentAlert.title == title,
            models.AgentAlert.acknowledged_at.is_(None),
        )
        .order_by(models.AgentAlert.created_at.desc())
        .first()
    )
    if existing:
        return {"proactive_alert": False, "reason": "existing", "alert_id": existing.id}

    report = create_report_for_agent(db, user_id, "doctor")
    forecast = apply_calibration(db, get_forecast_service().predict(user_id, _forecast_logs(db, user_id)))
    message = (
        "Glyco detected that the last 3 fasting glucose readings were above 7.0 mmol/L "
        f"and generated a doctor report. Forecast trend: {forecast['trend_direction']}."
    )
    alert = models.AgentAlert(
        user_id=user_id,
        severity="danger",
        title=title,
        message=message,
        recommended_action="Review the generated doctor report and contact your clinician if this pattern persists.",
        source_json={"report": report, "last_three": [row.fasting_glucose for row in reversed(logs)], "forecast": forecast},
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return {"proactive_alert": True, "message": message, "report_id": report["report_id"], "alert_id": alert.id}
