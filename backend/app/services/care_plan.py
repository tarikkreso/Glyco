from __future__ import annotations

import json
import logging
from datetime import date, datetime
from hashlib import sha256
from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from app.agent.bandit import RecommendationBandit, default_recommendations
from app.agent.guidelines import retrieve_guidelines
from app.db import models
from app.ml.forecast_inference import get_forecast_service
from app.services.bayesian import get_or_create_bayesian_state, serialize_bayesian_state
from app.services.assessments import create_monitoring_assessment, create_risk_assessment
from app.services.forecast_learning import apply_calibration

logger = logging.getLogger(__name__)

MEAL_LIBRARY: dict[str, dict[str, list[dict[str, Any]]]] = {
    "high_guard": {
        "breakfast": [
            {
                "name": "Greek Yogurt Berry Chia Bowl",
                "ingredients": ["180g plain Greek yogurt", "60g blueberries", "12g chia seeds", "15g walnuts", "2g cinnamon"],
                "steps": "Mix the yogurt with chia and cinnamon, then top with berries and walnuts.",
                "calories": 340,
                "carbs": 27,
            },
            {
                "name": "Vegetable Tofu Scramble",
                "ingredients": ["140g firm tofu", "80g zucchini", "70g bell pepper", "50g tomato", "8ml olive oil", "1g turmeric"],
                "steps": "Cook the vegetables in olive oil, crumble in tofu, season with turmeric, and heat until firm.",
                "calories": 360,
                "carbs": 22,
            },
            {
                "name": "Cottage Cheese Cucumber Plate",
                "ingredients": ["180g low-fat cottage cheese", "120g cucumber", "80g tomato", "35g rye crispbread", "8ml olive oil"],
                "steps": "Serve cottage cheese with sliced vegetables, rye crispbread, and olive oil over the vegetables.",
                "calories": 390,
                "carbs": 34,
            },
        ],
        "lunch": [
            {
                "name": "Turkey Lentil Salad",
                "ingredients": ["110g grilled turkey breast", "90g cooked lentils", "90g mixed greens", "70g cucumber", "60g tomato", "12ml olive oil", "10ml lemon juice"],
                "steps": "Slice turkey and combine with lentils, greens, vegetables, olive oil, and lemon juice.",
                "calories": 480,
                "carbs": 36,
            },
            {
                "name": "Chicken Broccoli Barley Bowl",
                "ingredients": ["120g chicken breast", "150g broccoli", "80g cooked barley", "50g carrots", "10ml olive oil", "5ml lemon juice"],
                "steps": "Grill chicken, steam vegetables, and serve over barley with olive oil and lemon.",
                "calories": 520,
                "carbs": 43,
            },
            {
                "name": "Tuna Bean Lettuce Bowl",
                "ingredients": ["110g tuna in water", "100g cooked white beans", "100g romaine lettuce", "60g cucumber", "40g red onion", "12ml olive oil"],
                "steps": "Drain tuna and toss with beans, lettuce, vegetables, and olive oil.",
                "calories": 500,
                "carbs": 38,
            },
        ],
        "dinner": [
            {
                "name": "Salmon Quinoa Greens",
                "ingredients": ["130g salmon fillet", "90g cooked quinoa", "140g green beans", "70g cauliflower", "8ml olive oil", "5ml lemon juice"],
                "steps": "Bake salmon, steam the vegetables, and serve with quinoa, olive oil, and lemon.",
                "calories": 560,
                "carbs": 42,
            },
            {
                "name": "Beef Vegetable Buckwheat Plate",
                "ingredients": ["105g lean beef strips", "100g cooked buckwheat", "120g cabbage", "80g zucchini", "8ml olive oil", "5ml vinegar"],
                "steps": "Sear beef, saute cabbage and zucchini, and serve with buckwheat and vinegar.",
                "calories": 540,
                "carbs": 45,
            },
            {
                "name": "Eggplant Chickpea Chicken Bake",
                "ingredients": ["110g chicken breast", "130g eggplant", "80g cooked chickpeas", "90g tomato sauce", "8ml olive oil", "2g oregano"],
                "steps": "Bake chicken with eggplant, chickpeas, tomato sauce, olive oil, and oregano until tender.",
                "calories": 530,
                "carbs": 40,
            },
        ],
        "snack": [
            {
                "name": "Apple Almond Yogurt Snack",
                "ingredients": ["100g apple", "100g plain Greek yogurt", "12g almonds"],
                "steps": "Slice the apple and serve with yogurt and almonds.",
                "calories": 210,
                "carbs": 24,
            },
            {
                "name": "Hummus Vegetable Plate",
                "ingredients": ["55g hummus", "100g carrots", "100g cucumber", "25g whole-grain rye crackers"],
                "steps": "Serve hummus with sliced vegetables and rye crackers.",
                "calories": 260,
                "carbs": 31,
            },
            {
                "name": "Kefir Seed Cup",
                "ingredients": ["180ml plain kefir", "10g pumpkin seeds", "60g raspberries"],
                "steps": "Pour kefir into a bowl and top with pumpkin seeds and raspberries.",
                "calories": 220,
                "carbs": 22,
            },
        ],
    },
    "low_guard": {
        "breakfast": [
            {
                "name": "Oat Yogurt Pear Bowl",
                "ingredients": ["45g rolled oats", "160ml low-fat milk", "100g pear", "100g plain Greek yogurt", "8g ground flaxseed"],
                "steps": "Cook oats with milk, then top with pear, yogurt, and flaxseed.",
                "calories": 460,
                "carbs": 62,
            },
            {
                "name": "Rye Egg Avocado Plate",
                "ingredients": ["70g rye bread", "1 large egg", "50g avocado", "80g tomato", "100g plain kefir"],
                "steps": "Boil or poach the egg and serve with rye bread, avocado, tomato, and kefir.",
                "calories": 500,
                "carbs": 52,
            },
            {
                "name": "Banana Peanut Kefir Oats",
                "ingredients": ["40g rolled oats", "180ml plain kefir", "90g banana", "12g peanut butter", "5g chia seeds"],
                "steps": "Soak oats in kefir and top with banana, peanut butter, and chia seeds.",
                "calories": 480,
                "carbs": 64,
            },
        ],
        "lunch": [
            {
                "name": "Chicken Sweet Potato Plate",
                "ingredients": ["115g chicken breast", "170g baked sweet potato", "100g green beans", "70g tomato", "8ml olive oil"],
                "steps": "Bake sweet potato, grill chicken, and serve with green beans, tomato, and olive oil.",
                "calories": 560,
                "carbs": 58,
            },
            {
                "name": "Bean Rice Turkey Bowl",
                "ingredients": ["100g turkey breast", "110g cooked brown rice", "100g cooked kidney beans", "80g lettuce", "50g tomato salsa"],
                "steps": "Layer rice, beans, turkey, lettuce, and salsa in a bowl.",
                "calories": 610,
                "carbs": 72,
            },
            {
                "name": "Sardine Potato Salad",
                "ingredients": ["95g sardines in water", "180g boiled potato", "80g green peas", "90g cucumber", "10ml olive oil", "5ml lemon juice"],
                "steps": "Combine sardines, potato, peas, cucumber, olive oil, and lemon juice.",
                "calories": 590,
                "carbs": 58,
            },
        ],
        "dinner": [
            {
                "name": "Turkey Pasta Vegetable Bowl",
                "ingredients": ["105g turkey mince", "130g cooked whole-grain pasta", "120g tomato sauce", "90g zucchini", "8ml olive oil"],
                "steps": "Cook turkey with zucchini and tomato sauce, then serve over whole-grain pasta.",
                "calories": 610,
                "carbs": 66,
            },
            {
                "name": "Cod Couscous Chickpea Plate",
                "ingredients": ["140g cod fillet", "120g cooked whole-wheat couscous", "70g cooked chickpeas", "120g roasted peppers", "8ml olive oil"],
                "steps": "Bake cod, warm couscous and chickpeas, and serve with roasted peppers and olive oil.",
                "calories": 600,
                "carbs": 69,
            },
            {
                "name": "Egg Rice Vegetable Bowl",
                "ingredients": ["2 large eggs", "140g cooked brown rice", "100g mixed vegetables", "60g edamame", "8ml sesame oil", "5ml low-sodium soy sauce"],
                "steps": "Scramble eggs, warm rice and vegetables, then finish with sesame oil and soy sauce.",
                "calories": 640,
                "carbs": 70,
            },
        ],
        "snack": [
            {
                "name": "Milk Banana Walnut Snack",
                "ingredients": ["180ml low-fat milk", "80g banana", "12g walnuts"],
                "steps": "Serve banana with milk and walnuts.",
                "calories": 260,
                "carbs": 33,
            },
            {
                "name": "Whole-Grain Toast Ricotta",
                "ingredients": ["45g whole-grain bread", "70g ricotta", "60g berries", "5g chia seeds"],
                "steps": "Spread ricotta on toast and serve with berries and chia seeds.",
                "calories": 300,
                "carbs": 34,
            },
            {
                "name": "Date Yogurt Seed Cup",
                "ingredients": ["130g plain Greek yogurt", "20g dates", "12g sunflower seeds", "40g strawberries"],
                "steps": "Chop dates and strawberries, then mix with yogurt and sunflower seeds.",
                "calories": 290,
                "carbs": 35,
            },
        ],
    },
    "balanced": {
        "breakfast": [
            {
                "name": "Egg Rye Vegetable Breakfast",
                "ingredients": ["2 large eggs", "60g rye bread", "90g tomato", "80g cucumber", "5ml olive oil"],
                "steps": "Cook eggs with olive oil and serve with rye bread, tomato, and cucumber.",
                "calories": 430,
                "carbs": 39,
            },
            {
                "name": "Kefir Oat Berry Bowl",
                "ingredients": ["45g rolled oats", "180ml plain kefir", "70g strawberries", "15g almonds", "5g chia seeds"],
                "steps": "Soak oats in kefir and top with strawberries, almonds, and chia seeds.",
                "calories": 420,
                "carbs": 50,
            },
            {
                "name": "Chicken Tomato Breakfast Wrap",
                "ingredients": ["60g whole-grain tortilla", "80g chicken breast", "60g tomato", "50g lettuce", "40g plain yogurt"],
                "steps": "Fill tortilla with chicken, tomato, lettuce, and yogurt, then roll tightly.",
                "calories": 450,
                "carbs": 45,
            },
        ],
        "lunch": [
            {
                "name": "Mediterranean Chicken Chickpea Bowl",
                "ingredients": ["115g chicken breast", "95g cooked chickpeas", "80g cucumber", "70g tomato", "50g lettuce", "10ml olive oil"],
                "steps": "Combine chicken, chickpeas, vegetables, and olive oil in a bowl.",
                "calories": 540,
                "carbs": 45,
            },
            {
                "name": "Trout Potato Green Salad",
                "ingredients": ["125g trout fillet", "150g boiled potato", "110g mixed greens", "60g tomato", "8ml olive oil", "5ml lemon juice"],
                "steps": "Bake trout and serve with potato and greens dressed with olive oil and lemon.",
                "calories": 560,
                "carbs": 48,
            },
            {
                "name": "Lean Beef Bean Soup",
                "ingredients": ["95g lean beef", "130g cooked beans", "120g mixed soup vegetables", "80g tomato puree", "10ml olive oil"],
                "steps": "Simmer beef, beans, vegetables, tomato puree, and olive oil until tender.",
                "calories": 570,
                "carbs": 50,
            },
        ],
        "dinner": [
            {
                "name": "Chicken Barley Vegetable Dinner",
                "ingredients": ["120g chicken breast", "110g cooked barley", "130g roasted vegetables", "80g yogurt cucumber sauce", "8ml olive oil"],
                "steps": "Grill chicken and serve with barley, roasted vegetables, and yogurt cucumber sauce.",
                "calories": 590,
                "carbs": 55,
            },
            {
                "name": "Mackerel Bean Greens Plate",
                "ingredients": ["115g mackerel fillet", "100g cooked beans", "130g leafy greens", "60g tomato", "5ml olive oil"],
                "steps": "Bake mackerel and serve with beans, greens, tomato, and olive oil.",
                "calories": 610,
                "carbs": 39,
            },
            {
                "name": "Turkey Quinoa Pepper Skillet",
                "ingredients": ["115g turkey breast", "110g cooked quinoa", "120g bell peppers", "70g onion", "8ml olive oil"],
                "steps": "Cook turkey with peppers and onion, then serve over quinoa.",
                "calories": 580,
                "carbs": 50,
            },
        ],
        "snack": [
            {
                "name": "Pear Cheese Seed Snack",
                "ingredients": ["120g pear", "40g reduced-fat cheese", "10g pumpkin seeds"],
                "steps": "Slice pear and serve with cheese and pumpkin seeds.",
                "calories": 260,
                "carbs": 28,
            },
            {
                "name": "Yogurt Berry Nut Snack",
                "ingredients": ["150g plain Greek yogurt", "70g berries", "12g walnuts"],
                "steps": "Top yogurt with berries and walnuts.",
                "calories": 250,
                "carbs": 22,
            },
            {
                "name": "Avocado Rye Crisp Snack",
                "ingredients": ["35g rye crispbread", "45g avocado", "60g tomato", "5ml lemon juice"],
                "steps": "Top rye crispbread with avocado, tomato, and lemon juice.",
                "calories": 240,
                "carbs": 29,
            },
        ],
    },
}


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 1) if values else None


