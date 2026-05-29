from __future__ import annotations

from statistics import mean


def _latest_log_delta(logs) -> str:
    if len(logs) < 2:
        return "There is not enough monitoring history yet to compare recent changes."
    previous = logs[-2].fasting_glucose
    latest = logs[-1].fasting_glucose
    delta = round(latest - previous, 1)
    direction = "increased" if delta > 0 else "decreased" if delta < 0 else "stayed level"
    return f"Fasting glucose {direction} by {abs(delta)} mg/dL since the previous log."


def _recent_average(logs) -> float | None:
    recent = [log.fasting_glucose for log in logs[-7:] if log.fasting_glucose is not None]
    return round(mean(recent), 1) if recent else None


def build_glyco_insight(user, risk, monitoring, logs) -> dict:
    sorted_logs = sorted(logs, key=lambda log: (getattr(log, "created_at", None) or log.log_date, log.log_date))
    avg = _recent_average(sorted_logs)
    risk_level = risk.risk_level if risk else "unknown"
    trend = monitoring.trend_label if monitoring else "unknown"
    top_factor = risk.top_factors_json[0]["label"] if risk and risk.top_factors_json else "profile pattern"
    anomaly = monitoring.anomaly_flags_json[0]["label"] if monitoring and monitoring.anomaly_flags_json else None

    what_changed = _latest_log_delta(sorted_logs)
    if avg is not None:
        what_changed += f" The recent 7-log average is {avg} mg/dL."

    why_parts = [
        f"The current risk state is {risk_level}.",
        f"The monitoring model currently classifies the trend as {trend}.",
        f"The strongest visible contributor is {top_factor}.",
    ]
    if anomaly:
        why_parts.append(f"Glyco also flagged {anomaly.lower()}.")

    if trend == "concerning" or risk_level == "high":
        next_steps = [
            "Log another fasting glucose reading tomorrow morning.",
            "Review recent meals and activity alongside the latest glucose rise.",
            "Generate a doctor summary if elevated readings continue.",
        ]
        doctor_questions = [
            "Should my recent fasting glucose pattern change my monitoring schedule?",
            "Do my blood pressure, BMI, and cholesterol flags change my risk management plan?",
            "What threshold should prompt me to contact the clinic?",
        ]
    elif trend == "watch" or risk_level == "medium":
        next_steps = [
            "Keep logging fasting glucose for the next 3 mornings.",
            "Add a short post-meal walk after the largest meal.",
            "Review the care plan and update missing profile details.",
        ]
        doctor_questions = [
            "Are these readings enough to adjust my prevention plan?",
            "Should I track post-meal glucose more often?",
            "Which lifestyle change would matter most this month?",
        ]
    else:
        next_steps = [
            "Continue the current logging routine.",
            "Keep activity and meal timing consistent.",
            "Recheck the profile if weight, blood pressure, or activity changes.",
        ]
        doctor_questions = [
            "How often should I repeat a risk screening?",
            "Are there prevention targets I should track at home?",
            "Which readings are most useful to bring to appointments?",
        ]

    return {
        "title": "Glyco Insight",
        "patient_name": user.full_name if user else "Demo patient",
        "what_changed": what_changed,
        "why_it_matters": " ".join(why_parts),
        "what_to_do_next": next_steps,
        "what_to_ask_your_doctor": doctor_questions,
        "confidence_note": (
            "This insight combines the trained risk model, monitoring trend model, and deterministic safety rules. "
            "It is decision support, not a diagnosis."
        ),
    }
