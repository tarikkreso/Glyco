const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export type HealthLog = {
  id: number;
  user_id: number;
  log_date: string;
  glucose_level: number;
  is_fasting: boolean;
  fasting_glucose: number;
  post_meal_glucose?: number;
  weight_kg?: number;
  systolic_bp?: number;
  diastolic_bp?: number;
  activity_minutes?: number;
  notes?: string;
  created_at?: string;
  reading_time?: string;
};

export type UserAccount = {
  id: number;
  full_name: string;
  email_or_demo_id: string;
  created_at?: string;
};

export type RiskAssessment = {
  risk_probability: number;
  risk_level: string;
  confidence_label: string;
  top_factors: Array<{ label: string; impact: number; detail: string }>;
  related_flags: Array<{ level: string; label: string; detail: string }>;
  explanation: string;
  next_actions: string[];
  model_version: string;
};

export type Profile = {
  id: number;
  user_id: number;
  age: number;
  sex: string;
  height_cm: number;
  weight_kg: number;
  bmi: number;
  high_bp: boolean;
  high_chol: boolean;
  smoker: boolean;
  phys_activity: boolean;
  fruits: boolean;
  veggies: boolean;
  general_health: number;
  stroke_history: boolean;
  heart_disease_history: boolean;
  difficulty_walking: boolean;
  family_history_diabetes: boolean;
  forecast_personalization_enabled: boolean;
  fasting_glucose_optional?: number | null;
  hba1c_optional?: number | null;
  created_at: string;
  updated_at: string;
};

export type BayesianRisk = {
  user_id: number;
  posterior_mean: number;
  credible_interval: { low: number; high: number };
  number_of_updates: number;
  prior: { alpha: number; beta: number; mean: number };
  posterior: { alpha: number; beta: number; mean: number };
  comparison: { absolute_change: number; relative_change: number };
};

export type MonitoringAssessment = {
  trend_label: string;
  trend_score: number;
  anomaly_flags: Array<{ level: string; label: string; detail: string }>;
  summary: Record<string, string | number>;
  recommended_actions: string[];
  model_version: string;
};

export type GlucoseForecast = {
  user_id: number;
  current_glucose: number;
  predictions: Record<"60" | "120" | "180" | "240", number>;
  confidence_intervals: Record<"60" | "120" | "180" | "240", { low: number; high: number }>;
  trend_direction: "rising" | "falling" | "stable" | string;
  predicted_low_alert: boolean;
  predicted_high_alert: boolean;
  recommendation: string;
  model_version: string;
  used_fallback: boolean;
  horizon_minutes: number[];
  created_at?: string;
  calibration_applied?: boolean;
  personalization_enabled?: boolean;
  personal_mae_per_horizon?: Record<string, number> | null;
  forecast_quality?: "learning" | "calibrated" | "needs_more_data" | string | null;
};

export type ForecastAccuracy = {
  user_id: number;
  personalization_enabled?: boolean;
  total_evaluations: number;
  per_horizon: Record<string, { count: number; mae: number; bias: number }>;
  latest: Array<Record<string, unknown>>;
};

export type ReportDocument = {
  id?: number;
  user_id?: number;
  report_type: string;
  created_at?: string;
  content: {
    title: string;
    sections: Array<{ title: string; body: string }>;
    disclaimer?: string;
  };
};

export type GlycoInsight = {
  title: string;
  patient_name: string;
  what_changed: string;
  why_it_matters: string;
  what_to_do_next: string[];
  what_to_ask_your_doctor: string[];
  confidence_note: string;
  tool_calls?: AgentToolCall[];
  guideline_snippets?: GuidelineSnippet[];
  llm_mode?: string;
  llm_model?: string;
  learning_summary?: AgentLearningSummary;
};

export type AgentToolCall = {
  name: string;
  label?: string;
  status: string;
  result_summary?: string;
  model_version?: string;
  details?: Record<string, unknown>;
};

export type GuidelineSnippet = {
  id: string;
  category: string;
  text: string;
};

export type AgentChatResponse = {
  answer: string;
  response?: string;
  tools_used?: string[];
  proactive_alert?: boolean;
  tool_calls: AgentToolCall[];
  guideline_snippets: GuidelineSnippet[];
  safety_note: string;
  patient_name: string;
  llm_mode: string;
  llm_model: string;
  learning_summary: AgentLearningSummary;
  recommendations?: AgentRecommendation[];
};

export type AgentRecommendation = {
  type: string;
  title: string;
  body: string;
  bandit_score?: number;
  bandit_alpha?: number;
  bandit_beta?: number;
};

export type AgentLearningSummary = {
  feedback_count: number;
  helpful_rate: number | null;
  preferred_tone: string;
  confirmed_actions: string[];
  adaptation_note: string;
  preferred_action_type?: string;
  avoided_action_types?: string[];
  action_type_scores?: Record<string, number>;
  recent_glucose_pattern?: {
    label: string;
    average: number | null;
    slope: number | null;
    high_count: number;
  };
  next_best_action?: {
    type: string;
    title: string;
    body: string;
  };
};

export type AgentFeedback = {
  id: number;
  user_id: number;
  helpful: boolean;
  preferred_tone: string;
  confirmed_action?: string;
  notes?: string;
  created_at: string;
};