def _as_mmol(value: float) -> float:
    return float(value) / 18.015 if float(value) > 40 else float(value)


def _mmol_to_mgdl(value: float | None) -> int | None:
    return int(round(float(value) * 18.015)) if value is not None else None


def _forecast_logs(db: Session, user_id: int, limit: int = 48) -> list[dict]:
    rows = (
        db.query(models.HealthLog)
        .filter(models.HealthLog.user_id == user_id)
        .order_by(models.HealthLog.created_at.desc(), models.HealthLog.log_date.desc())
        .limit(limit)
        .all()
    )
    ordered = list(reversed(rows))
    return [
        {
            "timestamp": row.created_at or row.log_date,
            "glucose_mmol": _as_mmol(row.glucose_level),
            "is_fasting": bool(row.is_fasting),
        }
        for row in ordered
        if row.glucose_level is not None
    ]


def _forecast_row_to_context(row: models.GlucoseForecast, source: str = "stored") -> dict:
    return {
        "source": source,
        "created_at": row.created_at,
        "current_glucose": row.current_glucose,
        "predictions": {
            "60": row.prediction_60min,
            "120": row.prediction_120min,
            "180": row.prediction_180min,
            "240": row.prediction_240min,
        },
        "trend_direction": row.trend_direction,
        "predicted_low_alert": row.predicted_low_alert,
        "predicted_high_alert": row.predicted_high_alert,
        "recommendation": row.recommendation,
        "model_version": row.model_version,
        "used_fallback": row.used_fallback,
    }


