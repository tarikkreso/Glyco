def build_report(report_type: str, user, risk, monitoring, logs) -> dict:
    latest_log = logs[-1] if logs else None
    name = user.full_name
    risk_text = (
        f"{risk.risk_level} risk at {int(risk.risk_probability * 100)}% using {risk.model_version}"
        if risk
        else "No recent risk assessment"
    )
    monitor_text = f"{monitoring.trend_label} using {monitoring.model_version}" if monitoring else "No monitoring assessment"
    sections = [
        {"title": "Patient", "body": f"{name} is using Glyco for diabetes risk screening and monitoring support."},
        {"title": "Current Risk", "body": risk_text},
        {"title": "Monitoring State", "body": f"Recent trend status: {monitor_text}."},
    ]
    if latest_log:
        sections.append({"title": "Latest Log", "body": f"Latest fasting glucose was {latest_log.fasting_glucose} mg/dL on {latest_log.log_date}."})
    if risk:
        sections.append({"title": "Risk Interpretation", "body": risk.explanation})
    if monitoring and monitoring.summary_json.get("message"):
        sections.append({"title": "Monitoring Interpretation", "body": monitoring.summary_json["message"]})
    if report_type == "family":
        sections.append({"title": "How Family Can Help", "body": "Encourage regular logging, walks after meals, medication routines, and follow-up appointments."})
    elif report_type == "doctor":
        sections.append({"title": "Clinical Discussion Points", "body": "Review the risk model output, fasting glucose pattern, blood pressure, BMI category, and cholesterol history."})
    else:
        sections.append({"title": "Weekly Focus", "body": "Maintain consistent logging and pair meals with light activity where appropriate."})
    return {"title": f"{report_type.replace('_', ' ').title()} Report", "sections": sections, "disclaimer": "Glyco provides decision support and does not diagnose medical conditions."}
