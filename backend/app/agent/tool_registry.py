from __future__ import annotations

from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from app.agent.bandit import RecommendationBandit, default_recommendations
from app.agent.tools import get_logs, get_profile, retrieve_guideline_snippets, run_risk_check, run_trend_check
from app.db import models
from app.ml.forecast_inference import get_forecast_service
from app.services.forecast_learning import apply_calibration
from app.services.bayesian import get_or_create_bayesian_state, serialize_bayesian_state


ACTION_KEYWORDS = {
    "nutrition": {"meal", "nutrition", "carb", "food", "diet", "snack", "protein", "fiber"},
    "activity": {"walk", "walking", "activity", "exercise", "movement", "steps"},
    "monitoring": {"log", "logging", "reading", "glucose", "track", "monitoring", "fasting"},
    "medication_check": {"medication", "medicine", "dose", "doctor", "clinician", "clinic"},
    "clinician_questions": {"question", "questions", "ask", "appointment", "doctor", "clinician"},
    "fasting_routine": {"fasting", "morning", "routine", "before", "breakfast"},
    "post_meal_review": {"post", "meal", "after", "lunch", "dinner", "portion"},
    "sleep_stress": {"sleep", "stress", "illness", "sick", "schedule"},
    "family_support": {"family", "caregiver", "support", "remind", "help"},
}


def _action_type_from_text(text: str | None) -> str | None:
    lowered = (text or "").lower()
    if any(keyword in lowered for keyword in {"walk", "walking", "exercise", "movement", "steps"}):
        return "activity"
    scores = {
        action_type: sum(1 for keyword in keywords if keyword in lowered)
        for action_type, keywords in ACTION_KEYWORDS.items()
    }
    best_action, best_score = sorted(scores.items(), key=lambda item: item[1], reverse=True)[0]
    return best_action if best_score > 0 else None


def _recent_glucose_pattern(db: Session, user_id: int) -> dict:
    rows = (
        db.query(models.HealthLog)
        .filter(models.HealthLog.user_id == user_id)
        .order_by(models.HealthLog.log_date.desc(), models.HealthLog.created_at.desc())
        .limit(7)
        .all()
    )
    ordered = list(reversed(rows))
    values = [row.glucose_level for row in ordered if row.glucose_level is not None]
    if not values:
        return {"label": "no-data", "average": None, "slope": None, "high_count": 0}
    slope = round(values[-1] - values[0], 1) if len(values) >= 2 else 0.0
    high_count = sum(1 for value in values if value >= 130)
    if high_count >= 3 or slope >= 15:
        label = "needs-attention"
    elif high_count or slope >= 5:
        label = "watch"
    else:
        label = "steady"
    return {"label": label, "average": round(mean(values), 1), "slope": slope, "high_count": high_count}


def _default_action_for_pattern(pattern: dict) -> str:
    if pattern["label"] == "no-data":
        return "monitoring"
    if pattern["high_count"] >= 3:
        return "post_meal_review"
    if pattern["slope"] and pattern["slope"] >= 15:
        return "activity"
    return "fasting_routine"


def build_learning_summary(db: Session, user_id: int) -> dict:
    rows = (
        db.query(models.AgentFeedback)
        .filter(models.AgentFeedback.user_id == user_id)
        .order_by(models.AgentFeedback.created_at.desc())
        .limit(12)
        .all()
    )
    if not rows:
        pattern = _recent_glucose_pattern(db, user_id)
        next_type = _default_action_for_pattern(pattern)
        return {
            "feedback_count": 0,
            "helpful_rate": None,
            "preferred_tone": "balanced",
            "confirmed_actions": [],
            "preferred_action_type": next_type,
            "avoided_action_types": [],
            "action_type_scores": {},
            "recent_glucose_pattern": pattern,
            "next_best_action": next((item for item in default_recommendations() if item["type"] == next_type), default_recommendations()[0]),
            "adaptation_note": "No feedback yet. The agent is adapting from recent glucose patterns and general clinical guidance.",
        }
    helpful_count = sum(1 for row in rows if row.helpful)
    tone_counts: dict[str, int] = {}
    action_scores = {name: 0 for name in ACTION_KEYWORDS}
    for row in rows:
        tone_counts[row.preferred_tone] = tone_counts.get(row.preferred_tone, 0) + 1
        action_type = _action_type_from_text(" ".join(filter(None, [row.confirmed_action, row.notes, row.message])))
        if action_type:
            action_scores[action_type] += 1 if row.helpful else -1
    preferred_tone = sorted(tone_counts.items(), key=lambda item: item[1], reverse=True)[0][0]
    confirmed_actions = [row.confirmed_action for row in rows if row.confirmed_action][:3]
    pattern = _recent_glucose_pattern(db, user_id)
    positive_scores = {key: value for key, value in action_scores.items() if value > 0}
    preferred_action_type = (
        sorted(positive_scores.items(), key=lambda item: item[1], reverse=True)[0][0]
        if positive_scores
        else _default_action_for_pattern(pattern)
    )
    avoided_action_types = [key for key, value in action_scores.items() if value < 0]
    next_best_action = next((item for item in default_recommendations() if item["type"] == preferred_action_type), default_recommendations()[0])
    return {
        "feedback_count": len(rows),
        "helpful_rate": round(helpful_count / len(rows), 2),
        "preferred_tone": preferred_tone,
        "confirmed_actions": confirmed_actions,
        "preferred_action_type": preferred_action_type,
        "avoided_action_types": avoided_action_types,
        "action_type_scores": action_scores,
        "recent_glucose_pattern": pattern,
        "next_best_action": next_best_action,
        "adaptation_note": (
            f"Personalized with {len(rows)} feedback signal(s): tone={preferred_tone}, "
            f"focus={preferred_action_type}, recent glucose pattern={pattern['label']}."
        ),
    }