def _latest_or_live_forecast(db: Session, user_id: int, latest_log: models.HealthLog | None) -> dict | None:
    row = (
        db.query(models.GlucoseForecast)
        .filter(models.GlucoseForecast.user_id == user_id)
        .order_by(models.GlucoseForecast.created_at.desc())
        .first()
    )
    if row and (latest_log is None or row.created_at >= latest_log.created_at):
        return _forecast_row_to_context(row)

    logs = _forecast_logs(db, user_id)
    if not logs:
        return None
    try:
        result = apply_calibration(db, get_forecast_service().predict(user_id, logs))
        return {**result, "source": "live", "created_at": datetime.utcnow()}
    except Exception as exc:
        logger.warning("Care plan forecast context unavailable: %s", exc)
        return _forecast_row_to_context(row) if row else None


def _profile_value(profile: models.Profile | dict | None, key: str) -> Any:
    if profile is None:
        return None
    if isinstance(profile, dict):
        return profile.get(key)
    return getattr(profile, key, None)


def _calorie_target(profile: models.Profile | dict | None) -> dict:
    height_cm = _profile_value(profile, "height_cm")
    weight_kg = _profile_value(profile, "weight_kg")
    age = _profile_value(profile, "age")
    if not profile or not height_cm or not weight_kg or not age:
        return {"target": None, "maintenance": None, "strategy": "profile-unavailable"}

    sex = str(_profile_value(profile, "sex") or "").lower()
    sex_offset = -161 if sex.startswith("f") else 5
    bmr = 10 * float(weight_kg) + 6.25 * float(height_cm) - 5 * int(age) + sex_offset
    activity_factor = 1.45 if _profile_value(profile, "phys_activity") else 1.25
    maintenance = bmr * activity_factor
    bmi = float(_profile_value(profile, "bmi") or 0)
    min_target = 1200 if sex.startswith("f") else 1500

    if bmi >= 30:
        target = max(min_target, maintenance - 500)
        strategy = "moderate-deficit"
    elif bmi >= 25:
        target = max(min_target, maintenance - 300)
        strategy = "small-deficit"
    elif 0 < bmi < 18.5:
        target = maintenance + 250
        strategy = "gentle-surplus"
    else:
        target = maintenance
        strategy = "maintenance"

    return {
        "target": int(round(target / 50) * 50),
        "maintenance": int(round(maintenance / 50) * 50),
        "strategy": strategy,
    }