export type AgentAlert = {
  id: number;
  user_id: number;
  severity: string;
  title: string;
  message: string;
  recommended_action: string;
  source_json: Record<string, unknown>;
  created_at: string;
  acknowledged_at?: string;
};

export type AlertActionResult = {
  acknowledged?: boolean;
  deleted?: boolean;
  updated?: number;
  count?: number;
  title?: string;
  severity?: string;
};

export type CarePlan = {
  user_id: number;
  source: string;
  direction: string;
  prefer: string[];
  limit: string[];
  sample_day: string[];
  weekly_recommendations: string[];
  signals?: {
    risk_level?: string;
    risk_model_version?: string;
    trend_label?: string;
    trend_model_version?: string;
    latest_glucose?: number;
    latest_is_fasting?: boolean;
    avg_fasting?: number | null;
    avg_post_meal?: number | null;
    bayesian_posterior?: number;
    top_recommendation_type?: string;
  };
};

export const api = {
  demoUser: () => request<{ id: number; full_name: string }>("/users/demo", { method: "POST" }),
  registerUser: (payload: { full_name: string; email: string }) =>
    request<UserAccount>("/users/register", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (userId: number, payload: { full_name: string; email: string }) =>
    request<UserAccount>(`/users/${userId}`, { method: "PUT", body: JSON.stringify(payload) }),
  profile: (userId = 1) => request<Profile>(`/profiles/${userId}`),
  updateProfile: (profileId: number, payload: Record<string, unknown>) =>
    request<Profile>(`/profiles/${profileId}`, { method: "PUT", body: JSON.stringify(payload) }),
  logs: (userId = 1) => request<HealthLog[]>(`/logs/${userId}`),
  latestRisk: (userId = 1) => request<RiskAssessment>(`/risk-assessment/${userId}/latest`),
  bayesianRisk: (userId = 1) => request<BayesianRisk>(`/risk/bayesian/${userId}`),
  latestMonitoring: (userId = 1) => request<MonitoringAssessment>(`/monitoring-assessment/${userId}/latest`),
  getForecastLatest: (userId = 1) => request<GlucoseForecast>(`/forecast/${userId}/latest`),
  getForecastHistory: (userId = 1) => request<GlucoseForecast[]>(`/forecast/${userId}/history`),
  getForecastAccuracy: (userId = 1) => request<ForecastAccuracy>(`/forecast/${userId}/accuracy`),
  triggerForecast: (userId = 1) => request<GlucoseForecast>(`/forecast/${userId}`, { method: "POST" }),
  assessRisk: (payload: Record<string, unknown>) => request<RiskAssessment>("/risk-assessment", { method: "POST", body: JSON.stringify(payload) }),
  addLog: (payload: { user_id?: number; glucose_level: number; is_fasting: boolean; reading_time?: string }) => request<HealthLog>("/logs", { method: "POST", body: JSON.stringify(payload) }),
  assessMonitoring: (userId = 1) => request<MonitoringAssessment>(`/monitoring-assessment?user_id=${userId}`, { method: "POST" }),
  report: (type: string, userId = 1) => request<ReportDocument>(`/reports/${type}?user_id=${userId}`, { method: "POST" }),
  reports: (userId = 1) => request<ReportDocument[]>(`/reports/${userId}`),
  reportPdfUrl: (reportId: number, inline = false) => `${API_BASE}/reports/${reportId}/pdf${inline ? "?inline=1" : ""}`,
  insight: (userId = 1) => request<GlycoInsight>(`/agent/insight/${userId}`),
  agentChat: (message: string, userId = 1) => request<AgentChatResponse>("/agent/chat", { method: "POST", body: JSON.stringify({ user_id: userId, message }) }),
  resetAgentMemory: (userId = 1) => request<{ status: string }>(`/agent/reset?user_id=${userId}`, { method: "POST" }),
  agentFeedback: (payload: { user_id?: number; message: string; helpful: boolean; preferred_tone: string; confirmed_action?: string; notes?: string }) => request<AgentFeedback>("/agent/feedback", { method: "POST", body: JSON.stringify({ user_id: 1, ...payload }) }),
  proactiveCheck: (userId = 1) => request<Record<string, unknown>>(`/agent/proactive-check/${userId}`, { method: "POST" }),
  alerts: (userId = 1) => request<AgentAlert[]>(`/alerts/${userId}`),
  acknowledgeAlert: (alertId: number, userId = 1) =>
    request<AlertActionResult>(`/alerts/${alertId}/acknowledge?user_id=${userId}`, { method: "POST" }),
  deleteAlert: (alertId: number, userId = 1) =>
    request<AlertActionResult>(`/alerts/${alertId}?user_id=${userId}`, { method: "DELETE" }),
  diet: (userId = 1, forceRefresh = false) => request<CarePlan>(`/care-plan/diet?user_id=${userId}&force_refresh=${forceRefresh}`, { method: "POST" }),
  familyShare: (token = "demo-family-sarah") => request<Record<string, unknown>>(`/family-shares/${token}`),
  createFamilyShare: (payload: { user_id: number; shared_with_name: string; relationship: string }) => request<{ share_token: string; url: string }>("/family-shares", { method: "POST", body: JSON.stringify(payload) }),
};