def _risk_tool_label(model_version: str) -> str:
    return "Trained RF risk model" if model_version == "random-forest-0.2" else "Risk fallback scorer"


def _trend_tool_label(model_version: str) -> str:
    return "Trained glucose trend model" if model_version == "glucose-trend-random-forest-0.2" else "Monitoring fallback scorer"


def _tool_call(name: str, label: str, summary: str, **extra: object) -> dict:
    return {"name": name, "label": label, "status": "ok", "result_summary": summary, **extra}


def _as_mmol(value: float) -> float:
    """Convert legacy mg/dL health log values to mmol/L for forecast tools."""
    return float(value) / 18.015 if float(value) > 40 else float(value)


def _forecast_logs(db: Session, user_id: int) -> list[dict]:
    """Load recent user logs in the shape expected by the forecast service."""
    rows = (
        db.query(models.HealthLog)
        .filter(models.HealthLog.user_id == user_id)
        .order_by(models.HealthLog.created_at.desc(), models.HealthLog.log_date.desc())
        .limit(48)
        .all()
    )
    return [
        {
            "timestamp": row.created_at or row.log_date,
            "glucose_mmol": _as_mmol(row.glucose_level),
            "is_fasting": bool(row.is_fasting),
        }
        for row in reversed(rows)
        if row.glucose_level is not None
    ]


def _format_forecast(result: dict) -> str:
    """Format a forecast result as a compact readable tool response."""
    predictions = result["predictions"]
    intervals = result["confidence_intervals"]
    alert = "Low predicted" if result["predicted_low_alert"] else "High predicted" if result["predicted_high_alert"] else "None"
    return (
        "Glucose Forecast for next 4 hours:\n"
        f"Current: {result['current_glucose']} mmol/L\n"
        f"60 min:  {predictions['60']} mmol/L [{intervals['60']['low']}-{intervals['60']['high']}]\n"
        f"120 min: {predictions['120']} mmol/L [{intervals['120']['low']}-{intervals['120']['high']}]\n"
        f"180 min: {predictions['180']} mmol/L [{intervals['180']['low']}-{intervals['180']['high']}]\n"
        f"240 min: {predictions['240']} mmol/L [{intervals['240']['low']}-{intervals['240']['high']}]\n"
        f"Trend: {result['trend_direction']}\n"
        f"Alert: {alert}\n"
        f"Recommendation: {result['recommendation']}\n"
        f"Model: {result['model_version']} | Fallback: {result['used_fallback']}"
    )


def gemini_tool_declarations() -> list[dict[str, Any]]:
    return [
        {
            "name": "get_patient_profile",
            "description": "Load the latest patient profile used for diabetes risk context.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "get_glucose_logs",
            "description": "Load recent glucose logs. Use this before interpreting glucose trend or weekly concerns.",
            "parameters": {
                "type": "OBJECT",
                "properties": {"days": {"type": "INTEGER", "description": "Number of recent days to read, default 7."}},
            },
        },
        {
            "name": "run_trained_risk_model",
            "description": "Run or refresh the current diabetes risk assessment.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "get_bayesian_risk_state",
            "description": "Read the per-user Bayesian posterior risk state.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "run_trained_glucose_trend_model",
            "description": "Run or refresh the current glucose trend assessment.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "get_glucose_forecast",
            "description": "Predict the user's glucose trajectory for the next 4 hours (60, 120, 180, 240 minutes ahead). Returns predicted values, confidence intervals, trend direction (rising/stable/falling), alert flags, and a plain-language recommendation. Use this tool when the user asks what to expect, whether to eat something, what their glucose will do later today, or when they mention worrying about hypoglycemia or hyperglycemia.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "user_id": {"type": "INTEGER", "description": "The user's ID"},
                },
                "required": ["user_id"],
            },
        },
        {
            "name": "retrieve_guidelines",
            "description": "Retrieve curated safety and diabetes support guidance snippets for the user question.",
            "parameters": {
                "type": "OBJECT",
                "properties": {"query": {"type": "STRING", "description": "The user question or focus area."}},
            },
        },
        {
            "name": "read_agent_learning_memory",
            "description": "Read feedback-derived personalization memory, preferred tone, and recent glucose pattern.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "rank_recommendations_with_thompson_sampling",
            "description": "Rank candidate recommendations using Thompson Sampling bandit state.",
            "parameters": {
                "type": "OBJECT",
                "properties": {"limit": {"type": "INTEGER", "description": "Number of recommendations to return, default 3."}},
            },
        },
    ]