def _forecast_strategy(forecast: dict | None, logs: dict) -> dict:
    prediction_60 = None
    current = None
    if forecast:
        predictions = forecast.get("predictions") or {}
        prediction_60 = predictions.get("60")
        current = forecast.get("current_glucose")

    prediction_60_mg = _mmol_to_mgdl(prediction_60)
    current_mg = _mmol_to_mgdl(current)
    trend = forecast.get("trend_direction") if forecast else None
    high_alert = bool(forecast and forecast.get("predicted_high_alert"))
    low_alert = bool(forecast and forecast.get("predicted_low_alert"))
    latest = logs.get("latest_glucose")

    if low_alert or (prediction_60 is not None and float(prediction_60) <= 4.0) or trend == "falling":
        meal_strategy = "low_guard"
        label = "falling_or_low"
        note = "near-term forecast is falling or near the lower range, so meals include steady carbohydrates with protein/fat to reduce sharp drops"
    elif high_alert or (prediction_60 is not None and float(prediction_60) >= 10.0) or (trend == "rising" and (latest or 0) >= 140):
        meal_strategy = "high_guard"
        label = "rising_or_high"
        note = "near-term forecast is rising or high, so meals emphasize lower-glycemic carbohydrates, fiber, and lean protein"
    else:
        meal_strategy = "balanced"
        label = "stable_or_unclear"
        note = "near-term forecast is stable or unavailable, so meals keep carbohydrates consistent and paired with protein/fiber"

    return {
        "meal_strategy": meal_strategy,
        "label": label,
        "note": note,
        "prediction_60_mg_dl": prediction_60_mg,
        "current_mg_dl": current_mg,
        "trend_direction": trend,
    }


