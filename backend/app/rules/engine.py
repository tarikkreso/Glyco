from statistics import mean, pstdev


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    return round(weight_kg / ((height_cm / 100) ** 2), 1)


def bmi_category(bmi: float) -> str:
    if bmi >= 30:
        return "obesity"
    if bmi >= 25:
        return "overweight"
    if bmi >= 18.5:
        return "healthy"
    return "underweight"


def profile_flags(profile) -> list[dict]:
    flags = []
    category = bmi_category(profile.bmi)
    if category in {"overweight", "obesity"}:
        flags.append({"type": "bmi", "level": "warning", "label": "BMI risk", "detail": f"BMI {profile.bmi} is categorized as {category}."})
    if profile.high_bp:
        flags.append({"type": "bp", "level": "warning", "label": "Blood pressure risk", "detail": "High blood pressure is marked in the profile."})
    if profile.high_chol:
        flags.append({"type": "cholesterol", "level": "warning", "label": "Cholesterol risk", "detail": "High cholesterol is marked in the profile."})
    if profile.high_bp and (profile.high_chol or profile.heart_disease_history):
        flags.append({"type": "cardio", "level": "danger", "label": "Cardio-metabolic warning", "detail": "Blood pressure plus cholesterol or heart history increases related risk."})
    return flags


def risk_level(probability: float) -> str:
    if probability >= 0.65:
        return "high"
    if probability >= 0.30:
        return "medium"
    return "low"


def estimate_risk_probability(profile) -> tuple[float, list[dict]]:
    factors = []
    score = -2.2
    weights = [
        ("BMI", max(0, profile.bmi - 24) * 0.08, f"BMI {profile.bmi}"),
        ("High blood pressure", 0.75 if profile.high_bp else 0, "Marked high blood pressure"),
        ("High cholesterol", 0.55 if profile.high_chol else 0, "Marked high cholesterol"),
        ("Low physical activity", 0.42 if not profile.phys_activity else 0, "Limited physical activity"),
        ("Age", max(0, profile.age - 45) * 0.025, f"Age {profile.age}"),
        ("Family history", 0.45 if profile.family_history_diabetes else 0, "Family history of diabetes"),
        ("General health", max(0, profile.general_health - 2) * 0.25, f"General health score {profile.general_health}/5"),
        ("Smoking", 0.25 if profile.smoker else 0, "Smoking marked in profile"),
    ]
    for label, contribution, detail in weights:
        score += contribution
        if contribution > 0.12:
            factors.append({"label": label, "impact": round(contribution, 2), "detail": detail})
    probability = 1 / (1 + 2.71828 ** (-score))
    return round(min(max(probability, 0.03), 0.96), 2), sorted(factors, key=lambda item: item["impact"], reverse=True)[:5]


def monitoring_state(logs) -> dict:
    ordered = sorted(logs, key=lambda log: log.log_date)
    recent = ordered[-14:]
    glucose = [log.fasting_glucose for log in recent if log.fasting_glucose is not None]
    if not glucose:
        return {"trend_label": "watch", "trend_score": 0.5, "anomaly_flags": [], "summary": {"message": "More readings are needed."}}
    avg_glucose = round(mean(glucose), 1)
    variability = round(pstdev(glucose), 1) if len(glucose) > 1 else 0
    slope = round((glucose[-1] - glucose[0]) / max(len(glucose) - 1, 1), 1)
    high_count = sum(1 for value in glucose if value >= 130)
    flags = []
    if high_count >= 3:
        flags.append({"level": "warning", "label": "Repeated elevated fasting readings", "detail": f"{high_count} recent readings were at or above 130 mg/dL."})
    if slope >= 3:
        flags.append({"level": "danger", "label": "Rising glucose pattern", "detail": f"Recent fasting glucose is rising about {slope} mg/dL per log."})
    if variability >= 25:
        flags.append({"level": "warning", "label": "High glucose variability", "detail": f"Recent variability is {variability} mg/dL."})
    bp_values = [(log.systolic_bp, log.diastolic_bp) for log in recent if log.systolic_bp and log.diastolic_bp]
    if sum(1 for sys, dia in bp_values if sys >= 140 or dia >= 90) >= 2:
        flags.append({"level": "warning", "label": "Blood pressure pattern", "detail": "Multiple recent blood pressure logs are elevated."})
    score = min(1, max(0, (avg_glucose - 95) / 80 + high_count * 0.04 + max(slope, 0) * 0.04))
    label = "stable"
    if score >= 0.68 or any(flag["level"] == "danger" for flag in flags):
        label = "concerning"
    elif score >= 0.38 or flags:
        label = "watch"
    return {
        "trend_label": label,
        "trend_score": round(score, 2),
        "anomaly_flags": flags,
        "summary": {
            "avg_fasting_glucose": avg_glucose,
            "variability": variability,
            "slope": slope,
            "logs_analyzed": len(recent),
            "message": f"Recent monitoring state is {label}.",
        },
    }