def execute_agent_tool(db: Session, user_id: int, name: str, args: dict[str, Any] | None, user_message: str) -> tuple[Any, dict]:
    args = args or {}
    if name == "get_patient_profile":
        result = get_profile(db, user_id)
        call = _tool_call(name, "Patient profile reader", "Loaded latest profile" if result else "No profile found")
        return result, call
    if name == "get_glucose_logs":
        days = int(args.get("days") or 7)
        result = get_logs(db, user_id, days=max(1, min(days, 30)))
        call = _tool_call(name, "Glucose log reader", f"Loaded {len(result)} glucose readings from the recent window")
        return result, call
    if name == "run_trained_risk_model":
        result = run_risk_check(db, user_id)
        version = result.get("model_version", "unavailable")
        call = _tool_call(
            name,
            _risk_tool_label(version),
            f"{result.get('risk_level', 'unknown')} risk via {version}",
            model_version=version,
            details={"risk_probability": result.get("risk_probability")},
        )
        return result, call
    if name == "get_bayesian_risk_state":
        result = serialize_bayesian_state(get_or_create_bayesian_state(db, user_id))
        posterior = result.get("posterior_mean")
        interval = result.get("credible_interval") or {}
        summary = (
            f"posterior {posterior:.2f}, interval {interval.get('low', 0):.2f}-{interval.get('high', 0):.2f}, updates {result.get('number_of_updates', 0)}"
            if isinstance(posterior, (int, float))
            else "No Bayesian posterior available"
        )
        return result, _tool_call(name, "Bayesian risk layer", summary, details=result)
    if name == "run_trained_glucose_trend_model":
        result = run_trend_check(db, user_id)
        version = result.get("model_version", "unavailable")
        call = _tool_call(
            name,
            _trend_tool_label(version),
            f"{result.get('trend_label', 'unknown')} via {version}",
            model_version=version,
            details={"trend_score": result.get("trend_score")},
        )
        return result, call
    if name == "get_glucose_forecast":
        result = apply_calibration(db, get_forecast_service().predict(user_id, _forecast_logs(db, user_id)))
        call = _tool_call(
            name,
            "Forecast",
            f"{result['trend_direction']} forecast via {result['model_version']}",
            model_version=result["model_version"],
            details=result,
            readable=_format_forecast(result),
        )
        return result, call
    if name == "retrieve_guidelines":
        result = retrieve_guideline_snippets(str(args.get("query") or user_message))
        return result, _tool_call(name, "Guidance retrieval", f"{len(result)} curated snippets")
    if name == "read_agent_learning_memory":
        result = build_learning_summary(db, user_id)
        return result, _tool_call(name, "Agent learning memory", result["adaptation_note"], details=result)
    if name == "rank_recommendations_with_thompson_sampling":
        limit = int(args.get("limit") or 3)
        forecast = apply_calibration(db, get_forecast_service().predict(user_id, _forecast_logs(db, user_id)))
        result = RecommendationBandit(db, user_id).rerank(default_recommendations(), limit=max(1, min(limit, 4)), forecast=forecast)
        top = result[0] if result else {}
        return result, _tool_call(name, "Adaptive recommendation ranker", top.get("title", "No recommendations"), details={"ranked_recommendations": result})
    return {"error": f"Unknown tool: {name}"}, {"name": name, "label": name, "status": "error", "result_summary": "Unknown tool"}


def context_from_tool_results(results: dict[str, Any]) -> dict:
    return {
        "profile": results.get("get_patient_profile"),
        "logs": results.get("get_glucose_logs") or [],
        "risk": results.get("run_trained_risk_model") or {},
        "bayesian": results.get("get_bayesian_risk_state") or {},
        "trend": results.get("run_trained_glucose_trend_model") or {},
        "forecast": results.get("get_glucose_forecast"),
        "guidelines": results.get("retrieve_guidelines") or [],
        "learning": results.get("read_agent_learning_memory") or {},
        "recommendations": results.get("rank_recommendations_with_thompson_sampling") or [],
    }
