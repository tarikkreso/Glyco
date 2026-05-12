import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.agent.anthropic_agent import detect_glucose_anomaly_and_report, dispatch_tool, run_agent_chat
from app.db import models
from app.db.database import SessionLocal
from app.rules.engine import calculate_bmi


def _create_user(db, demo_id: str) -> models.User:
    """Create a test user with a minimal risk profile."""
    user = models.User(full_name=demo_id, email_or_demo_id=demo_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(models.Profile(
        user_id=user.id,
        age=55,
        sex="Female",
        height_cm=165,
        weight_kg=86,
        bmi=calculate_bmi(86, 165),
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
    ))
    db.commit()
    return user


def test_tool_dispatch_logic() -> None:
    """Tool dispatch returns data for known agent tools."""
    db = SessionLocal()
    user = _create_user(db, "agent-dispatch")
    try:
        result = dispatch_tool(db, "get_recommendations", {"user_id": user.id})
        assert result
        assert result[0]["type"] in {"nutrition", "activity", "monitoring", "medication_check"}
    finally:
        db.query(models.BanditArmState).filter(models.BanditArmState.user_id == user.id).delete()
        db.query(models.Profile).filter(models.Profile.user_id == user.id).delete()
        db.query(models.User).filter(models.User.id == user.id).delete()
        db.commit()
        db.close()


def test_anomaly_detection_trigger() -> None:
    """Three fasting readings above 7 mmol/L trigger report generation."""
    db = SessionLocal()
    user = _create_user(db, "agent-anomaly")
    try:
        for idx in range(3):
            db.add(models.HealthLog(user_id=user.id, log_date=date.today() - timedelta(days=2 - idx), fasting_glucose=145))
        db.commit()
        result = detect_glucose_anomaly_and_report(db, user.id)
        assert result["proactive_alert"] is True
        assert result["report_id"]
    finally:
        db.query(models.AgentAlert).filter(models.AgentAlert.user_id == user.id).delete()
        db.query(models.Report).filter(models.Report.user_id == user.id).delete()
        db.query(models.HealthLog).filter(models.HealthLog.user_id == user.id).delete()
        db.query(models.Profile).filter(models.Profile.user_id == user.id).delete()
        db.query(models.User).filter(models.User.id == user.id).delete()
        db.commit()
        db.close()


def test_agent_chat_without_anthropic_key_uses_fallback(monkeypatch) -> None:
    """Missing Anthropic configuration still returns a tool-grounded response."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db = SessionLocal()
    user = _create_user(db, "agent-fallback")
    try:
        result = run_agent_chat(db, user.id, "What should I do this week?")
        assert result["response"]
        assert "get_recommendations" in result["tools_used"]
    finally:
        db.query(models.AgentMemory).filter(models.AgentMemory.user_id == user.id).delete()
        db.query(models.BanditArmState).filter(models.BanditArmState.user_id == user.id).delete()
        db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user.id).delete()
        db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user.id).delete()
        db.query(models.Profile).filter(models.Profile.user_id == user.id).delete()
        db.query(models.User).filter(models.User.id == user.id).delete()
        db.commit()
        db.close()
