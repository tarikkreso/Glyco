from __future__ import annotations

from datetime import date, timedelta
from sqlalchemy.orm import Session

from app.agent.guidelines import retrieve_guidelines
from app.db import models
from app.reports.generator import build_report
from app.services.assessments import create_monitoring_assessment, create_risk_assessment


def get_profile(db: Session, user_id: int) -> dict | None:
    profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).order_by(models.Profile.created_at.desc()).first()
    if not profile:
        return None
    return {
        "age": profile.age,
        "sex": profile.sex,
        "bmi": profile.bmi,
        "high_bp": profile.high_bp,
        "high_chol": profile.high_chol,
        "phys_activity": profile.phys_activity,
        "general_health": profile.general_health,
    }


def get_logs(db: Session, user_id: int, days: int = 7) -> list[dict]:
    start = date.today() - timedelta(days=days)
    rows = db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id, models.HealthLog.log_date >= start).order_by(models.HealthLog.log_date.asc()).all()
    return [
        {
            "date": row.log_date.isoformat(),
            "fasting_glucose": row.fasting_glucose,
            "post_meal_glucose": row.post_meal_glucose,
            "blood_pressure": f"{row.systolic_bp}/{row.diastolic_bp}" if row.systolic_bp and row.diastolic_bp else None,
            "activity_minutes": row.activity_minutes,
        }
        for row in rows
    ]


def run_risk_check(db: Session, user_id: int) -> dict:
    # The agent uses the same assessment service as the dashboard, keeping chat
    # explanations and visible risk cards grounded in one source of truth.
    row = db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user_id).order_by(models.RiskAssessment.created_at.desc()).first()
    profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).order_by(models.Profile.created_at.desc()).first()
    if (not row or row.model_version == "rules-fallback-0.1") and profile:
        return create_risk_assessment(db, profile)
    return {
        "risk_probability": row.risk_probability,
        "risk_level": row.risk_level,
        "top_factors": row.top_factors_json,
        "related_flags": row.related_flags_json,
        "model_version": row.model_version,
    } if row else {}


def run_trend_check(db: Session, user_id: int) -> dict:
    # If only a rules fallback exists, refresh monitoring so the trained model
    # can take over once the user has enough glucose history.
    row = db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user_id).order_by(models.MonitoringAssessment.created_at.desc()).first()
    if not row or row.model_version == "engineered-rules-0.1":
        return create_monitoring_assessment(db, user_id)
    return {
        "trend_label": row.trend_label,
        "trend_score": row.trend_score,
        "anomaly_flags": row.anomaly_flags_json,
        "summary": row.summary_json,
        "model_version": row.model_version,
    }


def generate_report(db: Session, user_id: int, report_type: str = "doctor") -> dict:
    user = db.get(models.User, user_id)
    risk = db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user_id).order_by(models.RiskAssessment.created_at.desc()).first()
    monitoring = db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user_id).order_by(models.MonitoringAssessment.created_at.desc()).first()
    logs = db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id).order_by(models.HealthLog.log_date.asc()).all()
    return build_report(report_type, user, risk, monitoring, logs)


def retrieve_guideline_snippets(query: str) -> list[dict]:
    # Lightweight retrieval grounds every answer in curated clinical-safety notes,
    # even when no external LLM provider is configured.
    return retrieve_guidelines(query)
