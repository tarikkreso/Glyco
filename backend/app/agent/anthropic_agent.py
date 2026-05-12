from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.agent.bandit import RecommendationBandit, default_recommendations
from app.core.settings import get_settings
from app.db import models
from app.reports.generator import build_report
from app.services.bayesian import get_or_create_bayesian_state, serialize_bayesian_state
from app.services.assessments import create_monitoring_assessment, create_risk_assessment

try:
    import anthropic
except Exception:  # pragma: no cover - absence is expected in local fallback mode.
    anthropic = None


ANTHROPIC_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_risk_assessment",
        "description": "Get the latest Random Forest risk assessment plus Bayesian posterior state.",
        "input_schema": {"type": "object", "properties": {"user_id": {"type": "integer"}}, "required": ["user_id"]},
    },
    {
        "name": "get_monitoring_trend",
        "description": "Get the latest monitoring trend assessment.",
        "input_schema": {"type": "object", "properties": {"user_id": {"type": "integer"}}, "required": ["user_id"]},
    },
    {
        "name": "get_health_logs",
        "description": "Get recent glucose and health logs.",
        "input_schema": {
            "type": "object",
            "properties": {"user_id": {"type": "integer"}, "days": {"type": "integer", "default": 14}},
            "required": ["user_id"],
        },
    },
    {
        "name": "get_recommendations",
        "description": "Get Thompson-sampled recommendations.",
        "input_schema": {"type": "object", "properties": {"user_id": {"type": "integer"}}, "required": ["user_id"]},
    },
    {
        "name": "create_report",
        "description": "Create a doctor, family, or weekly report.",
        "input_schema": {
            "type": "object",
            "properties": {"user_id": {"type": "integer"}, "report_type": {"type": "string"}},
            "required": ["user_id", "report_type"],
        },
    },
]


# Fetches or creates the latest risk state so tool calls always have a value to
# reason over, even for demo users after database reseeding.
def get_risk_assessment_tool(db: Session, user_id: int) -> dict[str, Any]:
    """Return latest RF risk and Bayesian state for a user."""
    risk = db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user_id).order_by(models.RiskAssessment.created_at.desc()).first()
    profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).order_by(models.Profile.created_at.desc()).first()
    if profile and not risk:
        create_risk_assessment(db, profile)
        risk = db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user_id).order_by(models.RiskAssessment.created_at.desc()).first()
    bayes = serialize_bayesian_state(get_or_create_bayesian_state(db, user_id))
    return {
        "random_forest": {
            "risk_probability": risk.risk_probability if risk else None,
            "risk_level": risk.risk_level if risk else "unknown",
            "model_version": risk.model_version if risk else "unavailable",
        },
        "bayesian": bayes,
    }


# Uses current persisted trend state, refreshing when no assessment exists yet.
def get_monitoring_trend_tool(db: Session, user_id: int) -> dict[str, Any]:
    """Return latest monitoring trend for a user."""
    row = db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user_id).order_by(models.MonitoringAssessment.created_at.desc()).first()
    if not row:
        return create_monitoring_assessment(db, user_id)
    return {
        "trend_label": row.trend_label,
        "trend_score": row.trend_score,
        "anomaly_flags": row.anomaly_flags_json,
        "summary": row.summary_json,
        "model_version": row.model_version,
    }


# Keeps the tool's date filter in one place so model calls and tests receive the
# same compact log representation.
def get_health_logs_tool(db: Session, user_id: int, days: int = 14) -> list[dict[str, Any]]:
    """Return recent health logs for Anthropic tool use."""
    start = date.today() - timedelta(days=days)
    rows = db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id, models.HealthLog.log_date >= start).order_by(models.HealthLog.log_date.asc()).all()
    return [
        {
            "date": row.log_date.isoformat(),
            "fasting_glucose": row.fasting_glucose,
            "post_meal_glucose": row.post_meal_glucose,
            "activity_minutes": row.activity_minutes,
            "blood_pressure": f"{row.systolic_bp}/{row.diastolic_bp}" if row.systolic_bp and row.diastolic_bp else None,
        }
        for row in rows
    ]


# Applies the bandit immediately before returning recommendations so every
# surface benefits from feedback learning.
def get_recommendations_tool(db: Session, user_id: int, limit: int = 4) -> list[dict[str, Any]]:
    """Return Thompson-sampled recommendations for a user."""
    return RecommendationBandit(db, user_id).rerank(default_recommendations(), limit=limit)


# Persists a report row and returns its identifier for downstream PDF generation.
def create_report_tool(db: Session, user_id: int, report_type: str = "doctor") -> dict[str, Any]:
    """Create and persist a report using the existing report builder."""
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


# Dispatches tool use by name, keeping the Anthropic loop tiny and testable.
def dispatch_tool(db: Session, name: str, tool_input: dict[str, Any]) -> Any:
    """Run one named agent tool with validated fallback defaults."""
    user_id = int(tool_input.get("user_id", 1))
    if name == "get_risk_assessment":
        return get_risk_assessment_tool(db, user_id)
    if name == "get_monitoring_trend":
        return get_monitoring_trend_tool(db, user_id)
    if name == "get_health_logs":
        return get_health_logs_tool(db, user_id, int(tool_input.get("days", 14)))
    if name == "get_recommendations":
        return get_recommendations_tool(db, user_id)
    if name == "create_report":
        return create_report_tool(db, user_id, str(tool_input.get("report_type", "doctor")))
    return {"error": f"Unknown tool: {name}"}


