from datetime import date
from sqlalchemy.orm import Session

from app.db import models
from app.ml.inference import build_risk_feature_row, predict_monitoring, predict_risk
from app.rules.engine import estimate_risk_probability, monitoring_state, profile_flags, risk_level
from app.services.bayesian import update_bayesian_state


def _risk_explanation(profile: models.Profile, probability: float, level: str, top_factors: list[dict], used_fallback: bool) -> str:
    factors = ", ".join(item["label"] for item in top_factors[:3]) or "profile indicators"
    source = "screening model" if not used_fallback else "deterministic fallback logic"
    return (
        f"Glyco estimates a {level} Type 2 diabetes risk pattern at {int(probability * 100)}% based on {factors}. "
        f"This result used the {source} and is screening support, not a diagnosis."
    )


def _monitoring_explanation(summary: dict, trend_label: str, used_fallback: bool) -> str:
    source = "trend model" if not used_fallback else "deterministic fallback logic"
    avg = summary.get("avg_glucose") or summary.get("avg_fasting_glucose")
    slope = summary.get("slope")
    details = []
    if avg is not None:
        details.append(f"average glucose {avg} mg/dL")
    if slope is not None:
        details.append(f"slope {slope}")
    joined = ", ".join(details) if details else "recent glucose patterns"
    return f"Recent monitoring state is {trend_label} based on {joined}. This result used the {source}."


def create_risk_assessment(db: Session, profile: models.Profile):
    model_result = predict_risk(profile)
    fallback_probability, fallback_factors = estimate_risk_probability(profile)
    probability = model_result["probability"] if model_result["ok"] else fallback_probability
    level = model_result["risk_level"] if model_result["ok"] else risk_level(fallback_probability)
    feature_row = model_result["feature_row"] if model_result["ok"] else build_risk_feature_row(profile)
    factors = []
    factor_details = {
        "BMI": ("BMI", f"BMI {profile.bmi} contributes to the screening profile."),
        "HighBP": ("High blood pressure", "High blood pressure is marked in the profile."),
        "HighChol": ("High cholesterol", "High cholesterol is marked in the profile."),
        "Smoker": ("Smoking", "Smoking is marked in the profile."),
        "PhysActivity": ("Physical activity", "Lower activity can increase diabetes risk."),
        "Age": ("Age", f"Age bucket {_age_bucket_display(profile.age)} is associated with higher risk."),
        "GenHlth": ("General health", f"General health score {profile.general_health}/5 raises baseline concern."),
        "HeartDiseaseorAttack": ("Heart disease history", "Heart disease history overlaps with cardio-metabolic risk."),
        "DiffWalk": ("Mobility difficulty", "Difficulty walking suggests reduced mobility risk."),
    }
    for name, value in sorted(feature_row.items(), key=lambda item: abs(float(item[1])), reverse=True):
        if name in factor_details and float(value) > 0:
            label, detail = factor_details[name]
            factors.append({"label": label, "impact": round(float(value), 2), "detail": detail})
    if not factors:
        factors = fallback_factors
    flags = profile_flags(profile)
    explanation = _risk_explanation(profile, probability, level, factors, not model_result["ok"])
    row = models.RiskAssessment(
        user_id=profile.user_id,
        profile_id=profile.id,
        risk_probability=probability,
        risk_level=level,
        top_factors_json=factors[:5],
        related_flags_json=flags,
        explanation=explanation,
        model_version=model_result["model_version"] if model_result["ok"] else "rules-fallback-0.1",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    update_bayesian_state(db, profile.user_id, probability)
    return {
        "id": row.id,
        "user_id": row.user_id,
        "profile_id": row.profile_id,
        "risk_probability": row.risk_probability,
        "risk_level": row.risk_level,
        "confidence_label": "directional",
        "top_factors": row.top_factors_json,
        "related_flags": row.related_flags_json,
        "explanation": row.explanation,
        "next_actions": ["Discuss results with a clinician", "Track fasting glucose weekly", "Review activity and nutrition plan"],
        "model_version": row.model_version,
    }


def _age_bucket_display(age: int) -> str:
    if age <= 24:
        return "18-24"
    if age >= 80:
        return "80+"
    start = age - ((age - 20) % 5)
    return f"{start}-{start + 4}"


def create_monitoring_assessment(db: Session, user_id: int):
    logs = db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id).order_by(models.HealthLog.log_date.asc()).all()
    model_result = predict_monitoring(logs)
    fallback_result = monitoring_state(logs)
    result = {
        "trend_label": model_result["trend_label"],
        "trend_score": model_result["trend_score"],
        "anomaly_flags": fallback_result["anomaly_flags"],
        "summary": {
            **fallback_result["summary"],
            "message": _monitoring_explanation(fallback_result["summary"], model_result["trend_label"], False),
            "model_score_map": model_result["score_map"],
        },
    } if model_result["ok"] else fallback_result
    if not model_result["ok"]:
        result["summary"]["message"] = _monitoring_explanation(result["summary"], result["trend_label"], True)
    row = models.MonitoringAssessment(
        user_id=user_id,
        assessment_date=date.today(),
        trend_label=result["trend_label"],
        trend_score=result["trend_score"],
        anomaly_flags_json=result["anomaly_flags"],
        summary_json=result["summary"],
        model_version=model_result["model_version"] if model_result["ok"] else "engineered-rules-0.1",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "user_id": row.user_id,
        "trend_label": row.trend_label,
        "trend_score": row.trend_score,
        "anomaly_flags": row.anomaly_flags_json,
        "summary": row.summary_json,
        "recommended_actions": ["Log the next glucose reading", "Review recent meals if readings are elevated", "Prepare a clinician summary if warnings persist"],
        "model_version": row.model_version,
    }