def _stable_index(seed: str, modulo: int) -> int:
    if modulo <= 0:
        return 0
    return int(sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % modulo


def _format_meal(meal: dict, slot_budget: int | None) -> str:
    budget_text = f" | slot target about {slot_budget} kcal" if slot_budget else ""
    ingredients = "\n".join(f"- {item}" for item in meal["ingredients"])
    return (
        f"{meal['name']} ({meal['calories']} kcal, ~{meal['carbs']}g carbs{budget_text})\n"
        f"{ingredients}\n"
        f"Preparation: {meal['steps']}"
    )


def _sample_day(context: dict, calorie_info: dict, forecast_strategy: dict) -> tuple[list[str], int]:
    target = calorie_info.get("target") or 1800
    budgets = {
        "breakfast": int(round(target * 0.25 / 10) * 10),
        "lunch": int(round(target * 0.30 / 10) * 10),
        "dinner": int(round(target * 0.30 / 10) * 10),
        "snack": int(round(target * 0.15 / 10) * 10),
    }
    seed = "|".join(
        [
            str(context["user"]["id"]),
            date.today().isoformat(),
            str(context["logs"].get("latest_glucose")),
            str(context["logs"].get("count")),
            str(context.get("prior_plan_count", 0)),
            str(forecast_strategy.get("label")),
        ]
    )
    strategy = forecast_strategy["meal_strategy"]
    sample: list[str] = []
    total = 0
    for slot in ("breakfast", "lunch", "dinner", "snack"):
        options = sorted(
            MEAL_LIBRARY[strategy][slot],
            key=lambda item: abs(int(item["calories"]) - budgets[slot]),
        )
        candidates = options[: min(3, len(options))]
        choice = candidates[_stable_index(f"{seed}|{slot}", len(candidates))]
        sample.append(_format_meal(choice, budgets[slot]))
        total += int(choice["calories"])
    return sample, total


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
    logs = db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id).order_by(models.HealthLog.created_at.asc(), models.HealthLog.log_date.asc()).all()
    recent = logs[-14:]
    fasting_values = [log.glucose_level for log in recent if log.glucose_level is not None and log.is_fasting]
    post_values = [log.glucose_level for log in recent if log.glucose_level is not None and not log.is_fasting]
    latest = recent[-1] if recent else None
    forecast = _latest_or_live_forecast(db, user_id, latest)
    recommendations = RecommendationBandit(db, user_id).rerank(default_recommendations(), limit=4, forecast=forecast)
    prior_plan_count = (
        db.query(models.Report)
        .filter(models.Report.user_id == user_id, models.Report.report_type == "diet_care_plan")
        .count()
    )
    return {
        "user": {"id": user_id, "name": user.full_name if user else "Demo patient"},
        "profile": {
            "age": profile.age if profile else None,
            "sex": profile.sex if profile else None,
            "height_cm": profile.height_cm if profile else None,
            "weight_kg": profile.weight_kg if profile else None,
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
        "forecast": forecast,
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
        "prior_plan_count": prior_plan_count,
    }


def _fallback_plan(context: dict) -> dict:
    risk = context["risk"]
    monitoring = context["monitoring"]
    logs = context["logs"]
    profile = context["profile"]
    forecast = context.get("forecast")
    top_action = context["recommendations"][0] if context["recommendations"] else {}
    latest_type = "fasting" if logs["latest_is_fasting"] else "not-fasting"
    latest_text = f"latest {latest_type} reading {logs['latest_glucose']} mg/dL" if logs["latest_glucose"] is not None else "no recent reading"
    trend = monitoring.get("trend_label", "unknown")
    risk_level = risk.get("risk_level", "unknown")
    calorie_info = _calorie_target(profile)
    forecast_strategy = _forecast_strategy(forecast, logs)
    sample_day, sample_day_calories = _sample_day(context, calorie_info, forecast_strategy)
    target_text = (
        f"an estimated {calorie_info['target']} kcal/day target"
        if calorie_info.get("target")
        else "no calorie target because height/weight/age are incomplete"
    )
    forecast_text = (
        f"60-minute forecast {forecast_strategy['prediction_60_mg_dl']} mg/dL and {forecast_strategy['trend_direction']} direction"
        if forecast_strategy.get("prediction_60_mg_dl") is not None
        else "no available 60-minute forecast"
    )

    prefer = [
        f"Meals matched to {forecast_text}: {forecast_strategy['note']}.",
        f"A daily menu near {target_text}; this sample day is about {sample_day_calories} kcal.",
        "Protein, fiber, and measured carbohydrate portions at each meal instead of untracked refined carbohydrates.",
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
        "direction": (
            f"Personalized glucose support based on {latest_text}, {trend} monitoring trend, {risk_level} risk, "
            f"{forecast_text}, BMI {profile.get('bmi') if profile.get('bmi') is not None else 'unknown'}, and {target_text}."
        ),
        "prefer": prefer,
        "limit": limit,
        "sample_day": sample_day,
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
            "profile_height_cm": profile.get("height_cm"),
            "profile_weight_kg": profile.get("weight_kg"),
            "profile_bmi": profile.get("bmi"),
            "daily_calorie_target": calorie_info.get("target"),
            "calorie_strategy": calorie_info.get("strategy"),
            "sample_day_calories": sample_day_calories,
            "forecast_source": forecast.get("source") if forecast else None,
            "forecast_model_version": forecast.get("model_version") if forecast else None,
            "forecast_trend_direction": forecast_strategy.get("trend_direction"),
            "forecast_60_mg_dl": forecast_strategy.get("prediction_60_mg_dl"),
            "forecast_current_mg_dl": forecast_strategy.get("current_mg_dl"),
            "forecast_meal_strategy": forecast_strategy.get("label"),
            "predicted_low_alert": forecast.get("predicted_low_alert") if forecast else None,
            "predicted_high_alert": forecast.get("predicted_high_alert") if forecast else None,
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
- Use forecast.current_glucose and forecast.predictions["60"] when present: if the 60-minute forecast is high/rising, choose lower-glycemic higher-fiber meals; if it is falling/low, include measured steady carbohydrates with protein/fat.
- Use profile height, weight, age, sex, and BMI when present so the day fits the daily calorie target already reflected in the safe fallback.
- Do not diagnose, prescribe, or change medication.
- Be specific to this patient's current data. Avoid generic wellness filler.
- Do not repeat the same breakfast every time; preserve meal variety from the safe fallback unless you can improve it with equally specific metric meals.
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
        
        # Ensure sample_day has exactly 4 items, padding with fallback meals if necessary.
        # Replace the old static mushroom/spinach pattern if a provider repeats it.
        plan_sample = plan.get("sample_day") or []
        if any("spinach and mushroom scrambled eggs" in str(item).lower() for item in plan_sample):
            plan_sample = fallback["sample_day"]
        while len(plan_sample) < 4:
            plan_sample.append(fallback["sample_day"][len(plan_sample)])
        plan["sample_day"] = plan_sample[:4]

        provider_name = getattr(llm_client, "provider_name", "personalized")
        if provider_name == "deepseek":
            model_name = getattr(llm_client, "model_name", "")
            if "liquid" in str(model_name).lower():
                provider_name = "liquid"
        merged = {**fallback, **plan, "source": f"{provider_name}-personalized"}
        # Never allow the LLM output to clobber the required signals payload.
        merged["signals"] = fallback.get("signals", {})
        return merged
    except Exception as exc:
        logger.warning("Personalized care plan generation failed: %s", exc)
        return None


def build_care_plan(db: Session, user_id: int) -> dict:
    context = _plan_context(db, user_id)
    fallback = _fallback_plan(context)
    return _personalized_plan(context, fallback) or fallback

