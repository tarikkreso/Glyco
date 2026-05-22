from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class User(Base):
    """Application user or demo patient."""

    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email_or_demo_id: Mapped[str] = mapped_column(String(120), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    profiles = relationship("Profile", back_populates="user")


class Profile(Base):
    """Clinical profile used by the Type 2 diabetes risk model."""

    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    age: Mapped[int] = mapped_column(Integer)
    sex: Mapped[str] = mapped_column(String(20))
    height_cm: Mapped[float] = mapped_column(Float)
    weight_kg: Mapped[float] = mapped_column(Float)
    bmi: Mapped[float] = mapped_column(Float)
    high_bp: Mapped[bool] = mapped_column(Boolean, default=False)
    high_chol: Mapped[bool] = mapped_column(Boolean, default=False)
    smoker: Mapped[bool] = mapped_column(Boolean, default=False)
    phys_activity: Mapped[bool] = mapped_column(Boolean, default=True)
    fruits: Mapped[bool] = mapped_column(Boolean, default=True)
    veggies: Mapped[bool] = mapped_column(Boolean, default=True)
    general_health: Mapped[int] = mapped_column(Integer, default=3)
    stroke_history: Mapped[bool] = mapped_column(Boolean, default=False)
    heart_disease_history: Mapped[bool] = mapped_column(Boolean, default=False)
    difficulty_walking: Mapped[bool] = mapped_column(Boolean, default=False)
    family_history_diabetes: Mapped[bool] = mapped_column(Boolean, default=False)
    fasting_glucose_optional: Mapped[float | None] = mapped_column(Float)
    hba1c_optional: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="profiles")


class RiskAssessment(Base):
    """Stored Random Forest or fallback diabetes risk assessment."""

    __tablename__ = "risk_assessments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    risk_probability: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(20))
    top_factors_json: Mapped[list] = mapped_column(JSON)
    related_flags_json: Mapped[list] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HealthLog(Base):
    """Patient-entered glucose and lifestyle monitoring log."""

    __tablename__ = "health_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    log_date: Mapped[date] = mapped_column(Date)
    is_fasting: Mapped[bool] = mapped_column(Boolean, default=True)
    fasting_glucose: Mapped[float] = mapped_column(Float)
    post_meal_glucose: Mapped[float | None] = mapped_column(Float)
    hba1c_optional: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    bmi_optional: Mapped[float | None] = mapped_column(Float)
    systolic_bp: Mapped[int | None] = mapped_column(Integer)
    diastolic_bp: Mapped[int | None] = mapped_column(Integer)
    activity_minutes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def glucose_level(self) -> float:
        return self.fasting_glucose


class MonitoringAssessment(Base):
    """Stored monitoring trend assessment for a user's recent logs."""

    __tablename__ = "monitoring_assessments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assessment_date: Mapped[date] = mapped_column(Date)
    trend_label: Mapped[str] = mapped_column(String(20))
    trend_score: Mapped[float] = mapped_column(Float)
    anomaly_flags_json: Mapped[list] = mapped_column(JSON)
    summary_json: Mapped[dict] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Report(Base):
    """Generated report metadata and JSON content."""

    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    report_type: Mapped[str] = mapped_column(String(40))
    content_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FamilyShare(Base):
    """Read-only sharing token for family support views."""

    __tablename__ = "family_shares"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    shared_with_name: Mapped[str] = mapped_column(String(120))
    relationship: Mapped[str] = mapped_column(String(80))
    share_token: Mapped[str] = mapped_column(String(80), unique=True)
    permissions_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GlucoseForecast(Base):
    """
    Stores point-in-time glucose forecast results per user.
    Each row represents one forecast run triggered by a new log entry
    or an explicit user request.
    """

    __tablename__ = "glucose_forecasts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    current_glucose: Mapped[float | None] = mapped_column(Float)
    prediction_60min: Mapped[float | None] = mapped_column(Float)
    prediction_120min: Mapped[float | None] = mapped_column(Float)
    prediction_180min: Mapped[float | None] = mapped_column(Float)
    prediction_240min: Mapped[float | None] = mapped_column(Float)
    ci_60_low: Mapped[float | None] = mapped_column(Float)
    ci_60_high: Mapped[float | None] = mapped_column(Float)
    ci_120_low: Mapped[float | None] = mapped_column(Float)
    ci_120_high: Mapped[float | None] = mapped_column(Float)
    ci_180_low: Mapped[float | None] = mapped_column(Float)
    ci_180_high: Mapped[float | None] = mapped_column(Float)
    ci_240_low: Mapped[float | None] = mapped_column(Float)
    ci_240_high: Mapped[float | None] = mapped_column(Float)
    trend_direction: Mapped[str | None] = mapped_column(String)
    predicted_low_alert: Mapped[bool] = mapped_column(Boolean, default=False)
    predicted_high_alert: Mapped[bool] = mapped_column(Boolean, default=False)
    recommendation: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String)
    used_fallback: Mapped[bool] = mapped_column(Boolean, default=False)


