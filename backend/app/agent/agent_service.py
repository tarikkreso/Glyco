from __future__ import annotations

from statistics import mean
from sqlalchemy.orm import Session

from app.agent.bandit import RecommendationBandit, default_recommendations
from app.agent.llm_client import get_llm_client, get_llm_status
from app.agent.safety import safety_note, urgent_message_if_needed
from app.agent.tools import get_logs, get_profile, retrieve_guideline_snippets, run_risk_check, run_trend_check
from app.db import models


def _learning_summary(db: Session, user_id: int) -> dict:
    rows = (
        db.query(models.AgentFeedback)
        .filter(models.AgentFeedback.user_id == user_id)
        .order_by(models.AgentFeedback.created_at.desc())
        .limit(12)
        .all()
    )
    if not rows:
        return {
            "feedback_count": 0,
            "helpful_rate": None,
            "preferred_tone": "balanced",
            "confirmed_actions": [],
            "adaptation_note": "No feedback yet. The agent is using general clinical guidance and model outputs.",
        }
    helpful_count = sum(1 for row in rows if row.helpful)
    tone_counts: dict[str, int] = {}
    for row in rows:
        tone_counts[row.preferred_tone] = tone_counts.get(row.preferred_tone, 0) + 1
    preferred_tone = sorted(tone_counts.items(), key=lambda item: item[1], reverse=True)[0][0]
    confirmed_actions = [row.confirmed_action for row in rows if row.confirmed_action][:3]
    return {
        "feedback_count": len(rows),
        "helpful_rate": round(helpful_count / len(rows), 2),
        "preferred_tone": preferred_tone,
        "confirmed_actions": confirmed_actions,
        "adaptation_note": f"Personalized with {len(rows)} recent feedback item(s); preferred tone is {preferred_tone}.",
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


def _fallback_answer(message: str, risk: dict, trend: dict, logs: list[dict], snippets: list[dict], urgent: str | None, learning: dict) -> str:
    if urgent:
        return urgent
    local_language = any(term in message.lower() for term in {"trebam", "brinuti", "sta", "doktor", "porodica", "sedmic", "tjedan"})
    glucose = [item["fasting_glucose"] for item in logs if item.get("fasting_glucose") is not None]
    avg = round(mean(glucose), 1) if glucose else None
    risk_level = risk.get("risk_level", "unknown")
    trend_label = trend.get("trend_label", "unknown")
    preferred_tone = learning.get("preferred_tone", "balanced")
    confirmed_actions = learning.get("confirmed_actions", [])
    if local_language:
        parts = [f"Prema Glyco podacima, trenutni nivo rizika je {risk_level}, a monitoring trend je {trend_label}."]
        if avg is not None:
            parts.append(f"Prosjek zadnjih fasting glucose ocitanja u vidljivom periodu je {avg} mg/dL.")
        if trend_label in {"watch", "concerning"} or risk_level == "high":
            parts.append("Ove sedmice vrijedi obratiti paznju: nastavi unositi ocitanja, pogledaj zadnje obroke/aktivnost i pripremi doctor summary ako povisene vrijednosti potraju.")
        else:
            parts.append("Trenutni obrazac izgleda stabilnije, pa je glavni korak dosljedno logovanje i pracenje promjena.")
        if snippets:
            parts.append(f"Guidance note: {snippets[0]['text']}")
        if confirmed_actions:
            parts.append(f"Agent je zapamtio ranije potvrdjen korak: {confirmed_actions[0]}.")
        if preferred_tone != "balanced":
            parts.append(f"Odgovor je prilagodjen tvom feedbacku: stil {preferred_tone}.")
    else:
        parts = [f"Based on your Glyco data, your current risk level is {risk_level} and your monitoring trend is {trend_label}."]
        if avg is not None:
            parts.append(f"Your recent average fasting glucose over the visible log window is {avg} mg/dL.")
        if trend_label in {"watch", "concerning"} or risk_level == "high":
            parts.append("This is worth paying attention to this week: keep logging, review recent meals/activity, and prepare a doctor summary if elevated readings continue.")
        else:
            parts.append("The current pattern looks more stable, so the main action is to keep logging consistently and watch for changes.")
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
    """Build the legacy agent response with reranked recommendations."""
    user = db.get(models.User, user_id)
    urgent = urgent_message_if_needed(message)
    learning = _learning_summary(db, user_id)
    profile = get_profile(db, user_id)
    logs = get_logs(db, user_id, days=7)
    risk = run_risk_check(db, user_id)
    trend = run_trend_check(db, user_id)
    snippets = retrieve_guideline_snippets(message)
    recommendations = RecommendationBandit(db, user_id).rerank(default_recommendations(), limit=3)
    tool_calls = [
        {"name": "get_profile", "status": "ok", "result_summary": "Loaded latest profile" if profile else "No profile found"},
        {"name": "get_logs", "status": "ok", "result_summary": f"Loaded {len(logs)} logs from the recent window"},
        {"name": "run_risk_check", "status": "ok", "result_summary": risk.get("risk_level", "unknown")},
        {"name": "run_trend_check", "status": "ok", "result_summary": trend.get("trend_label", "unknown")},
        {"name": "retrieve_guidelines", "status": "ok", "result_summary": f"{len(snippets)} curated snippets"},
        {"name": "read_agent_memory", "status": "ok", "result_summary": learning["adaptation_note"]},
        {"name": "get_recommendations", "status": "ok", "result_summary": recommendations[0]["title"] if recommendations else "No recommendations"},
    ]
    # Agent orchestration: gather patient state, model outputs, retrieval snippets,
    # safety state, and memory before any LLM/fallback generation happens.
    tools_context = {"profile": profile, "logs": logs, "risk": risk, "trend": trend, "guidelines": snippets, "learning": learning, "recommendations": recommendations}
    messages = [
        {"role": "system", "content": "You are Glyco, a careful diabetes risk and monitoring assistant. Do not diagnose. Use the tool context and adapt to the user's saved feedback."},
        {"role": "user", "content": message},
    ]
    llm_client = get_llm_client()
    llm_answer = None if urgent else llm_client.generate(messages, tools_context)
    if _is_low_quality_llm_answer(llm_answer):
        llm_answer = None
    answer = llm_answer or _fallback_answer(message, risk, trend, logs, snippets, urgent, learning)
    llm_status = get_llm_status()
    llm_provider = getattr(llm_client, "provider_name", "configured") if llm_answer else "fallback"
    llm_model = getattr(llm_client, "model_name", "configured") if llm_answer else "fallback"
    return {
        "answer": answer,
        "tool_calls": tool_calls,
        "guideline_snippets": snippets,
        "safety_note": safety_note(),
        "patient_name": user.full_name if user else "Demo patient",
        "llm_mode": llm_provider if llm_answer else "fallback",
        "llm_model": llm_model if llm_answer else llm_status["model"],
        "learning_summary": learning,
        "recommendations": recommendations,
    }


def build_agent_insight(db: Session, user_id: int) -> dict:
    """Build an insight summary for the dashboard using agent context."""
    response = chat_with_agent(db, user_id, "Trebam li se brinuti ovaj tjedan? Summarize what changed, why it matters, what to do next, and what to ask my doctor.")
    risk_label = next((item["result_summary"] for item in response["tool_calls"] if item["name"] == "run_risk_check"), "unknown")
    trend_label = next((item["result_summary"] for item in response["tool_calls"] if item["name"] == "run_trend_check"), "unknown")
    return {
        "title": "Glyco Insight",
        "patient_name": response["patient_name"],
        "what_changed": response["answer"],
        "why_it_matters": f"The agent used the risk model ({risk_label}), trend model ({trend_label}), recent logs, curated guidance snippets, and personalization memory.",
        "what_to_do_next": [
            "Follow the agent's weekly recommendation.",
            "Add another glucose log after the next fasting reading.",
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
    # risk/trend state and creates a user-visible alert only when action is useful.
    trend = run_trend_check(db, user_id)
    risk = run_risk_check(db, user_id)
    should_alert = trend.get("trend_label") in {"watch", "concerning"} or risk.get("risk_level") == "high"
    if not should_alert:
        return {"created": False, "reason": "stable"}
    severity = "danger" if trend.get("trend_label") == "concerning" else "warning"
    title = "Concerning trend detected" if severity == "danger" else "Watch pattern detected"
    message = f"Glyco detected a {trend.get('trend_label')} monitoring state with {risk.get('risk_level')} risk."
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
        source_json={"trend": trend, "risk": risk},
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return {"created": True, "alert_id": alert.id, "severity": severity, "title": title}
