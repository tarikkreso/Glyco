import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.agent.agent_service import build_agent_tool_pipeline, chat_with_agent
from app.agent.bandit import RECOMMENDATION_ARMS
from app.agent.proactive import detect_sustained_glucose_anomaly_and_report
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


def test_agent_tool_pipeline_uses_recommendation_ranker() -> None:
    """The active agent pipeline returns Thompson-ranked recommendations."""
    db = SessionLocal()
    user = _create_user(db, "agent-pipeline")
    try:
        result = build_agent_tool_pipeline(db, user.id, "What should I do this week?")
        ranker = next(tool for tool in result["tool_calls"] if tool["name"] == "rank_recommendations_with_thompson_sampling")
        ranked = ranker["details"]["ranked_recommendations"]
        assert ranked
        assert ranked[0]["type"] in RECOMMENDATION_ARMS
    finally:
        db.query(models.BanditArmState).filter(models.BanditArmState.user_id == user.id).delete()
        db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user.id).delete()
        db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user.id).delete()
        db.query(models.BayesianRiskState).filter(models.BayesianRiskState.user_id == user.id).delete()
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
        result = detect_sustained_glucose_anomaly_and_report(db, user.id)
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


def test_not_fasting_readings_do_not_trigger_fasting_anomaly() -> None:
    """Post-meal/not-fasting readings are not treated as fasting anomaly evidence."""
    db = SessionLocal()
    user = _create_user(db, "agent-post-meal-anomaly")
    try:
        for idx in range(3):
            db.add(
                models.HealthLog(
                    user_id=user.id,
                    log_date=date.today() - timedelta(days=2 - idx),
                    is_fasting=False,
                    fasting_glucose=190,
                    post_meal_glucose=190,
                )
            )
        db.commit()
        result = detect_sustained_glucose_anomaly_and_report(db, user.id)
        assert result["proactive_alert"] is False
    finally:
        db.query(models.AgentAlert).filter(models.AgentAlert.user_id == user.id).delete()
        db.query(models.Report).filter(models.Report.user_id == user.id).delete()
        db.query(models.HealthLog).filter(models.HealthLog.user_id == user.id).delete()
        db.query(models.Profile).filter(models.Profile.user_id == user.id).delete()
        db.query(models.User).filter(models.User.id == user.id).delete()
        db.commit()
        db.close()


def test_agent_chat_without_external_llm_uses_fallback(monkeypatch) -> None:
    """Missing external LLM configuration still returns a tool-grounded response."""
    monkeypatch.delenv("GLYCO_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GLYCO_GEMINI_API_KEY", raising=False)
    db = SessionLocal()
    user = _create_user(db, "agent-fallback")
    try:
        result = chat_with_agent(db, user.id, "What should I do this week?")
        assert result["answer"]
        assert result["llm_mode"] == "fallback"
        assert "rank_recommendations_with_thompson_sampling" in {tool["name"] for tool in result["tool_calls"]}
    finally:
        db.query(models.BanditArmState).filter(models.BanditArmState.user_id == user.id).delete()
        db.query(models.BayesianRiskState).filter(models.BayesianRiskState.user_id == user.id).delete()
        db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user.id).delete()
        db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user.id).delete()
        db.query(models.Profile).filter(models.Profile.user_id == user.id).delete()
        db.query(models.User).filter(models.User.id == user.id).delete()
        db.commit()
        db.close()


def test_gemini_agentic_loop_calls_tools_before_answering(monkeypatch) -> None:
    """Configured Gemini path uses function calls, not precomputed tool context."""
    monkeypatch.setenv("GLYCO_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    required_calls = [
        "get_patient_profile",
        "get_glucose_logs",
        "run_trained_risk_model",
        "get_bayesian_risk_state",
        "run_trained_glucose_trend_model",
        "retrieve_guidelines",
        "read_agent_learning_memory",
        "rank_recommendations_with_thompson_sampling",
    ]
    responses = [
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"functionCall": {"name": name, "args": {"query": "Should I worry?", "days": 7, "limit": 3}}}
                            for name in required_calls
                        ]
                    },
                    "finishReason": "STOP",
                }
            ]
        },
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    "Bottom line\n"
                                    "- Glyco used the live tools first and then answered. "
                                    "The RF risk model, trend model, Bayesian layer, and Thompson ranker were checked."
                                )
                            }
                        ]
                    },
                    "finishReason": "STOP",
                }
            ]
        },
    ]

    def fake_post(*args, **kwargs):
        payload = responses.pop(0)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)

    monkeypatch.setattr("app.agent.agentic_loop.httpx.post", fake_post)
    db = SessionLocal()
    user = _create_user(db, "agentic-gemini")
    try:
        for idx in range(4):
            db.add(models.HealthLog(user_id=user.id, log_date=date.today() - timedelta(days=3 - idx), fasting_glucose=120 + idx * 8))
        db.commit()
        result = chat_with_agent(db, user.id, "Should I worry this week?")
        assert result["llm_mode"] == "gemini-agentic"
        assert {tool["name"] for tool in result["tool_calls"]}.issuperset(required_calls)
        assert result["recommendations"]
        assert result["learning_summary"]["recent_glucose_pattern"]["label"] in {"watch", "needs-attention", "steady"}
    finally:
        db.query(models.AgentFeedback).filter(models.AgentFeedback.user_id == user.id).delete()
        db.query(models.BanditArmState).filter(models.BanditArmState.user_id == user.id).delete()
        db.query(models.BayesianRiskState).filter(models.BayesianRiskState.user_id == user.id).delete()
        db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user.id).delete()
        db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user.id).delete()
        db.query(models.HealthLog).filter(models.HealthLog.user_id == user.id).delete()
        db.query(models.Profile).filter(models.Profile.user_id == user.id).delete()
        db.query(models.User).filter(models.User.id == user.id).delete()
        db.commit()
        db.close()
