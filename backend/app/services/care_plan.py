from __future__ import annotations

import json
import logging
import os
from statistics import mean
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.agent.bandit import RecommendationBandit, default_recommendations
from app.agent.guidelines import retrieve_guidelines
from app.db import models
from app.services.bayesian import get_or_create_bayesian_state, serialize_bayesian_state
from app.services.assessments import create_monitoring_assessment, create_risk_assessment

logger = logging.getLogger(__name__)


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 1) if values else None


def _latest_risk(db: Session, user_id: int):
    row = db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user_id).order_by(models.RiskAssessment.created_at.desc()).first()
    profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).order_by(models.Profile.created_at.desc()).first()
    if profile and not row:
        create_risk_assessment(db, profile)
        row = db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user_id).order_by(models.RiskAssessment.created_at.desc()).first()
    return row, profile


def _latest_monitoring(db: Session, user_id: int):
    row = db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user_id).order_by(models.MonitoringAssessment.created_at.desc()).first()
    latest_log = db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id).order_by(models.HealthLog.created_at.desc()).first()
    if not row or (latest_log and latest_log.created_at > row.created_at):
        return create_monitoring_assessment(db, user_id)
    return {
        "trend_label": row.trend_label,
        "trend_score": row.trend_score,
        "anomaly_flags": row.anomaly_flags_json,
        "summary": row.summary_json,
        "model_version": row.model_version,
    }


def _plan_context(db: Session, user_id: int) -> dict:
    user = db.get(models.User, user_id)
    risk, profile = _latest_risk(db, user_id)
    monitoring = _latest_monitoring(db, user_id)
    logs = db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id).order_by(models.HealthLog.log_date.asc(), models.HealthLog.created_at.asc()).all()
    recent = logs[-14:]
    fasting_values = [log.glucose_level for log in recent if log.glucose_level is not None and log.is_fasting]
    post_values = [log.glucose_level for log in recent if log.glucose_level is not None and not log.is_fasting]
    latest = recent[-1] if recent else None
    recommendations = RecommendationBandit(db, user_id).rerank(default_recommendations(), limit=4)
    return {
        "user": {"id": user_id, "name": user.full_name if user else "Demo patient"},
        "profile": {
            "age": profile.age if profile else None,
            "bmi": profile.bmi if profile else None,
            "high_bp": profile.high_bp if profile else None,
            "high_chol": profile.high_chol if profile else None,
            "phys_activity": profile.phys_activity if profile else None,
            "general_health": profile.general_health if profile else None,
        },
        "risk": {
            "risk_level": risk.risk_level if risk else "unknown",
            "risk_probability": risk.risk_probability if risk else None,
            "model_version": risk.model_version if risk else "unavailable",
        },
        "monitoring": monitoring,
        "bayesian": serialize_bayesian_state(get_or_create_bayesian_state(db, user_id)),
        "logs": {
            "count": len(recent),
            "latest_glucose": latest.glucose_level if latest else None,
            "latest_is_fasting": latest.is_fasting if latest else None,
            "avg_fasting": _avg(fasting_values),
            "avg_post_meal": _avg(post_values),
            "fasting_count": len(fasting_values),
            "post_meal_count": len(post_values),
        },
        "recommendations": recommendations,
        "guidelines": retrieve_guidelines("care plan nutrition activity fasting post meal clinician support", limit=4),
    }


