from statistics import mean


def _fmt(value, unit: str = "") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        value = round(value, 1)
    return f"{value}{unit}"


def build_report(report_type: str, user, risk, monitoring, logs) -> dict:
    latest_log = logs[-1] if logs else None
    name = user.full_name if user else "Demo patient"
    fasting_values = [log.glucose_level for log in logs if log.glucose_level is not None and getattr(log, "is_fasting", True)]
    post_meal_values = [log.glucose_level for log in logs if log.glucose_level is not None and not getattr(log, "is_fasting", True)]
    activity_values = [log.activity_minutes for log in logs if log.activity_minutes is not None]
    avg_fasting = round(mean(fasting_values), 1) if fasting_values else None
    avg_post_meal = round(mean(post_meal_values), 1) if post_meal_values else None
    avg_activity = round(mean(activity_values), 1) if activity_values else None
    fasting_min = min(fasting_values) if fasting_values else None
    fasting_max = max(fasting_values) if fasting_values else None
    delta = None
    if len(fasting_values) >= 2:
        delta = round(fasting_values[-1] - fasting_values[-2], 1)

    risk_text = (
        f"{risk.risk_level} risk at {int(risk.risk_probability * 100)}% using {risk.model_version}"
        if risk
        else "No recent risk assessment"
    )
    monitor_text = f"{monitoring.trend_label} using {monitoring.model_version}" if monitoring else "No monitoring assessment"

    if report_type == "doctor":
        sections = [
            {"title": "Patient Overview", "body": f"{name} is using Glyco for diabetes risk screening and monitoring support."},
            {"title": "Risk Profile", "body": risk_text},
            {"title": "Monitoring Trend", "body": f"Recent trend status: {monitor_text}."},
            {"title": "Glucose Summary", "body": f"Average fasting glucose: {_fmt(avg_fasting, ' mg/dL')}. Average not-fasting glucose: {_fmt(avg_post_meal, ' mg/dL')}. Fasting range: {_fmt(fasting_min, ' mg/dL')} to {_fmt(fasting_max, ' mg/dL')}."},
            {"title": "Recent Vitals", "body": f"Latest BP: {_fmt(getattr(latest_log, 'systolic_bp', None), ' /')} {_fmt(getattr(latest_log, 'diastolic_bp', None), ' mmHg')}. Avg activity: {_fmt(avg_activity, ' min/day')}."},
        ]
        if risk:
            sections.append({"title": "Risk Interpretation", "body": risk.explanation})
        if monitoring and monitoring.summary_json.get("message"):
            sections.append({"title": "Monitoring Interpretation", "body": monitoring.summary_json["message"]})
        sections.append({"title": "Clinical Discussion Points", "body": "Review risk drivers, medication adherence, BP control, and targets for glucose variability."})
        title = "Doctor Summary"
        disclaimer = "Clinical decision support only. Not a diagnosis."
    elif report_type == "family":
        sections = [
            {"title": "Overview", "body": f"{name} is tracking health patterns to reduce diabetes risk."},
            {"title": "How Things Look", "body": f"Risk is currently {risk.risk_level if risk else 'unknown'} and the monitoring trend is {monitoring.trend_label if monitoring else 'unknown'}."},
            {"title": "Recent Readings", "body": f"Average fasting glucose: {_fmt(avg_fasting, ' mg/dL')}. Average not-fasting glucose: {_fmt(avg_post_meal, ' mg/dL')}. Latest reading: {_fmt(getattr(latest_log, 'glucose_level', None), ' mg/dL')}."},
            {"title": "How Family Can Help", "body": "Offer reminders to log readings, plan balanced meals, and take short walks after meals."},
            {"title": "Next Check-In", "body": "If readings stay elevated for several days, consider contacting a clinician."},
        ]
        title = "Family Update"
        disclaimer = "Shared to keep family informed. Not a diagnosis."
    else:
        change_text = "No change yet." if delta is None else f"Fasting glucose changed by {abs(delta)} mg/dL since the last log."
        if delta is not None:
            change_text = f"Fasting glucose {'increased' if delta > 0 else 'decreased' if delta < 0 else 'stayed level'} by {abs(delta)} mg/dL since the last log."
        sections = [
            {"title": "Week At A Glance", "body": f"Average fasting glucose: {_fmt(avg_fasting, ' mg/dL')}. {change_text}"},
            {"title": "Activity", "body": f"Average activity: {_fmt(avg_activity, ' min/day')}."},
            {"title": "Focus For Next Week", "body": "Keep a consistent logging schedule and match higher-carb meals with light activity."},
        ]
        title = "Weekly Reflection"
        disclaimer = "Personal reflection summary. Not a diagnosis."

    return {"title": title, "sections": sections, "disclaimer": disclaimer}
