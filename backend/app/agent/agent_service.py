from __future__ import annotations

from statistics import mean
from sqlalchemy.orm import Session

from app.agent.bandit import RecommendationBandit, default_recommendations
from app.agent.llm_client import get_llm_client, get_llm_status
from app.agent.safety import safety_note, urgent_message_if_needed
from app.agent.tools import get_logs, get_profile, retrieve_guideline_snippets, run_risk_check, run_trend_check
from app.db import models
from app.services.bayesian import get_or_create_bayesian_state, serialize_bayesian_state


ACTION_KEYWORDS = {
    "nutrition": {"meal", "nutrition", "carb", "food", "diet", "snack", "protein", "fiber"},
    "activity": {"walk", "walking", "activity", "exercise", "movement", "steps"},
    "monitoring": {"log", "logging", "reading", "glucose", "track", "monitoring", "fasting"},
    "medication_check": {"medication", "medicine", "dose", "doctor", "clinician", "clinic"},
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
        return "nutrition"
    if pattern["slope"] and pattern["slope"] >= 15:
        return "activity"
    return "monitoring"


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


def build_agent_tool_pipeline(db: Session, user_id: int, message: str) -> dict:
    """Run the complete Glyco agent tool pipeline before response generation."""
    profile = get_profile(db, user_id)
    logs = get_logs(db, user_id, days=7)
    risk = run_risk_check(db, user_id)
    bayesian = serialize_bayesian_state(get_or_create_bayesian_state(db, user_id))
    trend = run_trend_check(db, user_id)
    snippets = retrieve_guideline_snippets(message)
    learning = _learning_summary(db, user_id)
    recommendations = RecommendationBandit(db, user_id).rerank(default_recommendations(), limit=3)
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
            "Trained RF risk model",
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
            "Trained glucose trend model",
            f"{trend.get('trend_label', 'unknown')} via {trend_version}",
            model_version=trend_version,
            details={"trend_score": trend.get("trend_score")},
        ),
        _tool_call("retrieve_guidelines", "Guidance retrieval", f"{len(snippets)} curated snippets"),
        _tool_call("read_agent_learning_memory", "Agent learning memory", learning["adaptation_note"], details=learning),
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
        "recommendations": recommendations,
        "tool_calls": tool_calls,
    }