class GlucoseForecastEvaluation(Base):
    """Stores actual-vs-predicted glucose comparisons for forecast learning."""

    __tablename__ = "glucose_forecast_evaluations"
    __table_args__ = (
        UniqueConstraint("forecast_id", "horizon_minutes", name="uq_forecast_eval_horizon"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    forecast_id: Mapped[int] = mapped_column(ForeignKey("glucose_forecasts.id"), nullable=False)
    horizon_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_for: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    predicted_mmol: Mapped[float] = mapped_column(Float, nullable=False)
    actual_log_id: Mapped[int] = mapped_column(ForeignKey("health_logs.id"), nullable=False)
    actual_mmol: Mapped[float] = mapped_column(Float, nullable=False)
    absolute_error: Mapped[float] = mapped_column(Float, nullable=False)
    signed_error: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String)
    matched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GlucoseForecastCalibration(Base):
    """Stores lightweight per-user forecast calibration learned from outcomes."""

    __tablename__ = "glucose_forecast_calibrations"
    __table_args__ = (
        UniqueConstraint("user_id", "horizon_minutes", "model_version", name="uq_forecast_calibration"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    horizon_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0)
    mean_absolute_error: Mapped[float] = mapped_column(Float, default=0.0)
    signed_bias: Mapped[float] = mapped_column(Float, default=0.0)
    model_version: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentAlert(Base):
    """Proactive alert generated by the Glyco agent."""

    __tablename__ = "agent_alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    severity: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(Text)
    source_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)


class AgentFeedback(Base):
    """User feedback that teaches the agent response preferences."""

    __tablename__ = "agent_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(Text)
    helpful: Mapped[bool] = mapped_column(Boolean)
    preferred_tone: Mapped[str] = mapped_column(String(40), default="balanced")
    confirmed_action: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BayesianRiskState(Base):
    """Per-user Bayesian posterior layered over Random Forest risk signals."""

    __tablename__ = "bayesian_risk_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    alpha: Mapped[float] = mapped_column(Float, default=2.0)
    beta: Mapped[float] = mapped_column(Float, default=5.0)
    posterior_mean: Mapped[float] = mapped_column(Float, default=2.0 / 7.0)
    credible_interval_low: Mapped[float] = mapped_column(Float, default=0.0)
    credible_interval_high: Mapped[float] = mapped_column(Float, default=1.0)
    updates_count: Mapped[int] = mapped_column(Integer, default=0)
    prior_alpha: Mapped[float] = mapped_column(Float, default=2.0)
    prior_beta: Mapped[float] = mapped_column(Float, default=5.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BanditArmState(Base):
    """Persisted Thompson Sampling arm state for recommendation reranking."""

    __tablename__ = "bandit_arm_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    arm_name: Mapped[str] = mapped_column(String(80))
    alpha: Mapped[float] = mapped_column(Float, default=1.0)
    beta: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentMemory(Base):
    """Conversation history item stored per user for agent continuity."""

    __tablename__ = "agent_memory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