# Converts either mg/dL or mmol/L-looking values to mmol/L before anomaly checks.
def _as_mmol(value: float) -> float:
    """Normalize glucose values to mmol/L for the proactive threshold."""
    return value / 18.0 if value > 40 else value


# Checks the last three fasting readings and creates a doctor report when all
# are above the requested 7.0 mmol/L threshold.
def detect_glucose_anomaly_and_report(db: Session, user_id: int) -> dict[str, Any]:
    """Detect sustained high glucose and auto-generate a doctor report."""
    logs = db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id).order_by(models.HealthLog.log_date.desc()).limit(3).all()
    if len(logs) < 3 or not all(_as_mmol(row.fasting_glucose) > 7.0 for row in logs):
        return {"proactive_alert": False}
    report = create_report_tool(db, user_id, "doctor")
    message = "Glyco detected that the last 3 fasting glucose readings were above 7.0 mmol/L and generated a doctor report."
    alert = models.AgentAlert(
        user_id=user_id,
        severity="danger",
        title="Sustained elevated fasting glucose",
        message=message,
        recommended_action="Review the generated doctor report and contact your clinician if this pattern persists.",
        source_json={"report": report, "last_three": [row.fasting_glucose for row in reversed(logs)]},
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return {"proactive_alert": True, "message": message, "report_id": report["report_id"], "alert_id": alert.id}


# Saves both user and assistant messages into agent_memory for continuity.
def store_memory(db: Session, user_id: int, role: str, content: str, meta: dict[str, Any] | None = None) -> None:
    """Persist one conversation turn in agent memory."""
    db.add(models.AgentMemory(user_id=user_id, role=role, content=content, meta_json=meta or {}))
    db.commit()


# Reads recent history in Anthropic's expected user/assistant message format.
def load_memory_messages(db: Session, user_id: int, limit: int = 8) -> list[dict[str, str]]:
    """Load recent conversation history for the agent prompt."""
    rows = db.query(models.AgentMemory).filter(models.AgentMemory.user_id == user_id).order_by(models.AgentMemory.created_at.desc()).limit(limit).all()
    return [{"role": row.role, "content": row.content} for row in reversed(rows) if row.role in {"user", "assistant"}]


# Provides a deterministic local answer when the SDK or API key is absent, while
# still exercising the same tool dispatcher and recommendation reranker.
def fallback_agent_response(db: Session, user_id: int, message: str) -> dict[str, Any]:
    """Build a safe local response when Anthropic is not configured."""
    risk = get_risk_assessment_tool(db, user_id)
    trend = get_monitoring_trend_tool(db, user_id)
    recs = get_recommendations_tool(db, user_id, limit=3)
    tools = ["get_risk_assessment", "get_monitoring_trend", "get_recommendations"]
    response = (
        f"Current risk is {risk['random_forest']['risk_level']} with Bayesian posterior "
        f"{risk['bayesian']['posterior_mean']:.2f}. Monitoring trend is {trend.get('trend_label', 'unknown')}. "
        f"Top recommendation: {recs[0]['title']}. Glyco supports preparation and does not diagnose."
    )
    return {"response": response, "tools_used": tools, "proactive_alert": False}


# Runs Anthropic's tool-use loop until the model returns a normal text response.
def run_agent_chat(db: Session, user_id: int, message: str) -> dict[str, Any]:
    """Chat with the Anthropic tool-calling agent and return response metadata."""
    settings = get_settings()
    store_memory(db, user_id, "user", message)
    proactive = detect_glucose_anomaly_and_report(db, user_id)
    if anthropic is None or not settings.anthropic_api_key:
        result = fallback_agent_response(db, user_id, message)
        if proactive.get("proactive_alert"):
            result["response"] = f"{proactive['message']} {result['response']}"
            result["proactive_alert"] = True
        store_memory(db, user_id, "assistant", result["response"], {"tools_used": result["tools_used"], "proactive_alert": result["proactive_alert"]})
        return result

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    messages: list[dict[str, Any]] = load_memory_messages(db, user_id)
    tools_used: list[str] = []
    system = "You are Glyco, a clinical support agent. Use tools before answering, do not diagnose, and be concise."
    for _ in range(6):
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=900,
            system=system,
            tools=ANTHROPIC_TOOLS,
            messages=messages,
        )
        assistant_content = [block.model_dump() if hasattr(block, "model_dump") else block for block in response.content]
        messages.append({"role": "assistant", "content": assistant_content})
        tool_blocks = [block for block in response.content if getattr(block, "type", None) == "tool_use"]
        if not tool_blocks:
            text = "\n".join(getattr(block, "text", "") for block in response.content if getattr(block, "type", None) == "text").strip()
            if proactive.get("proactive_alert"):
                text = f"{proactive['message']}\n\n{text}"
            payload = {"response": text, "tools_used": tools_used, "proactive_alert": bool(proactive.get("proactive_alert"))}
            store_memory(db, user_id, "assistant", text, {"tools_used": tools_used, "proactive_alert": payload["proactive_alert"]})
            return payload
        tool_results = []
        for block in tool_blocks:
            tools_used.append(block.name)
            result = dispatch_tool(db, block.name, dict(block.input or {}))
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result, default=str)})
        messages.append({"role": "user", "content": tool_results})
    result = fallback_agent_response(db, user_id, message)
    result["tools_used"] = sorted(set(tools_used + result["tools_used"]))
    return result
