from datetime import date, datetime
from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    full_name: str
    email_or_demo_id: str
    created_at: datetime
    model_config = {"from_attributes": True}


class UserRegisterIn(BaseModel):
    full_name: str = Field("Glyco User", min_length=1, max_length=120)
    email: str = Field(..., min_length=3, max_length=120)


class UserUpdateIn(BaseModel):
    full_name: str = Field("Glyco User", min_length=1, max_length=120)
    email: str = Field(..., min_length=3, max_length=120)


class ProfileIn(BaseModel):
    user_id: int = 1
    age: int = Field(55, ge=18, le=100)
    sex: str = "Female"
    height_cm: float = Field(168, gt=80, lt=240)
    weight_kg: float = Field(86, gt=30, lt=250)
    high_bp: bool = True
    high_chol: bool = True
    smoker: bool = False
    phys_activity: bool = True
    fruits: bool = True
    veggies: bool = True
    general_health: int = Field(3, ge=1, le=5)
    stroke_history: bool = False
    heart_disease_history: bool = False
    difficulty_walking: bool = False
    family_history_diabetes: bool = True
    forecast_personalization_enabled: bool = True
    fasting_glucose_optional: float | None = None
    hba1c_optional: float | None = None


class ProfileOut(ProfileIn):
    id: int
    bmi: float
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class HealthLogIn(BaseModel):
    user_id: int = 1
    glucose_level: float = Field(118, ge=40, le=500)
    is_fasting: bool = True
    reading_time: datetime | None = None


class HealthLogOut(BaseModel):
    id: int
    user_id: int
    log_date: date
    glucose_level: float
    is_fasting: bool
    fasting_glucose: float
    post_meal_glucose: float | None = None
    hba1c_optional: float | None = None
    weight_kg: float | None = None
    bmi_optional: float | None = None
    systolic_bp: int | None = None
    diastolic_bp: int | None = None
    activity_minutes: int | None = None
    notes: str | None = None
    created_at: datetime
    reading_time: datetime
    model_config = {"from_attributes": True}


class RiskAssessmentOut(BaseModel):
    id: int | None = None
    user_id: int
    profile_id: int
    risk_probability: float
    risk_level: str
    confidence_label: str
    top_factors: list[dict]
    related_flags: list[dict]
    explanation: str
    next_actions: list[str]
    model_version: str


class MonitoringAssessmentOut(BaseModel):
    id: int | None = None
    user_id: int
    trend_label: str
    trend_score: float
    anomaly_flags: list[dict]
    summary: dict
    recommended_actions: list[str]
    model_version: str


class GlucoseForecastOut(BaseModel):
    """Public response shape for generated and stored glucose forecasts."""

    user_id: int
    current_glucose: float
    predictions: dict[str, float]
    confidence_intervals: dict[str, dict[str, float]]
    trend_direction: str
    predicted_low_alert: bool
    predicted_high_alert: bool
    recommendation: str
    model_version: str
    used_fallback: bool
    horizon_minutes: list[int]
    created_at: datetime | None = None
    calibration_applied: bool = False
    personalization_enabled: bool = True
    personal_mae_per_horizon: dict[str, float] | None = None
    forecast_quality: str | None = None


class ReportOut(BaseModel):
    id: int | None = None
    user_id: int
    report_type: str
    content: dict
    created_at: datetime | None = None


class FamilyShareIn(BaseModel):
    user_id: int = 1
    shared_with_name: str = "Care Circle"
    relationship: str = "Family"


class AgentChatIn(BaseModel):
    user_id: int = 1
    message: str = Field(..., min_length=2, max_length=1200)


class AgentChatOut(BaseModel):
    """Chat response that preserves legacy fields while adding v1 agent metadata."""

    answer: str
    response: str | None = None
    tools_used: list[str] = []
    proactive_alert: bool = False
    tool_calls: list[dict]
    guideline_snippets: list[dict]
    safety_note: str
    patient_name: str
    llm_mode: str
    llm_model: str
    learning_summary: dict
    recommendations: list[dict] = []


class AgentFeedbackIn(BaseModel):
    user_id: int = 1
    message: str = Field(..., min_length=2, max_length=1200)
    helpful: bool = True
    preferred_tone: str = Field("balanced", max_length=40)
    confirmed_action: str | None = Field(None, max_length=600)
    notes: str | None = Field(None, max_length=600)


class AgentFeedbackOut(BaseModel):
    id: int
    user_id: int
    helpful: bool
    preferred_tone: str
    confirmed_action: str | None = None
    notes: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class AgentAlertOut(BaseModel):
    id: int
    user_id: int
    severity: str
    title: str
    message: str
    recommended_action: str
    source_json: dict
    created_at: datetime
    acknowledged_at: datetime | None = None
    model_config = {"from_attributes": True}