def _fallback_plan(context: dict) -> dict:
    risk = context["risk"]
    monitoring = context["monitoring"]
    logs = context["logs"]
    profile = context["profile"]
    top_action = context["recommendations"][0] if context["recommendations"] else {}
    latest_type = "fasting" if logs["latest_is_fasting"] else "not-fasting"
    latest_text = f"latest {latest_type} reading {logs['latest_glucose']} mg/dL" if logs["latest_glucose"] is not None else "no recent reading"
    trend = monitoring.get("trend_label", "unknown")
    risk_level = risk.get("risk_level", "unknown")

    prefer = [
        "Protein or fiber with the meal most likely to affect the next reading",
        "Water or unsweetened drinks around logging times",
        "Vegetables, beans, yogurt, eggs, fish, or lean proteins as practical anchors",
    ]
    limit = [
        "Sugary drinks and large refined-carb portions when readings are elevated",
        "Late-night snacks if morning fasting readings are trending upward",
        "Changing medication or treatment without a clinician",
    ]
    weekly = [
        f"Log at least 4 readings and label each one fasting or not fasting; current 14-day count is {logs['count']}.",
        top_action.get("body", "Keep the next glucose reading consistent so Glyco can compare the pattern."),
        f"Prepare one clinician question if the trend stays {trend} or risk remains {risk_level}.",
    ]
    if logs["avg_fasting"] is not None and logs["avg_fasting"] >= 130:
        weekly.insert(1, f"Prioritize morning consistency: recent fasting average is {logs['avg_fasting']} mg/dL.")
    if logs["avg_post_meal"] is not None and logs["avg_post_meal"] >= 180:
        weekly.insert(1, f"Review the meal before higher not-fasting readings; recent not-fasting average is {logs['avg_post_meal']} mg/dL.")
    if profile.get("phys_activity") is False:
        weekly.append("Add a short, comfortable walk after one meal if it is safe for you.")

    return {
        "user_id": context["user"]["id"],
        "source": "data-fallback",
        "direction": f"Personalized glucose support based on {latest_text}, {trend} monitoring trend, and {risk_level} risk.",
        "prefer": prefer,
        "limit": limit,
        "sample_day": [
            "Breakfast: choose a steady option and log fasting first if this is a fasting day.",
            "Main meal: pair the main carbohydrate with protein or fiber, then note the next not-fasting reading.",
            "Evening: keep snacks simple and write one note if sleep, stress, or schedule changed.",
        ],
        "weekly_recommendations": weekly[:5],
        "signals": {
            "risk_level": risk_level,
            "risk_model_version": risk.get("model_version"),
            "trend_label": trend,
            "trend_model_version": monitoring.get("model_version"),
            "latest_glucose": logs["latest_glucose"],
            "latest_is_fasting": logs["latest_is_fasting"],
            "avg_fasting": logs["avg_fasting"],
            "avg_post_meal": logs["avg_post_meal"],
            "bayesian_posterior": context["bayesian"].get("posterior_mean"),
            "top_recommendation_type": top_action.get("type"),
        },
    }


def _gemini_plan(context: dict, fallback: dict) -> dict | None:
    provider = os.getenv("GLYCO_LLM_PROVIDER", "").lower()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GLYCO_GEMINI_API_KEY", "")
    if provider not in {"gemini", "google"} or not api_key:
        return None
    model = os.getenv("GLYCO_GEMINI_MODEL", "gemini-2.5-flash")
    base_url = os.getenv("GLYCO_GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta")
    prompt = f"""Create a personalized diabetes-support care plan from real Glyco data.

Return ONLY valid JSON with these keys:
direction: string
prefer: array of 3-5 strings
limit: array of 3-5 strings
sample_day: array of 3 strings
weekly_recommendations: array of 3-5 strings

Rules:
- Use the same language as the patient-facing app context if obvious; otherwise English.
- Use the latest reading, fasting/not-fasting label, risk, trend, Bayesian posterior, and Thompson-ranked recommendation.
- Do not diagnose, prescribe, or change medication.
- Be specific to this patient's current data. Avoid generic wellness filler.

Context JSON:
{json.dumps(context, default=str)}

Safe fallback plan to improve, not ignore:
{json.dumps(fallback, default=str)}"""
    try:
        response = httpx.post(
            f"{base_url}/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.25, "topP": 0.85, "maxOutputTokens": 1200},
            },
            timeout=float(os.getenv("GLYCO_GEMINI_TIMEOUT_SECONDS", "45")),
        )
        response.raise_for_status()
        parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        plan = json.loads(text)
        if not all(isinstance(plan.get(key), list) for key in ("prefer", "limit", "sample_day", "weekly_recommendations")):
            return None
        return {**fallback, **plan, "source": "gemini-personalized"}
    except Exception as exc:
        logger.warning("Gemini care plan failed: %s", exc)
        return None


def build_care_plan(db: Session, user_id: int) -> dict:
    context = _plan_context(db, user_id)
    fallback = _fallback_plan(context)
    return _gemini_plan(context, fallback) or fallback