def _fallback_answer(message: str, risk: dict, trend: dict, bayesian: dict, logs: list[dict], snippets: list[dict], urgent: str | None, learning: dict) -> str:
    if urgent:
        return urgent
    local_language = any(term in message.lower() for term in {"trebam", "brinuti", "sta", "doktor", "porodica", "sedmic", "tjedan"})
    glucose = [item["fasting_glucose"] for item in logs if item.get("fasting_glucose") is not None]
    avg = round(mean(glucose), 1) if glucose else None
    risk_level = risk.get("risk_level", "unknown")
    risk_version = risk.get("model_version", "unavailable")
    trend_label = trend.get("trend_label", "unknown")
    trend_version = trend.get("model_version", "unavailable")
    posterior = bayesian.get("posterior_mean")
    posterior_text = f"{posterior:.2f}" if isinstance(posterior, (int, float)) else "unknown"
    preferred_tone = learning.get("preferred_tone", "balanced")
    confirmed_actions = learning.get("confirmed_actions", [])
    next_action = learning.get("next_best_action") or {}
    pattern = learning.get("recent_glucose_pattern") or {}
    if local_language:
        parts = [f"Tvoj trenirani glucose trend model ({trend_version}) trenutno vidi obrazac kao {trend_label}. RF risk model ({risk_version}) procjenjuje {risk_level} rizik."]
        parts.append(f"Bayesian layer izgladjuje taj risk signal kroz vrijeme; trenutni posterior je {posterior_text}.")
        if avg is not None:
            parts.append(f"Prosjek zadnjih glucose ocitanja u vidljivom periodu je {avg} mg/dL.")
        if trend_label in {"watch", "concerning"} or risk_level == "high":
            parts.append("Ove sedmice vrijedi obratiti paznju: nastavi unositi ocitanja, pogledaj zadnje obroke/aktivnost i pripremi doctor summary ako povisene vrijednosti potraju.")
        else:
            parts.append("Trenutni obrazac izgleda stabilnije, pa je glavni korak dosljedno logovanje i pracenje promjena.")
        if next_action:
            parts.append(f"Zbog recent pattern={pattern.get('label', 'unknown')} i naucenog fokusa={learning.get('preferred_action_type', 'monitoring')}, Glyco preporucuje {next_action.get('title')}: {next_action.get('body')}")
        if snippets:
            parts.append(f"Guidance note: {snippets[0]['text']}")
        if confirmed_actions:
            parts.append(f"Agent je zapamtio ranije potvrdjen korak: {confirmed_actions[0]}.")
        if preferred_tone != "balanced":
            parts.append(f"Odgovor je prilagodjen tvom feedbacku: stil {preferred_tone}.")
    else:
        parts = [f"Your trained glucose trend model ({trend_version}) currently sees this as {trend_label}. The RF risk model ({risk_version}) estimates {risk_level} risk."]
        parts.append(f"The Bayesian layer smooths the RF risk signal over time; the current posterior is {posterior_text}.")
        if avg is not None:
            parts.append(f"Your recent average glucose over the visible log window is {avg} mg/dL.")
        if trend_label in {"watch", "concerning"} or risk_level == "high":
            parts.append("This is worth paying attention to this week: keep logging, review recent meals, and prepare a doctor summary if elevated readings continue.")
        else:
            parts.append("The current pattern looks more stable, so the main action is to keep logging consistently and watch for changes.")
        if next_action:
            parts.append(f"Because your recent pattern is {pattern.get('label', 'unknown')} and learned focus is {learning.get('preferred_action_type', 'monitoring')}, Glyco recommends {next_action.get('title')}: {next_action.get('body')}")
        if pattern.get("label"):
            parts.append(f"I chose that focus from your recent glucose pattern: {pattern['label']}.")
        if snippets:
            parts.append(f"Grounding note: {snippets[0]['text']}")
        if confirmed_actions:
            parts.append(f"I also remembered a previously confirmed action: {confirmed_actions[0]}.")
        if preferred_tone != "balanced":
            parts.append(f"This answer is adapted from your feedback preference: {preferred_tone} tone.")
    return " ".join(parts)


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
    tools_context = build_agent_tool_pipeline(db, user_id, message)
    messages = [
        {"role": "system", "content": "You are Glyco, a careful diabetes risk and monitoring assistant. Do not diagnose. Use the tool context and adapt to the user's saved feedback."},
        {"role": "user", "content": message},
    ]
    llm_client = get_llm_client()
    llm_answer = None if urgent else llm_client.generate(messages, tools_context)
    if _is_low_quality_llm_answer(llm_answer):
        llm_answer = None
    answer = llm_answer or _fallback_answer(
        message,
        tools_context["risk"],
        tools_context["trend"],
        tools_context["bayesian"],
        tools_context["logs"],
        tools_context["guidelines"],
        urgent,
        tools_context["learning"],
    )
    llm_status = get_llm_status()
    llm_provider = getattr(llm_client, "provider_name", "configured") if llm_answer else "fallback"
    llm_model = getattr(llm_client, "model_name", "configured") if llm_answer else "fallback"
    return {
        "answer": answer,
        "tool_calls": tools_context["tool_calls"],
        "guideline_snippets": tools_context["guidelines"],
        "safety_note": safety_note(),
        "patient_name": user.full_name if user else "Demo patient",
        "llm_mode": llm_provider if llm_answer else "fallback",
        "llm_model": llm_model if llm_answer else llm_status["model"],
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
