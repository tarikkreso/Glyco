from secrets import token_urlsafe
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db import models
from app.agent.anthropic_agent import detect_glucose_anomaly_and_report
from app.agent.bandit import RecommendationBandit
from app.agent.agent_service import build_agent_insight, chat_with_agent, proactive_check, record_agent_feedback
from app.agent.llm_client import get_llm_status
from app.schemas.schemas import AgentAlertOut, AgentChatIn, AgentChatOut, AgentFeedbackIn, AgentFeedbackOut, FamilyShareIn, HealthLogIn, HealthLogOut, ProfileIn, ProfileOut, ReportOut, UserOut
from app.rules.engine import calculate_bmi
from app.services.bayesian import get_or_create_bayesian_state, serialize_bayesian_state
from app.services.assessments import create_monitoring_assessment, create_risk_assessment
from app.services.pdf_service import generate_pdf_report
from app.reports.generator import build_report

router = APIRouter()


@router.post("/users/demo", response_model=UserOut)
def demo_user(db: Session = Depends(get_db)):
    """Return the primary seeded demo user."""
    return db.query(models.User).filter(models.User.email_or_demo_id == "demo-monitoring").first()


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
def create_log(payload: HealthLogIn, db: Session = Depends(get_db)):
    """Create a glucose log and update monitoring and alerts."""
    row = models.HealthLog(
        user_id=payload.user_id,
        log_date=date.today(),
        is_fasting=payload.is_fasting,
        fasting_glucose=payload.glucose_level,
        post_meal_glucose=None if payload.is_fasting else payload.glucose_level,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    create_monitoring_assessment(db, payload.user_id)
    proactive_check(db, payload.user_id)
    detect_glucose_anomaly_and_report(db, payload.user_id)
    return row


@router.get("/logs/{user_id}", response_model=list[HealthLogOut])
def get_logs(user_id: int, db: Session = Depends(get_db)):
    """Return all logs for a user in chronological order."""
    return db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id).order_by(models.HealthLog.log_date.asc()).all()


@router.post("/monitoring-assessment")
def monitoring_assessment(user_id: int = 1, db: Session = Depends(get_db)):
    """Create a monitoring assessment for a user."""
    return create_monitoring_assessment(db, user_id)


@router.get("/monitoring-assessment/{user_id}/latest")
def latest_monitoring(user_id: int, db: Session = Depends(get_db)):
    """Return or refresh the latest monitoring assessment."""
    row = db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user_id).order_by(models.MonitoringAssessment.created_at.desc()).first()
    latest_log = db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id).order_by(models.HealthLog.log_date.desc()).first()
    if row and (row.model_version != "glucose-trend-random-forest-0.2" or (latest_log and latest_log.created_at > row.created_at)):
        return create_monitoring_assessment(db, user_id)
    if not row:
        return create_monitoring_assessment(db, user_id)
    return {"id": row.id, "user_id": row.user_id, "trend_label": row.trend_label, "trend_score": row.trend_score, "anomaly_flags": row.anomaly_flags_json, "summary": row.summary_json, "recommended_actions": ["Keep logging consistently"], "model_version": row.model_version}


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
    logs = db.query(models.HealthLog).filter(models.HealthLog.user_id == user_id).order_by(models.HealthLog.log_date.asc()).all()
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


@router.post("/agent/feedback", response_model=AgentFeedbackOut)
def agent_feedback(payload: AgentFeedbackIn, db: Session = Depends(get_db)):
    """Persist agent feedback and update recommendation bandit state."""
    if not db.get(models.User, payload.user_id):
        raise HTTPException(404, "User not found")
    arm = "monitoring"
    if payload.confirmed_action:
        lowered = payload.confirmed_action.lower()
        if "meal" in lowered or "nutrition" in lowered or "carb" in lowered:
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
    """Return active and historical agent alerts."""
    return db.query(models.AgentAlert).filter(models.AgentAlert.user_id == user_id).order_by(models.AgentAlert.created_at.desc()).all()


@router.post("/care-plan/diet")
def diet_plan(user_id: int = 1):
    """Return a static diet plan for the MVP care plan page."""
    return {"user_id": user_id, "direction": "Steady glucose support", "prefer": ["High-fiber vegetables", "Lean proteins", "Beans and lentils", "Unsweetened yogurt"], "limit": ["Sugary drinks", "Large refined-carb portions", "Late-night snacks"], "sample_day": ["Eggs with spinach", "Lentil soup and salad", "Grilled fish with vegetables"], "weekly_recommendations": ["Walk 10-15 minutes after main meals", "Log fasting glucose at least 4 mornings", "Prepare low-carb snacks ahead of time"]}


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
    logs = db.query(models.HealthLog).filter(models.HealthLog.user_id == share.user_id).order_by(models.HealthLog.log_date.asc()).all()
    monitoring = latest_monitoring(share.user_id, db)
    risk = latest_risk(share.user_id, db)
    return {"user": user, "share": {"shared_with_name": share.shared_with_name, "relationship": share.relationship}, "logs": logs, "monitoring": monitoring, "risk": risk}
