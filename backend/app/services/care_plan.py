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
            "Spinach and Mushroom Scrambled Eggs:\n- 2 large eggs\n- 60g fresh spinach\n- 50g sliced mushrooms\n- 10 ml olive oil\nScramble the eggs with spinach and mushrooms in olive oil. Serve with 1 slice (30g) of sprouted whole-grain toast and black coffee.",
            "Grilled Chicken Avocado Salad:\n- 115g chicken breast\n- 100g mixed romaine lettuce\n- 50g cherry tomatoes\n- 50g sliced cucumbers\n- 1/4 (40g) avocado\n- 15 ml olive oil and fresh lemon juice\nGrill the chicken, slice it, and toss with salad ingredients and dressing.",
            "Baked Lemon-Herb Salmon:\n- 140g salmon fillet seasoned with dill\n- 100g roasted broccoli florets\n- 75g fresh asparagus\n- 100 ml cooked wild rice or quinoa\nBake the salmon and serve with the steamed/roasted vegetables and wild rice.",
            "Plain Greek Yogurt & Almonds:\n- 120 ml plain, unsweetened Greek yogurt\n- 15g crushed raw almonds\n- 5g chia seeds\n- Sprinkle of cinnamon\nCombine ingredients in a bowl for a protein-rich snack."
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


from app.agent.llm_client import get_llm_client


def _personalized_plan(context: dict, fallback: dict) -> dict | None:
    llm_client = get_llm_client()
    prompt = f"""Create a personalized diabetes-support care plan from real Glyco data.

Return ONLY valid JSON with these keys:
direction: string
prefer: array of 3-5 strings
limit: array of 3-5 strings
sample_day: array of 4 strings
weekly_recommendations: array of 3-5 strings

Rules:
- Use the same language as the patient-facing app context if obvious; otherwise English.
- Use the latest reading, fasting/not-fasting label, risk, trend, Bayesian posterior, and Thompson-ranked recommendation.
- Do not diagnose, prescribe, or change medication.
- Be specific to this patient's current data. Avoid generic wellness filler.
- The "sample_day" array MUST contain exactly 4 strings, representing Breakfast, Lunch, Dinner, and Snack in that order.
- Each meal MUST be a highly realistic, professional, diabetic-appropriate meal/recipe.
- You MUST use metric units exclusively for ingredients and quantities (e.g. grams (g), milliliters (ml), liters (l) instead of ounces, pounds, cups, tablespoons, or teaspoons). Every single ingredient in the list MUST specify its metric quantity (e.g. "- 100g spinach", "- 15ml olive oil", "- 120ml yogurt"). DO NOT use imperial units or non-standard measurements.
- The format for each meal MUST be structured explicitly with: Meal Name, followed by a list of ingredients with each ingredient on a new line starting with a hyphen (e.g. '- 100g spinach', '- 15ml olive oil'), followed by a step-by-step preparation instruction.
- Ensure the ingredient list is rendered clearly in bullet points with newlines.

Context JSON:
{json.dumps(context, default=str)}

Safe fallback plan to improve, not ignore:
{json.dumps(fallback, default=str)}"""
    try:
        messages = [{"role": "user", "content": prompt}]
        text = llm_client.generate(messages, {})
        if not text:
            return None
        text = text.strip()
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1:
            text = text[start_idx : end_idx + 1]
        elif text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        plan = json.loads(text, strict=False)
        if not all(isinstance(plan.get(key), list) for key in ("prefer", "limit", "sample_day", "weekly_recommendations")):
            return None
        
        # Ensure sample_day has exactly 4 items, padding with fallback meals if necessary
        plan_sample = plan.get("sample_day") or []
        while len(plan_sample) < 4:
            plan_sample.append(fallback["sample_day"][len(plan_sample)])
        plan["sample_day"] = plan_sample[:4]

        provider_name = getattr(llm_client, "provider_name", "personalized")
        if provider_name == "deepseek":
            model_name = getattr(llm_client, "model_name", "")
            if "liquid" in str(model_name).lower():
                provider_name = "liquid"
        return {**fallback, **plan, "source": f"{provider_name}-personalized"}
    except Exception as exc:
        logger.warning("Personalized care plan generation failed: %s", exc)
        return None


def build_care_plan(db: Session, user_id: int) -> dict:
    context = _plan_context(db, user_id)
    fallback = _fallback_plan(context)
    return _personalized_plan(context, fallback) or fallback

