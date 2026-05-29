from secrets import token_urlsafe
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_db
from app.db import models
from app.agent.bandit import RecommendationBandit
from app.agent.agent_service import build_agent_insight, chat_with_agent, proactive_check, record_agent_feedback
from app.agent.llm_client import get_llm_status
from app.agent.proactive import detect_sustained_glucose_anomaly_and_report
from app.ml.forecast_inference import get_forecast_service
from app.schemas.schemas import AgentAlertOut, AgentChatIn, AgentChatOut, AgentFeedbackIn, AgentFeedbackOut, FamilyShareIn, GlucoseForecastOut, HealthLogIn, HealthLogOut, ProfileIn, ProfileOut, ReportOut, UserOut, UserRegisterIn, UserUpdateIn
from app.rules.engine import calculate_bmi
from app.services.bayesian import get_or_create_bayesian_state, serialize_bayesian_state
from app.services.assessments import create_monitoring_assessment, create_risk_assessment
from app.services.care_plan import build_care_plan
from app.services.forecast_learning import apply_calibration, calibration_snapshot, evaluate_forecasts_for_log, forecast_accuracy_summary, forecast_personalization_enabled
from app.services.pdf_service import generate_pdf_report
from app.reports.generator import build_report

router = APIRouter()


def _refresh_log_followups(user_id: int, log_id: int | None = None) -> None:
    """Refresh model-derived follow-ups after a glucose log is created."""
    db = SessionLocal()
    try:
        if log_id is not None:
            log = db.get(models.HealthLog, log_id)
            if log is not None:
                evaluate_forecasts_for_log(db, log)
        create_monitoring_assessment(db, user_id)
        proactive_check(db, user_id)
        detect_sustained_glucose_anomaly_and_report(db, user_id)
        trigger_forecast_if_ready(user_id, db)
    finally:
        db.close()


def _as_mmol(value: float) -> float:
    """Convert legacy mg/dL glucose values to mmol/L for forecast inputs."""
    return float(value) / 18.015 if float(value) > 40 else float(value)


def _logs_for_forecast(db: Session, user_id: int, limit: int = 48) -> list[dict]:
    """Load recent health logs and convert them to forecast service log dictionaries."""
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


def _forecast_to_response(row: models.GlucoseForecast, db: Session | None = None) -> dict:
    """Serialize a stored forecast ORM row into the public forecast response shape."""
    response = {
        "user_id": row.user_id,
        "current_glucose": row.current_glucose,
        "predictions": {
            "60": row.prediction_60min,
            "120": row.prediction_120min,
            "180": row.prediction_180min,
            "240": row.prediction_240min,
        },
        "confidence_intervals": {
            "60": {"low": row.ci_60_low, "high": row.ci_60_high},
            "120": {"low": row.ci_120_low, "high": row.ci_120_high},
            "180": {"low": row.ci_180_low, "high": row.ci_180_high},
            "240": {"low": row.ci_240_low, "high": row.ci_240_high},
        },
        "trend_direction": row.trend_direction,
        "predicted_low_alert": row.predicted_low_alert,
        "predicted_high_alert": row.predicted_high_alert,
        "recommendation": row.recommendation,
        "model_version": row.model_version,
        "used_fallback": row.used_fallback,
        "horizon_minutes": [60, 120, 180, 240],
        "created_at": row.created_at,
        "calibration_applied": False,
        "personalization_enabled": True,
        "personal_mae_per_horizon": None,
        "forecast_quality": "needs_more_data",
    }
    if db is not None:
        personalization_enabled = forecast_personalization_enabled(db, row.user_id)
        response["personalization_enabled"] = personalization_enabled
        if not personalization_enabled:
            response["forecast_quality"] = "personalization_off"
            return response
        snapshot = calibration_snapshot(db, row.user_id, row.model_version)
        personal_mae = {horizon: float(item["mae"]) for horizon, item in snapshot.items()}
        response["personal_mae_per_horizon"] = personal_mae or None
        # Stored rows already contain the prediction values that were saved at creation time.
        response["calibration_applied"] = any(int(item["count"]) >= 5 for item in snapshot.values())
        response["forecast_quality"] = "calibrated" if response["calibration_applied"] else "learning" if personal_mae else "needs_more_data"
    return response


