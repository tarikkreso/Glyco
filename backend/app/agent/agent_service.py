from __future__ import annotations

from statistics import mean
from sqlalchemy.orm import Session

from app.agent.bandit import RecommendationBandit, default_recommendations
from app.agent.llm_client import get_llm_client, get_llm_status, build_rich_system_prompt
from app.agent.safety import safety_note, urgent_message_if_needed
from app.agent.tools import get_logs, get_profile, retrieve_guideline_snippets, run_risk_check, run_trend_check
from app.db import models
from app.ml.forecast_inference import get_forecast_service
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


def _learning_summary(db: Session, user_id: int) -> dict:
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


def record_agent_feedback(
    db: Session,
    user_id: int,
    message: str,
    helpful: bool,
    preferred_tone: str = "balanced",
    confirmed_action: str | None = None,
    notes: str | None = None,
) -> models.AgentFeedback:
    """Store user feedback for personalization memory."""
    row = models.AgentFeedback(
        user_id=user_id,
        message=message,
        helpful=helpful,
        preferred_tone=preferred_tone.strip().lower() or "balanced",
        confirmed_action=confirmed_action,
        notes=notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _tool_call(name: str, label: str, summary: str, **extra: object) -> dict:
    """Create one visible agent evidence item for the UI and tests."""
    return {"name": name, "label": label, "status": "ok", "result_summary": summary, **extra}


def _as_mmol(value: float) -> float:
    """Convert legacy mg/dL readings to mmol/L for forecast context."""
    return float(value) / 18.015 if float(value) > 40 else float(value)


def _forecast_row_to_dict(row: models.GlucoseForecast) -> dict:
    """Serialize a stored forecast row into the standard forecast context shape."""
    return {
        "user_id": row.user_id,
        "current_glucose": row.current_glucose,
        "predictions": {
            "60": row.prediction_60min,
            "120": row.prediction_120min,
            "180": row.prediction_180min,
            "240": row.prediction_240min,
        },
        "confidence_intervals": {
            "60": {"low": row.ci_60_low, "high": row.ci_60_high},
            "120": {"low": row.ci_120_low, "high": row.ci_120_high},
            "180": {"low": row.ci_180_low, "high": row.ci_180_high},
            "240": {"low": row.ci_240_low, "high": row.ci_240_high},
        },
        "trend_direction": row.trend_direction,
        "predicted_low_alert": row.predicted_low_alert,
        "predicted_high_alert": row.predicted_high_alert,
        "recommendation": row.recommendation,
        "model_version": row.model_version,
        "used_fallback": row.used_fallback,
        "horizon_minutes": [60, 120, 180, 240],
        "created_at": row.created_at,
    }


def _forecast_logs(db: Session, user_id: int) -> list[dict]:
    """Load recent health logs for forecast context construction."""
    rows = (
        db.query(models.HealthLog)
        .filter(models.HealthLog.user_id == user_id)
        .order_by(models.HealthLog.created_at.desc(), models.HealthLog.log_date.desc())
        .limit(48)
        .all()
    )
    return [
        {"timestamp": row.created_at or row.log_date, "glucose_mmol": _as_mmol(row.glucose_level)}
        for row in reversed(rows)
        if row.glucose_level is not None
    ]


def _save_forecast_context(db: Session, result: dict) -> models.GlucoseForecast:
    """Persist a freshly generated forecast for agent context reuse."""
    predictions = result["predictions"]
    intervals = result["confidence_intervals"]
    row = models.GlucoseForecast(
        user_id=result["user_id"],
        current_glucose=result["current_glucose"],
        prediction_60min=predictions["60"],
        prediction_120min=predictions["120"],
        prediction_180min=predictions["180"],
        prediction_240min=predictions["240"],
        ci_60_low=intervals["60"]["low"],
        ci_60_high=intervals["60"]["high"],
        ci_120_low=intervals["120"]["low"],
        ci_120_high=intervals["120"]["high"],
        ci_180_low=intervals["180"]["low"],
        ci_180_high=intervals["180"]["high"],
        ci_240_low=intervals["240"]["low"],
        ci_240_high=intervals["240"]["high"],
        trend_direction=result["trend_direction"],
        predicted_low_alert=result["predicted_low_alert"],
        predicted_high_alert=result["predicted_high_alert"],
        recommendation=result["recommendation"],
        model_version=result["model_version"],
        used_fallback=result["used_fallback"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _load_forecast_context_sync(user_id: int, db: Session) -> dict | None:
    """Load or synchronously create the latest forecast context for this user."""
    row = (
        db.query(models.GlucoseForecast)
        .filter(models.GlucoseForecast.user_id == user_id)
        .order_by(models.GlucoseForecast.created_at.desc())
        .first()
    )
    if row:
        return _forecast_row_to_dict(row)
    logs = _forecast_logs(db, user_id)
    if len(logs) < 4:
        return None
    result = get_forecast_service().predict(user_id, logs)
    return _forecast_row_to_dict(_save_forecast_context(db, result))


async def _load_forecast_context(user_id: int, db: Session) -> dict | None:
    """
    Load the latest glucose forecast for this user.
    If no forecast exists yet but there are enough logs,
    trigger a new forecast synchronously before returning.
    Returns None if there are fewer than 4 logs.
    """
    return _load_forecast_context_sync(user_id, db)


def _get_care_plan_for_agent(db: Session, user_id: int) -> dict:
    """
    Retrieve the latest cached diet care plan from the database.
    If no cached plan is found, fall back to calculating the local fallback plan.
    This avoids nesting external LLM API calls during a chat session.
    """
    cached = (
        db.query(models.Report)
        .filter(
            models.Report.user_id == user_id,
            models.Report.report_type == "diet_care_plan",
        )
        .order_by(models.Report.created_at.desc())
        .first()
    )
    if cached and cached.content_json:
        return cached.content_json
    
    from app.services.care_plan import _plan_context, _fallback_plan
    context = _plan_context(db, user_id)
    return _fallback_plan(context)


def _risk_tool_label(model_version: str) -> str:
    return "Trained RF risk model" if model_version == "random-forest-0.2" else "Risk fallback scorer"


def _trend_tool_label(model_version: str) -> str:
    return "Trained glucose trend model" if model_version == "glucose-trend-random-forest-0.2" else "Monitoring fallback scorer"


def build_agent_tool_pipeline(db: Session, user_id: int, message: str) -> dict:
    """Run the complete Glyco agent tool pipeline before response generation."""
    profile = get_profile(db, user_id)
    logs = get_logs(db, user_id, days=7)
    risk = run_risk_check(db, user_id)
    bayesian = serialize_bayesian_state(get_or_create_bayesian_state(db, user_id))
    trend = run_trend_check(db, user_id)
    snippets = retrieve_guideline_snippets(message)
    learning = _learning_summary(db, user_id)
    forecast = _load_forecast_context_sync(user_id, db)
    recommendations = RecommendationBandit(db, user_id).rerank(default_recommendations(), limit=3, forecast=forecast)
    care_plan = _get_care_plan_for_agent(db, user_id)
    
    risk_version = risk.get("model_version", "unavailable")
    trend_version = trend.get("model_version", "unavailable")
    posterior = bayesian.get("posterior_mean")
    interval = bayesian.get("credible_interval") or {}
    top_recommendation = recommendations[0] if recommendations else {}
    tool_calls = [
        _tool_call("get_patient_profile", "Patient profile reader", "Loaded latest profile" if profile else "No profile found"),
        _tool_call("get_glucose_logs", "Glucose log reader", f"Loaded {len(logs)} glucose readings from the recent window"),
        _tool_call(
            "run_trained_risk_model",
            _risk_tool_label(risk_version),
            f"{risk.get('risk_level', 'unknown')} risk via {risk_version}",
            model_version=risk_version,
            details={"risk_probability": risk.get("risk_probability")},
        ),
        _tool_call(
            "get_bayesian_risk_state",
            "Bayesian risk layer",
            f"posterior {posterior:.2f}, interval {interval.get('low', 0):.2f}-{interval.get('high', 0):.2f}, updates {bayesian.get('number_of_updates', 0)}" if isinstance(posterior, (int, float)) else "No Bayesian posterior available",
            details=bayesian,
        ),
        _tool_call(
            "run_trained_glucose_trend_model",
            _trend_tool_label(trend_version),
            f"{trend.get('trend_label', 'unknown')} via {trend_version}",
            model_version=trend_version,
            details={"trend_score": trend.get("trend_score")},
        ),
        _tool_call("retrieve_guidelines", "Guidance retrieval", f"{len(snippets)} curated snippets"),
        _tool_call("read_agent_learning_memory", "Agent learning memory", learning["adaptation_note"], details=learning),
        _tool_call("retrieve_care_plan", "Care plan loader", f"Loaded care plan (source: {care_plan.get('source', 'unknown')})"),
        *(
            [
                _tool_call(
                    "forecast_context",
                    "Forecast",
                    f"{forecast['trend_direction']} forecast via {forecast['model_version']}",
                    details=forecast,
                )
            ]
            if forecast is not None
            else []
        ),
        _tool_call(
            "rank_recommendations_with_thompson_sampling",
            "Adaptive recommendation ranker",
            top_recommendation.get("title", "No recommendations"),
            details={"ranked_recommendations": recommendations},
        ),
    ]
    return {
        "profile": profile,
        "logs": logs,
        "risk": risk,
        "bayesian": bayesian,
        "trend": trend,
        "guidelines": snippets,
        "learning": learning,
        "forecast": forecast,
        "recommendations": recommendations,
        "care_plan": care_plan,
        "tool_calls": tool_calls,
    }


def _load_chat_history(db: Session, user_id: int, limit: int = 10) -> list[dict]:
    rows = (
        db.query(models.AgentMemory)
        .filter(models.AgentMemory.user_id == user_id)
        .order_by(models.AgentMemory.created_at.desc())
        .limit(limit)
        .all()
    )
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


def _save_chat_message(db: Session, user_id: int, role: str, content: str) -> None:
    row = models.AgentMemory(user_id=user_id, role=role, content=content)
    db.add(row)
    db.commit()


def _is_low_quality_llm_answer(answer: str | None) -> bool:
    if not answer:
        return True
    lowered = answer.lower()
    blocked_fragments = {
        "tool context",
        "**profile**",
        "'risk_probability'",
        "'trend_label'",
        "{'date'",
        "profile:",
        "logs:",
    }
    return any(fragment in lowered for fragment in blocked_fragments)


def chat_with_agent(db: Session, user_id: int, message: str) -> dict:
    """Build an agent response from trained-model tools and adaptive memory."""
    user = db.get(models.User, user_id)
    urgent = urgent_message_if_needed(message)
    
    if urgent:
        tools_context = build_agent_tool_pipeline(db, user_id, message)
        return {
            "answer": urgent,
            "tool_calls": tools_context["tool_calls"],
            "guideline_snippets": tools_context["guidelines"],
            "safety_note": safety_note(),
            "patient_name": user.full_name if user else "Demo patient",
            "llm_mode": "safety",
            "llm_model": "urgent-safety",
            "learning_summary": tools_context["learning"],
            "recommendations": tools_context["recommendations"],
        }

    tools_context = build_agent_tool_pipeline(db, user_id, message)
    
    # 1. Load history from AgentMemory (continuity of last 10 messages)
    history = _load_chat_history(db, user_id, limit=10)
    
    # 2. Build detailed system prompt
    system_prompt = build_rich_system_prompt(tools_context)
    
    # 3. Assemble full messages list
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]
    
    llm_client = get_llm_client()
    llm_answer = llm_client.generate(messages, tools_context)
    
    if _is_low_quality_llm_answer(llm_answer):
        llm_answer = None
        
    llm_status = get_llm_status()
    llm_error_detail = None
    for candidate in getattr(llm_client, "clients", []) or []:
        detail = getattr(candidate, "last_error", None)
        if detail:
            llm_error_detail = str(detail)
            break

    if not llm_answer:
        hint = "Please verify your LLM provider API key and try again."
        if llm_status.get("provider") == "deepseek":
            deepseek_url = (llm_status.get("deepseek") or {}).get("url", "")
            if "openrouter.ai" in str(deepseek_url).lower():
                hint = "If you're using an OpenRouter key, you may need credits/billing enabled (OpenRouter can return HTTP 402)."
            else:
                hint = "Set DEEPSEEK_API_KEY (or OPENROUTER_API_KEY) and ensure the model/url are valid."
        elif llm_status.get("provider") == "gemini":
            hint = "Set GEMINI_API_KEY and try again."
        elif llm_status.get("provider") == "groq":
            hint = "Set GROQ_API_KEY and ensure the model/url are valid."
        elif llm_status.get("provider") == "ollama":
            hint = "Ensure Ollama is running and GLYCO_OLLAMA_URL is reachable."

        detail_suffix = f" (Details: {llm_error_detail})" if llm_error_detail else ""
        answer = f"Error: Glyco chatbot couldn't reach the configured LLM provider.{detail_suffix} {hint}"
        llm_mode = "error"
        llm_model = "error"
    else:
        answer = llm_answer
        llm_mode = getattr(llm_client, "provider_name", "configured")
        llm_model = getattr(llm_client, "model_name", "configured")
        if llm_model == "fallback":
            llm_model = llm_status["model"]
        
        # Save both user query and assistant response to conversational history memory
        _save_chat_message(db, user_id, "user", message)
        _save_chat_message(db, user_id, "assistant", answer)
        
    return {
        "answer": answer,
        "tool_calls": tools_context["tool_calls"],
        "guideline_snippets": tools_context["guidelines"],
        "safety_note": safety_note(),
        "patient_name": user.full_name if user else "Demo patient",
        "llm_mode": llm_mode,
        "llm_model": llm_model,
        "learning_summary": tools_context["learning"],
        "recommendations": tools_context["recommendations"],
    }


def build_agent_insight(db: Session, user_id: int) -> dict:
    """Build an insight summary for the dashboard using agent context."""
    response = chat_with_agent(db, user_id, "Trebam li se brinuti ovaj tjedan? Summarize what changed, why it matters, what to do next, and what to ask my doctor.")
    risk_label = next((item["result_summary"] for item in response["tool_calls"] if item["name"] == "run_trained_risk_model"), "unknown")
    trend_label = next((item["result_summary"] for item in response["tool_calls"] if item["name"] == "run_trained_glucose_trend_model"), "unknown")
    return {
        "title": "Glyco Insight",
        "patient_name": response["patient_name"],
        "what_changed": response["answer"],
        "why_it_matters": f"The agent used the risk model ({risk_label}), trend model ({trend_label}), recent logs, curated guidance snippets, and personalization memory.",
        "what_to_do_next": [
            "Follow the agent's weekly recommendation.",
            "Add another glucose log after the next reading.",
            "Generate a doctor report if the trend remains watch or concerning.",
        ],
        "what_to_ask_your_doctor": [
            "Do these recent readings change my monitoring schedule?",
            "Which risk factor should I prioritize first?",
            "What threshold should prompt me to contact the clinic?",
        ],
        "confidence_note": response["safety_note"],
        "tool_calls": response["tool_calls"],
        "guideline_snippets": response["guideline_snippets"],
        "llm_mode": response["llm_mode"],
        "llm_model": response["llm_model"],
        "learning_summary": response["learning_summary"],
    }


def proactive_check(db: Session, user_id: int) -> dict:
    """Create a proactive alert when model state suggests extra attention."""
    # Proactive checks turn passive model output into agent behavior: Glyco watches
    # trend state and creates a user-visible alert only when action is useful.
    trend = run_trend_check(db, user_id)
    should_alert = trend.get("trend_label") in {"watch", "concerning"}
    if not should_alert:
        return {"created": False, "reason": "stable"}
    severity = "danger" if trend.get("trend_label") == "concerning" else "warning"
    title = "Concerning trend detected" if severity == "danger" else "Watch pattern detected"
    message = f"Glyco detected a {trend.get('trend_label')} glucose monitoring state."
    action = "Review recent logs and generate a doctor summary if elevated readings continue."
    existing = (
        db.query(models.AgentAlert)
        .filter(models.AgentAlert.user_id == user_id, models.AgentAlert.title == title, models.AgentAlert.acknowledged_at.is_(None))
        .order_by(models.AgentAlert.created_at.desc())
        .first()
    )
    if existing:
        return {"created": False, "reason": "existing", "alert_id": existing.id}
    alert = models.AgentAlert(
        user_id=user_id,
        severity=severity,
        title=title,
        message=message,
        recommended_action=action,
        source_json={"trend": trend},
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return {"created": True, "alert_id": alert.id, "severity": severity, "title": title}
