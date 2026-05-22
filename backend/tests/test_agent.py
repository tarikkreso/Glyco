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
    # Use empty-string env vars (not delenv) so the app's .env loader cannot
    # re-populate keys later in the same test run.
    monkeypatch.setenv("GLYCO_LLM_PROVIDER", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GLYCO_GEMINI_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("GLYCO_DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("GLYCO_OPENROUTER_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GLYCO_GROQ_API_KEY", "")
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


def test_agent_history_memory() -> None:
    """The chatbot preserves conversation history in the SQLite AgentMemory table."""
    # Ensure tests don't accidentally call external LLMs when devs have keys set.
    import os

    for name in (
        "GLYCO_LLM_PROVIDER",
        "DEEPSEEK_API_KEY",
        "GLYCO_DEEPSEEK_API_KEY",
        "OPENROUTER_API_KEY",
        "GLYCO_OPENROUTER_API_KEY",
        "GEMINI_API_KEY",
        "GLYCO_GEMINI_API_KEY",
        "GROQ_API_KEY",
        "GLYCO_GROQ_API_KEY",
    ):
        os.environ[name] = ""

    db = SessionLocal()
    user = _create_user(db, "agent-memory-test")
    try:
        # Clear any existing history first
        db.query(models.AgentMemory).filter(models.AgentMemory.user_id == user.id).delete()
        db.commit()

        # First turn
        chat_with_agent(db, user.id, "Hi, I am Nedim.")
        history1 = db.query(models.AgentMemory).filter(models.AgentMemory.user_id == user.id).order_by(models.AgentMemory.created_at.asc()).all()
        assert len(history1) == 2
        assert history1[0].role == "user"
        assert history1[0].content == "Hi, I am Nedim."
        assert history1[1].role == "assistant"

        # Second turn
        chat_with_agent(db, user.id, "What is my name?")
        history2 = db.query(models.AgentMemory).filter(models.AgentMemory.user_id == user.id).order_by(models.AgentMemory.created_at.asc()).all()
        assert len(history2) == 4
        assert history2[2].content == "What is my name?"
    finally:
        db.query(models.AgentMemory).filter(models.AgentMemory.user_id == user.id).delete()
        db.query(models.BanditArmState).filter(models.BanditArmState.user_id == user.id).delete()
        db.query(models.BayesianRiskState).filter(models.BayesianRiskState.user_id == user.id).delete()
        db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user.id).delete()
        db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user.id).delete()
        db.query(models.Profile).filter(models.Profile.user_id == user.id).delete()
        db.query(models.User).filter(models.User.id == user.id).delete()
        db.commit()
        db.close()


def test_rich_system_prompt_diet_meal_support() -> None:
    """The rich system prompt contains Diet & Meal Support rules and Patient personalized diet care plan."""
    from app.agent.llm_client import build_rich_system_prompt
    db = SessionLocal()
    user = _create_user(db, "prompt-diet-test")
    try:
        pipeline_context = build_agent_tool_pipeline(db, user.id, "what should I eat?")
        system_prompt = build_rich_system_prompt(pipeline_context)
        
        # Check that prompt contains key terms we injected
        assert "Diet & Meal Support" in system_prompt
        assert "PATIENT PERSONALIZED DIET CARE PLAN:" in system_prompt
        assert "CURRENT TIME OF DAY:" in system_prompt
    finally:
        db.query(models.BanditArmState).filter(models.BanditArmState.user_id == user.id).delete()
        db.query(models.BayesianRiskState).filter(models.BayesianRiskState.user_id == user.id).delete()
        db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user.id).delete()
        db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user.id).delete()
        db.query(models.Profile).filter(models.Profile.user_id == user.id).delete()
        db.query(models.User).filter(models.User.id == user.id).delete()
        db.commit()
        db.close()


def test_prompt_translation_and_direct_answer() -> None:
    """Ensure prompt builders contain translation guidelines and direct answer instructions."""
    from app.agent.llm_client import build_rich_system_prompt, _build_concise_prompt
    db = SessionLocal()
    user = _create_user(db, "prompt-trans-test")
    try:
        pipeline_context = build_agent_tool_pipeline(db, user.id, "da li se moze kineskom metodom pijenjem samo tople vode izlijeciti secer")
        system_prompt = build_rich_system_prompt(pipeline_context)
        
        # Check that system prompt contains language & translation + direct answer guidelines
        assert "Language & Translation" in system_prompt
        assert "Direct Answer First" in system_prompt
        assert "Bosnian, Croatian, Serbian" in system_prompt
        assert "Zaključak" in system_prompt
        assert "warm water" in system_prompt

        # Check concise prompt contains same guidelines
        messages = [{"role": "user", "content": "da li se moze kineskom metodom pijenjem samo tople vode izlijeciti secer"}]
        concise_prompt = _build_concise_prompt(messages, pipeline_context)
        assert "Language & Translation" in concise_prompt
        assert "Direct Answer First" in concise_prompt
        assert "warm water" in concise_prompt
    finally:
        db.query(models.BanditArmState).filter(models.BanditArmState.user_id == user.id).delete()
        db.query(models.BayesianRiskState).filter(models.BayesianRiskState.user_id == user.id).delete()
        db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user.id).delete()
        db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user.id).delete()
        db.query(models.Profile).filter(models.Profile.user_id == user.id).delete()
        db.query(models.User).filter(models.User.id == user.id).delete()
        db.commit()
        db.close()


def test_groq_client_integration() -> None:
    """Verify that GroqClient compiles and integrates correctly into provider order and status check."""
    import os
    from app.agent.llm_client import _provider_order, get_llm_status, GroqClient, get_llm_client
    
    # Temporarily set keys
    os.environ["GROQ_API_KEY"] = "gsk_test_key"
    os.environ["GEMINI_API_KEY"] = "gemini_test_key"
    
    try:
        order = _provider_order()
        assert "groq" in order
        assert order[0] == "groq"  # Defaults to groq first when present and provider unset
        
        status = get_llm_status()
        assert status["groq"]["configured"] is True
        assert status["groq"]["model"] == "llama-3.3-70b-versatile"
        
        client = get_llm_client()
        # Verify groq is in the chain
        providers = [getattr(c, "provider_name", "") for c in client.clients]
        assert "groq" in providers
    finally:
        os.environ.pop("GROQ_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)