def _forecast_result_response(result: dict, row: models.GlucoseForecast) -> dict:
    """Attach database metadata to a freshly generated forecast response."""
    return {**result, "created_at": row.created_at}


def _save_forecast_result(db: Session, result: dict) -> models.GlucoseForecast:
    """Persist a forecast result dictionary to the glucose_forecasts table."""
    predictions = result["predictions"]
    intervals = result["confidence_intervals"]
    row = models.GlucoseForecast(
        user_id=result["user_id"],
        current_glucose=result["current_glucose"],
        prediction_60min=predictions["60"],
        prediction_120min=predictions["120"],
        prediction_180min=predictions["180"],
        prediction_240min=predictions["240"],
        ci_60_low=intervals["60"]["low"],
        ci_60_high=intervals["60"]["high"],
        ci_120_low=intervals["120"]["low"],
        ci_120_high=intervals["120"]["high"],
        ci_180_low=intervals["180"]["low"],
        ci_180_high=intervals["180"]["high"],
        ci_240_low=intervals["240"]["low"],
        ci_240_high=intervals["240"]["high"],
        trend_direction=result["trend_direction"],
        predicted_low_alert=result["predicted_low_alert"],
        predicted_high_alert=result["predicted_high_alert"],
        recommendation=result["recommendation"],
        model_version=result["model_version"],
        used_fallback=result["used_fallback"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _create_forecast_alert_if_needed(db: Session, result: dict) -> None:
    """Create an agent alert when the forecast predicts low or high glucose."""
    if not (result["predicted_low_alert"] or result["predicted_high_alert"]):
        return
    severity = "high" if result["predicted_low_alert"] else "medium"
    title = "Forecast glucose alert"
    existing = (
        db.query(models.AgentAlert)
        .filter(
            models.AgentAlert.user_id == result["user_id"],
            models.AgentAlert.title == title,
            models.AgentAlert.severity == severity,
            models.AgentAlert.acknowledged_at.is_(None),
        )
        .order_by(models.AgentAlert.created_at.desc())
        .first()
    )
    if existing:
        return
    db.add(
        models.AgentAlert(
            user_id=result["user_id"],
            severity=severity,
            title=title,
            message=result["recommendation"],
            recommended_action=result["recommendation"],
            source_json={"alert_type": "forecast_alert", "forecast": result},
        )
    )
    db.commit()


def trigger_forecast_if_ready(user_id: int, db: Session) -> dict:
    """
    Called in the background after each new log entry.
    Only runs the forecast if the user has at least 4 glucose logs.
    This ensures the forecast chart updates automatically after logging.
    """
    logs = _logs_for_forecast(db, user_id)
    if len(logs) < 4:
        return {"created": False, "reason": "insufficient_logs"}
    result = apply_calibration(db, get_forecast_service().predict(user_id, logs))
    row = _save_forecast_result(db, result)
    _create_forecast_alert_if_needed(db, result)
    return {"created": True, "forecast_id": row.id}


@router.post("/users/demo", response_model=UserOut)
def demo_user(db: Session = Depends(get_db)):
    """Return the primary seeded demo user."""
    return db.query(models.User).filter(models.User.email_or_demo_id == "demo-monitoring").first()


@router.post("/users/register", response_model=UserOut)
def register_user(payload: UserRegisterIn, db: Session = Depends(get_db)) -> models.User:
    """Create or return an app user for the lightweight registration flow."""
    email = payload.email.strip().lower()
    user = db.query(models.User).filter(models.User.email_or_demo_id == email).first()
    if user:
        return user
    row = models.User(full_name=payload.full_name.strip() or "Glyco User", email_or_demo_id=email)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdateIn, db: Session = Depends(get_db)) -> models.User:
    """Update the signed-in user's display name and email identifier."""
    row = db.get(models.User, user_id)
    if not row:
        raise HTTPException(404, "User not found")
    email = payload.email.strip().lower()
    existing = db.query(models.User).filter(models.User.email_or_demo_id == email, models.User.id != user_id).first()
    if existing:
        raise HTTPException(409, "Email is already used by another account")
    row.full_name = payload.full_name.strip() or "Glyco User"
    row.email_or_demo_id = email
    db.commit()
    db.refresh(row)
    return row


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Return a user by identifier."""
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.post("/profiles", response_model=ProfileOut)
def create_profile(payload: ProfileIn, db: Session = Depends(get_db)):
    """Create a profile and compute BMI for risk assessment."""
    bmi = calculate_bmi(payload.weight_kg, payload.height_cm)
    row = models.Profile(**payload.model_dump(), bmi=bmi)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/profiles/{user_id}", response_model=ProfileOut)
def get_profile(user_id: int, db: Session = Depends(get_db)):
    """Return the latest profile for a user."""
    row = db.query(models.Profile).filter(models.Profile.user_id == user_id).order_by(models.Profile.created_at.desc()).first()
    if not row:
        raise HTTPException(404, "Profile not found")
    return row


@router.put("/profiles/{profile_id}", response_model=ProfileOut)
def update_profile(profile_id: int, payload: ProfileIn, db: Session = Depends(get_db)):
    """Update a profile and refresh BMI."""
    row = db.get(models.Profile, profile_id)
    if not row:
        raise HTTPException(404, "Profile not found")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.bmi = calculate_bmi(payload.weight_kg, payload.height_cm)
    db.commit()
    db.refresh(row)
    return row


@router.post("/risk-assessment")
def risk_assessment(payload: ProfileIn, db: Session = Depends(get_db)):
    """Create a profile and a corresponding risk assessment."""
    profile = create_profile(payload, db)
    return create_risk_assessment(db, profile)


@router.get("/risk-assessment/{user_id}/latest")
def latest_risk(user_id: int, db: Session = Depends(get_db)):
    """Return or refresh the latest Random Forest risk assessment."""
    row = db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user_id).order_by(models.RiskAssessment.created_at.desc()).first()
    profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).order_by(models.Profile.created_at.desc()).first()
    if row and profile and (row.model_version != "random-forest-0.2" or profile.updated_at > row.created_at):
        return create_risk_assessment(db, profile)
    if not row:
        if not profile:
            raise HTTPException(404, "Risk assessment not found")
        return create_risk_assessment(db, profile)
    return {"id": row.id, "user_id": row.user_id, "profile_id": row.profile_id, "risk_probability": row.risk_probability, "risk_level": row.risk_level, "confidence_label": "directional", "top_factors": row.top_factors_json, "related_flags": row.related_flags_json, "explanation": row.explanation, "next_actions": ["Review profile", "Log fasting glucose"], "model_version": row.model_version}


@router.get("/risk/bayesian/{user_id}")
def bayesian_risk(user_id: int, db: Session = Depends(get_db)):
    """Return the user's Bayesian posterior risk state."""
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    return serialize_bayesian_state(get_or_create_bayesian_state(db, user_id))


@router.post("/logs", response_model=HealthLogOut)
def create_log(payload: HealthLogIn, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Create a glucose log and update monitoring and alerts."""
    reading_time = payload.reading_time or datetime.utcnow()
    if reading_time.tzinfo is not None:
        # SQLite stores naive datetimes; keep an absolute UTC instant for matching forecasts.
        reading_time = reading_time.astimezone(timezone.utc).replace(tzinfo=None)
    row = models.HealthLog(
        user_id=payload.user_id,
        log_date=reading_time.date(),
        is_fasting=payload.is_fasting,
        fasting_glucose=payload.glucose_level,
        post_meal_glucose=None if payload.is_fasting else payload.glucose_level,
        # created_at intentionally stores the actual reading time for manual back-entry.
        created_at=reading_time,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    background_tasks.add_task(_refresh_log_followups, payload.user_id, row.id)
    return row


@router.get("/logs/{user_id}", response_model=list[HealthLogOut])
def get_logs(user_id: int, db: Session = Depends(get_db)):
    """Return all logs for a user in chronological order."""
    return db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id).order_by(models.HealthLog.created_at.asc(), models.HealthLog.log_date.asc()).all()


@router.post("/monitoring-assessment")
def monitoring_assessment(user_id: int = 1, db: Session = Depends(get_db)):
    """Create a monitoring assessment for a user."""
    return create_monitoring_assessment(db, user_id)


@router.get("/monitoring-assessment/{user_id}/latest")
def latest_monitoring(user_id: int, db: Session = Depends(get_db)):
    """Return or refresh the latest monitoring assessment."""
    row = db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user_id).order_by(models.MonitoringAssessment.created_at.desc()).first()
    latest_log = db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id).order_by(models.HealthLog.created_at.desc(), models.HealthLog.log_date.desc()).first()
    if row and (row.model_version != "glucose-trend-random-forest-0.2" or (latest_log and latest_log.created_at > row.created_at)):
        return create_monitoring_assessment(db, user_id)
    if not row:
        return create_monitoring_assessment(db, user_id)
    return {"id": row.id, "user_id": row.user_id, "trend_label": row.trend_label, "trend_score": row.trend_score, "anomaly_flags": row.anomaly_flags_json, "summary": row.summary_json, "recommended_actions": ["Keep logging consistently"], "model_version": row.model_version}


@router.post("/forecast/{user_id}", response_model=GlucoseForecastOut)
def trigger_forecast(user_id: int, db: Session = Depends(get_db)):
    """
    Trigger a glucose forecast for a user.
    Loads recent logs, runs GlucoseForecastService.predict(),
    saves the result to glucose_forecasts, and returns the full result.
    Also creates an agent_alerts row if predicted_low_alert or 
    predicted_high_alert is True.
    """
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    logs = _logs_for_forecast(db, user_id)
    result = apply_calibration(db, get_forecast_service().predict(user_id, logs))
    row = _save_forecast_result(db, result)
    _create_forecast_alert_if_needed(db, result)
    return _forecast_result_response(result, row)


@router.get("/forecast/{user_id}/latest", response_model=GlucoseForecastOut)
def latest_forecast(user_id: int, db: Session = Depends(get_db)):
    """
    Return the most recent forecast for a user.
    Returns 404 if no forecast exists yet.
    """
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    row = (
        db.query(models.GlucoseForecast)
        .filter(models.GlucoseForecast.user_id == user_id)
        .order_by(models.GlucoseForecast.created_at.desc())
        .first()
    )
    if not row:
        # The Monitoring page can ask for latest before the background forecast has run.
        created = trigger_forecast_if_ready(user_id, db)
        if not created.get("created"):
            raise HTTPException(404, "Forecast not found")
        row = db.get(models.GlucoseForecast, created["forecast_id"])
        if not row:
            raise HTTPException(404, "Forecast not found")
    return _forecast_to_response(row, db)


@router.get("/forecast/{user_id}/history", response_model=list[GlucoseForecastOut])
def forecast_history(user_id: int, db: Session = Depends(get_db)):
    """
    Return the last 10 forecast records for a user, ordered newest first.
    Used by the frontend to show forecast trend over time.
    """
    rows = (
        db.query(models.GlucoseForecast)
        .filter(models.GlucoseForecast.user_id == user_id)
        .order_by(models.GlucoseForecast.created_at.desc())
        .limit(10)
        .all()
    )
    return [_forecast_to_response(row, db) for row in rows]


@router.get("/forecast/{user_id}/accuracy")
def forecast_accuracy(user_id: int, db: Session = Depends(get_db)):
    """Return forecast accuracy and calibration evidence for a user."""
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    return forecast_accuracy_summary(db, user_id)


@router.post("/reports/{report_type}", response_model=ReportOut)
def create_report(report_type: str, user_id: int = 1, db: Session = Depends(get_db)):
    """Create and persist a JSON report."""
    if report_type not in {"doctor", "family", "weekly"}:
        raise HTTPException(400, "Unsupported report type")
    user = db.get(models.User, user_id)
    latest_risk(user_id, db)
    latest_monitoring(user_id, db)
    risk = db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user_id).order_by(models.RiskAssessment.created_at.desc()).first()
    monitoring = db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user_id).order_by(models.MonitoringAssessment.created_at.desc()).first()
    logs = db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id).order_by(models.HealthLog.created_at.asc(), models.HealthLog.log_date.asc()).all()
    content = build_report(report_type, user, risk, monitoring, logs)
    row = models.Report(user_id=user_id, report_type=report_type, content_json=content)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "user_id": row.user_id, "report_type": row.report_type, "content": row.content_json, "created_at": row.created_at}


@router.get("/reports/{user_id}", response_model=list[ReportOut])
def get_reports(user_id: int, db: Session = Depends(get_db)):
    """Return reports for a user in reverse chronological order."""
    rows = db.query(models.Report).filter(models.Report.user_id == user_id).order_by(models.Report.created_at.desc()).all()
    return [{"id": row.id, "user_id": row.user_id, "report_type": row.report_type, "content": row.content_json, "created_at": row.created_at} for row in rows]


@router.get("/reports/{report_id}/pdf")
def report_pdf(report_id: int, inline: bool = False, db: Session = Depends(get_db)):
    """Generate and return a PDF export for a report."""
    try:
        path = generate_pdf_report(db, report_id)
    except ValueError:
        raise HTTPException(404, "Report not found")
    disposition = "inline" if inline else "attachment"
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"glyco_report_{report_id}.pdf",
        content_disposition_type=disposition,
    )


@router.get("/insights/{user_id}")
def glyco_insight(user_id: int, db: Session = Depends(get_db)):
    """Build the dashboard insight panel response."""
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return build_agent_insight(db, user_id)


@router.post("/agent/chat", response_model=AgentChatOut)
def agent_chat(payload: AgentChatIn, db: Session = Depends(get_db)):
    """Run the Glyco agent pipeline with Gemini/fallback verbalization."""
    if not db.get(models.User, payload.user_id):
        raise HTTPException(404, "User not found")
    result = chat_with_agent(db, payload.user_id, payload.message)
    return {
        **result,
        "response": result["answer"],
        "tools_used": [tool["name"] for tool in result["tool_calls"]],
        "proactive_alert": False,
    }


@router.post("/agent/reset")
def reset_agent_memory(user_id: int = 1, db: Session = Depends(get_db)):
    """Clear all AgentMemory conversation history rows for a given user."""
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    db.query(models.AgentMemory).filter(models.AgentMemory.user_id == user_id).delete()
    db.commit()
    return {"status": "ok", "message": "Agent memory cleared successfully"}



@router.post("/agent/feedback", response_model=AgentFeedbackOut)
def agent_feedback(payload: AgentFeedbackIn, db: Session = Depends(get_db)):
    """Persist agent feedback and update recommendation bandit state."""
    if not db.get(models.User, payload.user_id):
        raise HTTPException(404, "User not found")
    arm = "monitoring"
    if payload.confirmed_action:
        lowered = payload.confirmed_action.lower()
        if "post" in lowered and "meal" in lowered:
            arm = "post_meal_review"
        elif "fasting" in lowered or "morning" in lowered:
            arm = "fasting_routine"
        elif "family" in lowered or "caregiver" in lowered:
            arm = "family_support"
        elif "sleep" in lowered or "stress" in lowered:
            arm = "sleep_stress"
        elif "question" in lowered or "ask" in lowered:
            arm = "clinician_questions"
        elif "meal" in lowered or "nutrition" in lowered or "carb" in lowered:
            arm = "nutrition"
        elif "walk" in lowered or "activity" in lowered:
            arm = "activity"
        elif "medication" in lowered:
            arm = "medication_check"
    RecommendationBandit(db, payload.user_id).update_feedback(arm, payload.helpful)
    return record_agent_feedback(
        db,
        payload.user_id,
        payload.message,
        payload.helpful,
        payload.preferred_tone,
        payload.confirmed_action,
        payload.notes,
    )


@router.get("/agent/llm-status")
def agent_llm_status():
    """Return current LLM configuration status."""
    return get_llm_status()


@router.get("/agent/insight/{user_id}")
def agent_insight(user_id: int, db: Session = Depends(get_db)):
    """Return agent insight for the dashboard."""
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    return build_agent_insight(db, user_id)


@router.post("/agent/proactive-check/{user_id}")
def run_agent_proactive_check(user_id: int, db: Session = Depends(get_db)):
    """Run proactive alert detection for a user."""
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    return proactive_check(db, user_id)


@router.get("/alerts/{user_id}", response_model=list[AgentAlertOut])
def get_agent_alerts(user_id: int, db: Session = Depends(get_db)):
    """Return active (unacknowledged) agent alerts.

    Alerts can be generated repeatedly by background follow-ups, so we de-duplicate
    by (title, severity) and return the most recent instance per signature.
    """
    rows = (
        db.query(models.AgentAlert)
        .filter(models.AgentAlert.user_id == user_id, models.AgentAlert.acknowledged_at.is_(None))
        .order_by(models.AgentAlert.created_at.desc())
        .all()
    )
    unique_alerts: list[models.AgentAlert] = []
    seen: set[tuple[str, str]] = set()
    max_unique = 50
    for row in rows:
        signature = (row.title, row.severity)
        if signature in seen:
            continue
        seen.add(signature)
        unique_alerts.append(row)
        if len(unique_alerts) >= max_unique:
            break
    return unique_alerts


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_agent_alert(alert_id: int, user_id: int = 1, db: Session = Depends(get_db)):
    """Acknowledge (dismiss) an alert.

    To avoid repeated identical alerts sticking around, we acknowledge *all* active
    alerts matching the same (title, severity) signature for the user.
    """
    row = db.get(models.AgentAlert, alert_id)
    if not row or row.user_id != user_id:
        raise HTTPException(404, "Alert not found")

    title = row.title
    severity = row.severity

    now = datetime.utcnow()
    updated = (
        db.query(models.AgentAlert)
        .filter(
            models.AgentAlert.user_id == user_id,
            models.AgentAlert.title == title,
            models.AgentAlert.severity == severity,
            models.AgentAlert.acknowledged_at.is_(None),
        )
        .update({models.AgentAlert.acknowledged_at: now}, synchronize_session=False)
    )
    db.commit()
    return {"acknowledged": True, "updated": updated, "title": title, "severity": severity}


@router.delete("/alerts/{alert_id}")
def delete_agent_alert(alert_id: int, user_id: int = 1, db: Session = Depends(get_db)):
    """Delete an alert.

    This deletes all alerts with the same (title, severity) signature for the user
    (including acknowledged history) to keep the store tidy.
    """
    row = db.get(models.AgentAlert, alert_id)
    if not row or row.user_id != user_id:
        raise HTTPException(404, "Alert not found")

    title = row.title
    severity = row.severity

    deleted = (
        db.query(models.AgentAlert)
        .filter(
            models.AgentAlert.user_id == user_id,
            models.AgentAlert.title == title,
            models.AgentAlert.severity == severity,
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": True, "count": deleted, "title": title, "severity": severity}


@router.post("/care-plan/diet")
def diet_plan(user_id: int = 1, force_refresh: bool = False, db: Session = Depends(get_db)):
    """Return a personalized care plan from live patient/model data."""
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    
    # Check if we have a cached diet care plan from the last 24 hours
    if not force_refresh:
        one_day_ago = datetime.utcnow() - timedelta(days=1)
        cached = (
            db.query(models.Report)
            .filter(
                models.Report.user_id == user_id,
                models.Report.report_type == "diet_care_plan",
                models.Report.created_at >= one_day_ago,
            )
            .order_by(models.Report.created_at.desc())
            .first()
        )
        if cached:
            return cached.content_json

    # Build a fresh plan
    plan = build_care_plan(db, user_id)

    # Cache it in the reports table
    report = models.Report(
        user_id=user_id,
        report_type="diet_care_plan",
        content_json=plan,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return plan


@router.post("/family-shares")
def family_share(payload: FamilyShareIn, db: Session = Depends(get_db)):
    """Create a family share token."""
    row = models.FamilyShare(user_id=payload.user_id, shared_with_name=payload.shared_with_name, relationship=payload.relationship, share_token=token_urlsafe(16), permissions_json={"read_only": True})
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"share_token": row.share_token, "url": f"/share/{row.share_token}"}


@router.get("/family-shares/{share_token}")
def read_family_share(share_token: str, db: Session = Depends(get_db)):
    """Read a family share by token."""
    share = db.query(models.FamilyShare).filter(models.FamilyShare.share_token == share_token).first()
    if not share:
        raise HTTPException(404, "Share not found")
    user = db.get(models.User, share.user_id)
    logs = db.query(models.HealthLog).filter(models.HealthLog.user_id == share.user_id).order_by(models.HealthLog.created_at.asc(), models.HealthLog.log_date.asc()).all()
    monitoring = latest_monitoring(share.user_id, db)
    risk = latest_risk(share.user_id, db)
    serialized_logs = [HealthLogOut.model_validate(log) for log in logs]
    serialized_user = UserOut.model_validate(user) if user else None
    return {
        "user": serialized_user,
        "share": {"shared_with_name": share.shared_with_name, "relationship": share.relationship},
        "logs": serialized_logs,
        "monitoring": monitoring,
        "risk": risk
    }
