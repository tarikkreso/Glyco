from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from statistics import mean
from typing import Protocol

import httpx

from app.agent.language import detect_language, language_name

logger = logging.getLogger(__name__)
GEMINI_COOLDOWN_UNTIL = 0.0


def llm_network_enabled() -> bool:
    """Return whether LLM clients are allowed to make outbound HTTP calls."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return os.getenv("GLYCO_DISABLE_LLM_NETWORK", "").strip().lower() not in {"1", "true", "yes", "on"}


def _load_env_files() -> None:
    """Refresh provider-related environment variables from local .env files."""
    module_path = Path(__file__).resolve()
    repo_root = module_path.parents[3] if len(module_path.parents) > 3 else module_path.parents[-1]
    env_paths = [repo_root / "backend" / ".env", repo_root / ".env"]
    for env_path in env_paths:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # Respect explicitly-set environment variables (including empty
            # strings set by tests to prevent re-population).
            if key and key not in os.environ:
                os.environ[key] = value


def _gemini_cooldown_seconds() -> float:
    """Return how long Gemini should be skipped after a rate-limit response."""
    return float(os.getenv("GLYCO_GEMINI_429_COOLDOWN_SECONDS", "120"))


def gemini_is_rate_limited() -> bool:
    """Return whether Gemini calls should be skipped because of a recent 429."""
    return time.time() < GEMINI_COOLDOWN_UNTIL


def note_gemini_rate_limit() -> None:
    """Record a short Gemini cooldown after Google returns HTTP 429."""
    global GEMINI_COOLDOWN_UNTIL
    # A temporary cooldown prevents every dashboard refresh from retrying a known exhausted quota.
    GEMINI_COOLDOWN_UNTIL = time.time() + _gemini_cooldown_seconds()


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


class LLMClient(Protocol):
    def generate(self, messages: list[dict], tools_context: dict) -> str | None:
        ...


class FallbackLLMClient:
    def __init__(self) -> None:
        self.provider_name = "fallback"
        self.model_name = "fallback"

    def generate(self, messages: list[dict], tools_context: dict) -> str | None:
        return "Error: No active LLM provider configured. Please set DEEPSEEK_API_KEY (or OPENROUTER_API_KEY) and/or GLYCO_LLM_PROVIDER."


class GroqClient:
    def __init__(self) -> None:
        self.provider_name = "groq"
        self.api_key = _first_env(
            "GROQ_API_KEY",
            "GLYCO_GROQ_API_KEY",
        )
        self.model = os.getenv("GLYCO_GROQ_MODEL", "llama-3.3-70b-versatile")
        self.model_name = self.model
        self.base_url = os.getenv("GLYCO_GROQ_URL", "https://api.groq.com/openai/v1")
        self.timeout = float(os.getenv("GLYCO_GROQ_TIMEOUT_SECONDS", "45"))
        self.last_error: str | None = None

    def generate(self, messages: list[dict], tools_context: dict) -> str | None:
        self.last_error = None
        if not llm_network_enabled():
            self.last_error = "LLM network disabled"
            return None
        if not self.api_key:
            logger.warning("Groq generation skipped: GROQ_API_KEY is not set")
            self.last_error = "API key is not set"
            return None
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.25,
            }
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
            choice = result.get("choices", [{}])[0]
            message = choice.get("message") or {}
            answer = (message.get("content") or choice.get("text") or "").strip()
            return answer or None
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            reason = exc.response.reason_phrase or "HTTP error"
            detail = ""
            try:
                payload = exc.response.json()
                if isinstance(payload, dict):
                    err = payload.get("error")
                    if isinstance(err, dict):
                        detail = str(err.get("message") or err.get("type") or "")
                    else:
                        detail = str(payload.get("message") or "")
            except Exception:
                detail = (exc.response.text or "").strip()
            detail = " ".join(detail.split())
            self.last_error = f"{status} {reason}" + (f": {detail[:180]}" if detail else "")
            logger.warning("Groq generation failed: %s", self.last_error)
            return None
        except httpx.RequestError as exc:
            self.last_error = f"Network error: {exc}"
            logger.warning("Groq generation failed: %s", self.last_error)
            return None
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("Groq generation failed: %s", exc)
            return None


class DeepSeekClient:
    def __init__(self) -> None:
        self.provider_name = "deepseek"
        self.api_key = _first_env(
            "DEEPSEEK_API_KEY",
            "GLYCO_DEEPSEEK_API_KEY",
            # Alias for OpenRouter keys (OpenRouter uses OpenAI-style endpoints).
            "OPENROUTER_API_KEY",
            "GLYCO_OPENROUTER_API_KEY",
        )
        self.model = os.getenv("GLYCO_DEEPSEEK_MODEL", "deepseek/deepseek-v4-flash:free")
        self.model_name = self.model
        self.base_url = os.getenv("GLYCO_DEEPSEEK_URL", "https://openrouter.ai/api/v1")
        self.timeout = float(os.getenv("GLYCO_DEEPSEEK_TIMEOUT_SECONDS", "45"))
        self.last_error: str | None = None

    def generate(self, messages: list[dict], tools_context: dict) -> str | None:
        self.last_error = None
        if not llm_network_enabled():
            self.last_error = "LLM network disabled"
            return None
        if not self.api_key:
            logger.warning("DeepSeek generation skipped: DEEPSEEK_API_KEY is not set")
            self.last_error = "API key is not set"
            return None
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/tarikkreso/Glyco",
                "X-OpenRouter-Title": "Glyco",
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.25,
            }
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
            choice = result.get("choices", [{}])[0]
            message = choice.get("message") or {}
            answer = (message.get("content") or choice.get("text") or "").strip()
            return answer or None
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            reason = exc.response.reason_phrase or "HTTP error"
            detail = ""
            try:
                payload = exc.response.json()
                if isinstance(payload, dict):
                    err = payload.get("error")
                    if isinstance(err, dict):
                        detail = str(err.get("message") or err.get("type") or "")
                    else:
                        detail = str(payload.get("message") or "")
            except Exception:
                detail = (exc.response.text or "").strip()
            detail = " ".join(detail.split())
            self.last_error = f"{status} {reason}" + (f": {detail[:180]}" if detail else "")
            logger.warning("DeepSeek generation failed: %s", self.last_error)
            return None
        except httpx.RequestError as exc:
            self.last_error = f"Network error: {exc}"
            logger.warning("DeepSeek generation failed: %s", self.last_error)
            return None
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("DeepSeek generation failed: %s", exc)
            return None



def _patient_summary(tools_context: dict) -> dict:
    logs = tools_context.get("logs") or []
    glucose = [
        item.get("glucose_level", item.get("fasting_glucose"))
        for item in logs
        if item.get("glucose_level", item.get("fasting_glucose")) is not None
    ]
    fasting_count = sum(1 for item in logs if item.get("is_fasting"))
    non_fasting_count = sum(1 for item in logs if item.get("is_fasting") is False)
    return {
        "profile": tools_context.get("profile") or {},
        "risk": tools_context.get("risk") or {},
        "bayesian": tools_context.get("bayesian") or {},
        "trend": tools_context.get("trend") or {},
        "forecast": tools_context.get("forecast"),
        "guidelines": tools_context.get("guidelines") or [],
        "learning": tools_context.get("learning") or {},
        "recommendations": tools_context.get("recommendations") or [],
        "care_plan": tools_context.get("care_plan") or {},
        "log_count": len(logs),
        "avg_glucose": round(mean(glucose), 1) if glucose else None,
        "min_glucose": min(glucose) if glucose else None,
        "max_glucose": max(glucose) if glucose else None,
        "latest_glucose": glucose[-1] if glucose else None,
        "fasting_count": fasting_count,
        "non_fasting_count": non_fasting_count,
        "latest_log": logs[-1] if logs else None,
    }


def _forecast_block(forecast: dict | None) -> str:
    """Build the glucose forecast context block shown to configured LLMs."""
    if forecast is None:
        return "GLUCOSE FORECAST: Not available yet (insufficient log history)."
    intervals = forecast["confidence_intervals"]
    predictions = forecast["predictions"]
    return f"""GLUCOSE FORECAST (LightGBM, trained on Type 2 CGM data):
  Current:  {forecast['current_glucose']:.1f} mmol/L
  +60 min:  {predictions['60']:.1f} mmol/L  [{intervals['60']['low']:.1f}-{intervals['60']['high']:.1f}]
  +120 min: {predictions['120']:.1f} mmol/L [{intervals['120']['low']:.1f}-{intervals['120']['high']:.1f}]
  +180 min: {predictions['180']:.1f} mmol/L [{intervals['180']['low']:.1f}-{intervals['180']['high']:.1f}]
  +240 min: {predictions['240']:.1f} mmol/L [{intervals['240']['low']:.1f}-{intervals['240']['high']:.1f}]
  Trend: {forecast['trend_direction']}
  Low alert: {forecast['predicted_low_alert']}
  High alert: {forecast['predicted_high_alert']}
  Recommendation: {forecast['recommendation']}
  Fallback used: {forecast['used_fallback']}"""


def _care_plan_and_time_block(care_plan: dict | None) -> str:
    """Build the care plan and current time of day context block shown to configured LLMs."""
    from datetime import datetime
    now = datetime.now()
    hour = now.hour
    
    # Map hour of day to meal time
    if 5 <= hour < 11:
        time_label = "Morning (Breakfast time)"
        meal_idx = 0
        meal_name = "Breakfast"
    elif 11 <= hour < 16:
        time_label = "Midday (Lunch time)"
        meal_idx = 1
        meal_name = "Lunch"
    elif 16 <= hour < 21:
        time_label = "Evening (Dinner time)"
        meal_idx = 2
        meal_name = "Dinner"
    else:
        time_label = "Night (Snack time)"
        meal_idx = 3
        meal_name = "Snack"

    if not care_plan:
        return f"CURRENT TIME: {time_label}. CARE PLAN: Not available."
        
    prefer = care_plan.get("prefer") or []
    limit = care_plan.get("limit") or []
    sample_day = care_plan.get("sample_day") or []
    
    prefer_str = ", ".join(prefer) if prefer else "None"
    limit_str = ", ".join(limit) if limit else "None"
    
    meal_suggestion = ""
    if len(sample_day) > meal_idx:
        meal_suggestion = f"\n  - Recommended Meal for {meal_name}: {sample_day[meal_idx]}"
    
    sample_day_str = "\n".join(f"  - {label}: {meal}" for label, meal in zip(["Breakfast", "Lunch", "Dinner", "Snack"], sample_day))
    
    return f"""CURRENT TIME OF DAY: {time_label}
PATIENT PERSONALIZED DIET CARE PLAN:
- Direction: {care_plan.get('direction', 'No specific direction.')}
- Preferred Foods (Anchor foods): {prefer_str}
- Avoid or Limit: {limit_str}
- Stored Sample Day Meal Plan:{meal_suggestion}
{sample_day_str}"""


def _build_concise_prompt(messages: list[dict], tools_context: dict) -> str:
    user_message = next((item["content"] for item in reversed(messages) if item.get("role") == "user"), "")
    target_language = language_name(detect_language(user_message))
    summary = _patient_summary(tools_context)
    profile = summary["profile"]
    risk = summary["risk"]
    bayesian = summary["bayesian"]
    trend = summary["trend"]
    risk_source = "RF risk model" if risk.get("model_version") == "random-forest-0.2" else "risk fallback scorer"
    trend_source = "glucose trend model" if trend.get("model_version") == "glucose-trend-random-forest-0.2" else "monitoring fallback scorer"
    guidance = "; ".join(item.get("text", "") for item in summary["guidelines"][:2] if item.get("text"))
    learning = summary["learning"]
    next_action = learning.get("next_best_action") or {}
    forecast_text = _forecast_block(summary["forecast"])
    care_plan_text = _care_plan_and_time_block(summary.get("care_plan"))
    return f"""You are Glyco, a careful diabetes risk and monitoring assistant.

Core rules:
- Required response language: {target_language}. Write the entire answer in {target_language}.
- **Language & Translation**: You MUST detect the language of the user's latest query (e.g. Bosnian, Croatian, Serbian, or any other language) and write the entire response, including any headings or bullets, in that exact language.
- **Direct Answer First**: Always address the user's specific question or topic directly and scientifically at the very beginning of your response before transitioning to general glucose patterns. If they ask about alternative medicine, myths, or home remedies (like curing diabetes by drinking warm water), clearly debunk it with scientific facts while maintaining a supportive clinical tone (e.g. explain that drinking warm water cannot cure diabetes, but drinking water generally supports hydration).
- Do not diagnose. Do not mention or reveal "tool context". Do not copy raw data.
- Use short, clear sentences. Give 3-5 practical bullets.

- **Diet & Meal Support**: If the user asks "what should I eat", "what's my meal plan", "recipe", "food", or about meals, you MUST recommend the meal from their personalized care plan matching the current time of day. Remind them of preferred foods and foods to limit.

User question: {user_message}

Patient summary:
- Age: {profile.get("age", "unknown")}
- BMI: {profile.get("bmi", "unknown")}
- {risk_source}: {risk.get("risk_level", "unknown")} via {risk.get("model_version", "unknown")}
- Bayesian risk posterior: {bayesian.get("posterior_mean", "unknown")}
- {trend_source}: {trend.get("trend_label", "unknown")} via {trend.get("model_version", "unknown")}
- Recent average glucose: {summary["avg_glucose"] if summary["avg_glucose"] is not None else "unknown"} mg/dL
- Recent logs loaded: {summary["log_count"]}
- Forecast context: {forecast_text}
- Diet Care Plan & Time: {care_plan_text}
- Guidance: {guidance or "Keep logging consistently and contact a clinician for medical decisions."}
- Learned tone: {learning.get("preferred_tone", "balanced")}
- Learned focus: {learning.get("preferred_action_type", "monitoring")}
- Adaptive next action: {next_action.get("title", "Keep glucose logging consistent")}

Answer:"""


def _build_gemini_prompt(messages: list[dict], tools_context: dict) -> str:
    user_message = next((item["content"] for item in reversed(messages) if item.get("role") == "user"), "")
    target_language = language_name(detect_language(user_message))
    summary = _patient_summary(tools_context)
    profile = summary["profile"]
    risk = summary["risk"]
    bayesian = summary["bayesian"]
    trend = summary["trend"]
    risk_source = "trained RF risk model" if risk.get("model_version") == "random-forest-0.2" else "risk fallback scorer"
    trend_source = "trained glucose trend model" if trend.get("model_version") == "glucose-trend-random-forest-0.2" else "monitoring fallback scorer"
    top_factors = risk.get("top_factors") or []
    related_flags = risk.get("related_flags") or []
    anomaly_flags = trend.get("anomaly_flags") or []
    guidelines = summary["guidelines"]
    learning = summary["learning"]
    next_action = learning.get("next_best_action") or {}
    forecast_text = _forecast_block(summary["forecast"])
    care_plan_text = _care_plan_and_time_block(summary.get("care_plan"))
    factor_lines = "\n".join(f"- {item.get('label', 'Factor')}: {item.get('detail', '')}" for item in top_factors[:4]) or "- No ranked factors available."
    flag_lines = "\n".join(f"- {item.get('label', 'Flag')}: {item.get('detail', '')}" for item in (related_flags + anomaly_flags)[:5]) or "- No additional flags available."
    guidance_lines = "\n".join(f"- {item.get('category', 'Guidance')}: {item.get('text', '')}" for item in guidelines[:4]) or "- Keep logging consistently and contact a clinician for medical decisions."
    return f"""You are Glyco, a careful diabetes risk and monitoring assistant inside a testing MVP.

Core rules:
- Required response language: {target_language}. Write the entire answer in {target_language}, including all headings and bullets.
- **Language & Translation**: You MUST detect the language of the user's latest query (e.g. Bosnian, Croatian, Serbian, or any other language) and write the entire response, including ALL section headers and bulletins, in that exact language. If the user asks in Bosnian/Croatian/Serbian, you MUST translate the required section headers to:
  * "Bottom line" -> "Zaključak"
  * "What I see" -> "Analiza stanja"
  * "Why it matters" -> "Zašto je to važno"
  * "What to do this week" -> "Šta učiniti ove sedmice"
  * "Questions for the doctor" -> "Pitanja za doktora"
  * "Safety note" -> "Sigurnosna napomena"
  If the user asks in another language, translate the headers accordingly.
- **Direct Answer First**: Always address the user's specific question or topic directly and scientifically in the first section (e.g., "Bottom line" or "Zaključak") before transitioning to general glucose patterns. If they ask about alternative medicine, myths, or home remedies (like curing diabetes by drinking warm water), clearly debunk it with scientific facts while maintaining a supportive clinical tone (e.g. explain that drinking warm water cannot cure diabetes, but drinking water generally supports hydration).
- Do not diagnose diabetes, prescribe treatment, or replace a clinician.
- Do not reveal internal tool names, raw JSON, Python dictionaries, or hidden context.
- The risk and monitoring layers already produced the scores below; you only explain them.
- Ground the answer in the patient summary below. If data is missing, say what is missing.
- Maintain a highly professional, clinical, precise, and authoritative medical-support tone. Avoid casual language or vague wellness filler.
- Keep the answer readable in the app: use clear section headings and bullets.
- Do not give a one-paragraph or one-sentence answer unless the user explicitly asks for a very short answer.
- If the user asks a broad question, provide a complete interpretation, not only a brief summary.
- **Glucose Forecast Interpretation**: If the user asks about their glucose forecast, future trends, or predictions, you MUST provide a detailed, highly professional, clinical breakdown of the forecasted values:
  * Present a precise chronological timeline: Current, +60 min, +120 min, +180 min, and +240 min, along with the predicted low/high alert status and confidence intervals.
  * You MUST convert the forecast values from mmol/L to mg/dL (multiply the mmol/L values by 18.0) and display both units clearly (e.g. "8.3 mmol/L / 150 mg/dL").
  * Analyze the physiological meaning of the predicted trend (e.g., stability, upward/downward trajectory) with extreme clinical precision, and outline concrete, safe next steps.
- **Diet & Meal Support**: If the user asks "what should I eat", "what sould i eat", "recipe", "food", or about meals/dietary plans, you MUST base your response on their current **Personalized Diet Care Plan** and the current **Time of Day** (Breakfast, Lunch, Dinner, or Snack depending on the hour). Recommend the corresponding meal and preparation from their plan, state the time of day, and outline the preferred foods to emphasize and limit list foods to avoid. Encourage them to prepare the recipe.

User question:
{user_message}

Patient summary:
- Age: {profile.get("age", "unknown")}
- Sex: {profile.get("sex", "unknown")}
- BMI: {profile.get("bmi", "unknown")}
- High blood pressure: {profile.get("high_bp", "unknown")}
- High cholesterol: {profile.get("high_chol", "unknown")}
- Physical activity marked active: {profile.get("phys_activity", "unknown")}
- General health rating: {profile.get("general_health", "unknown")}
- Risk source: {risk_source}
- Risk source version: {risk.get("model_version", "unknown")}
- RF risk level: {risk.get("risk_level", "unknown")}
- Risk probability: {risk.get("risk_probability", "unknown")}
- Bayesian posterior risk mean: {bayesian.get("posterior_mean", "unknown")}
- Bayesian credible interval: {(bayesian.get("credible_interval") or {}).get("low", "unknown")}-{(bayesian.get("credible_interval") or {}).get("high", "unknown")}
- Monitoring source: {trend_source}
- Monitoring source version: {trend.get("model_version", "unknown")}
- Glucose trend label: {trend.get("trend_label", "unknown")}
- Trend score: {trend.get("trend_score", "unknown")}
- Recent log count: {summary["log_count"]}
- Average glucose: {summary["avg_glucose"] if summary["avg_glucose"] is not None else "unknown"} mg/dL
- Glucose range: {summary["min_glucose"] if summary["min_glucose"] is not None else "unknown"}-{summary["max_glucose"] if summary["max_glucose"] is not None else "unknown"} mg/dL
- Latest glucose: {summary["latest_glucose"] if summary["latest_glucose"] is not None else "unknown"} mg/dL
- Fasting readings: {summary["fasting_count"]}
- Not-fasting readings: {summary["non_fasting_count"]}
- Latest log: {summary["latest_log"] or "none"}
- Learned tone preference: {learning.get("preferred_tone", "balanced")}
- Learned action focus: {learning.get("preferred_action_type", "monitoring")}
- Recent adaptive glucose pattern: {(learning.get("recent_glucose_pattern") or {}).get("label", "unknown")}
- Adaptive next action: {next_action.get("title", "Keep glucose logging consistent")} - {next_action.get("body", "")}

{forecast_text}

{care_plan_text}

Top factors:
{factor_lines}

Flags and trend notes:
{flag_lines}

Curated guidance:
{guidance_lines}

Write the response with exactly these sections:

Bottom line
- Give a direct answer in 1-2 sentences.

What I see
- Include 3-5 bullets.
- Mention the risk level, monitoring trend, glucose pattern, and at least one relevant factor or flag.
- Explicitly say whether the risk and trend results came from trained models or fallback scorers.
- Explain that the Bayesian layer smooths risk over time.

Why it matters
- Include 2-4 bullets.
- Explain the practical meaning of the readings without diagnosing.

What to do this week
- Include 4-6 concrete, low-risk actions.
- Make the actions specific enough that the patient or family could do them today.
- Include the adaptive next action unless it conflicts with safety or the user's question.

Questions for the doctor
- Include 2-4 useful questions to bring to a clinician.

Safety note
- End with one brief sentence that Glyco supports preparation and does not replace medical care.

If the user asks about family support, add a "How family can help" section before "Questions for the doctor" with 3-5 concrete actions.
Target length: 240-380 words. Complete every section. End with a full sentence."""


def build_rich_system_prompt(tools_context: dict, language: str = "en") -> str:
    """Build the rich clinical system prompt with an explicit response language."""
    summary = _patient_summary(tools_context)
    profile = summary["profile"]
    risk = summary["risk"]
    bayesian = summary["bayesian"]
    trend = summary["trend"]
    risk_source = "trained RF risk model" if risk.get("model_version") == "random-forest-0.2" else "risk fallback scorer"
    trend_source = "trained glucose trend model" if trend.get("model_version") == "glucose-trend-random-forest-0.2" else "monitoring fallback scorer"
    top_factors = risk.get("top_factors") or []
    related_flags = risk.get("related_flags") or []
    anomaly_flags = trend.get("anomaly_flags") or []
    guidelines = summary["guidelines"]
    learning = summary["learning"]
    next_action = learning.get("next_best_action") or {}
    forecast_text = _forecast_block(summary["forecast"])
    care_plan_text = _care_plan_and_time_block(summary.get("care_plan"))
    factor_lines = "\n".join(f"- {item.get('label', 'Factor')}: {item.get('detail', '')}" for item in top_factors[:4]) or "- No ranked factors available."
    flag_lines = "\n".join(f"- {item.get('label', 'Flag')}: {item.get('detail', '')}" for item in (related_flags + anomaly_flags)[:5]) or "- No additional flags available."
    guidance_lines = "\n".join(f"- {item.get('category', 'Guidance')}: {item.get('text', '')}" for item in guidelines[:4]) or "- Keep logging consistently and contact a clinician for medical decisions."

    # Format the detailed logs block including all fields
    logs = tools_context.get("logs") or []
    logs_lines = []
    for log in logs:
        log_str = (
            f"- Date: {log.get('date')}, Glucose: {log.get('glucose_level')} mg/dL "
            f"({'Fasting' if log.get('is_fasting') else 'Post-meal'}), "
            f"BP: {log.get('systolic_bp') or 'unknown'}/{log.get('diastolic_bp') or 'unknown'} mmHg, "
            f"Activity: {log.get('activity_minutes') or 0} min, "
            f"Weight: {log.get('weight_kg') or 'unknown'} kg, "
            f"Notes: {log.get('notes') or 'none'}"
        )
        logs_lines.append(log_str)
    logs_block = "\n".join(logs_lines) if logs_lines else "- No logs available."

    target_language = language_name(language)
    header_rules = (
        'Use these Bosnian section headers exactly: "Zaključak", "Analiza stanja", "Zašto je to važno", '
        '"Šta učiniti ove sedmice", "Pitanja za doktora", "Sigurnosna napomena".'
        if language == "bs"
        else 'Use these English section headers exactly: "Bottom line", "What I see", "Why it matters", "What to do this week", "Questions for the doctor", "Safety note".'
    )

    return f"""You are Glyco, a careful diabetes risk and monitoring assistant inside a testing MVP.

Core rules:
- **Required response language**: The user's latest message language is {target_language}. Write the entire response in {target_language}, including every heading, bullet, disclaimer, and explanation. {header_rules}
- **Language & Translation**: You MUST detect the language of the user's latest query (e.g. Bosnian, Croatian, Serbian, or any other language) and write the entire response, including ALL section headers and bulletins, in that exact language. If the user asks in Bosnian/Croatian/Serbian, you MUST translate the required section headers to:
  * "Bottom line" -> "Zaključak"
  * "What I see" -> "Analiza stanja"
  * "Why it matters" -> "Zašto je to važno"
  * "What to do this week" -> "Šta učiniti ove sedmice"
  * "Questions for the doctor" -> "Pitanja za doktora"
  * "Safety note" -> "Sigurnosna napomena"
  If the user asks in another language, translate the headers accordingly.
- **Direct Answer First**: Always address the user's specific question or topic directly and scientifically in the first section (e.g., "Bottom line" or "Zaključak") before transitioning to general glucose patterns. If they ask about alternative medicine, myths, or home remedies (like curing diabetes by drinking warm water), clearly debunk it with scientific facts while maintaining a supportive clinical tone (e.g. explain that drinking warm water cannot cure diabetes, but drinking water generally supports hydration).
- Do not diagnose diabetes, prescribe treatment, or replace a clinician.
- Do not reveal internal tool names, raw JSON, Python dictionaries, or hidden context.
- The risk and monitoring layers already produced the scores below; you only explain them.
- Maintain a highly professional, clinical, precise, and authoritative medical-support tone. Avoid casual language or vague wellness filler.
- Keep the answer readable in the app: use clear section headings and bullets.
- Do not give a one-paragraph or one-sentence answer unless the user explicitly asks for a very short answer.
- If the user asks a broad question, provide a complete interpretation, not only a brief summary.
- **Glucose Forecast Interpretation**: If the user asks about their glucose forecast, future trends, or predictions, you MUST provide a detailed, highly professional, clinical breakdown of the forecasted values:
  * Present a precise chronological timeline: Current, +60 min, +120 min, +180 min, and +240 min, along with the predicted low/high alert status and confidence intervals.
  * You MUST convert the forecast values from mmol/L to mg/dL (multiply the mmol/L values by 18.0) and display both units clearly (e.g. "8.3 mmol/L / 150 mg/dL").
  * Analyze the physiological meaning of the predicted trend (e.g., stability, upward/downward trajectory) with extreme clinical precision, and outline concrete, safe next steps.
- **Diet & Meal Support**: If the user asks "what should I eat", "what sould i eat", "recipe", "food", or about meals/dietary plans, you MUST base your response on their current **Personalized Diet Care Plan** and the current **Time of Day** (Breakfast, Lunch, Dinner, or Snack depending on the hour). Recommend the corresponding meal and preparation from their plan, state the time of day, and outline the preferred foods to emphasize and limit list foods to avoid. Encourage them to prepare the recipe.

Patient summary:
- Age: {profile.get("age", "unknown")}
- Sex: {profile.get("sex", "unknown")}
- Height: {profile.get("height_cm", "unknown")} cm
- Weight: {profile.get("weight_kg", "unknown")} kg
- BMI: {profile.get("bmi", "unknown")}
- High blood pressure: {profile.get("high_bp", "unknown")}
- High cholesterol: {profile.get("high_chol", "unknown")}
- Smoker: {profile.get("smoker", "unknown")}
- Physical activity marked active: {profile.get("phys_activity", "unknown")}
- Fruits consumption: {profile.get("fruits", "unknown")}
- Veggies consumption: {profile.get("veggies", "unknown")}
- General health rating: {profile.get("general_health", "unknown")}
- Stroke history: {profile.get("stroke_history", "unknown")}
- Heart disease history: {profile.get("heart_disease_history", "unknown")}
- Difficulty walking: {profile.get("difficulty_walking", "unknown")}
- Family history of diabetes: {profile.get("family_history_diabetes", "unknown")}
- Risk source: {risk_source}
- Risk source version: {risk.get("model_version", "unknown")}
- RF risk level: {risk.get("risk_level", "unknown")}
- Risk probability: {risk.get("risk_probability", "unknown")}
- Bayesian posterior risk mean: {bayesian.get("posterior_mean", "unknown")}
- Bayesian credible interval: {(bayesian.get("credible_interval") or {}).get("low", "unknown")}-{(bayesian.get("credible_interval") or {}).get("high", "unknown")}
- Monitoring source: {trend_source}
- Monitoring source version: {trend.get("model_version", "unknown")}
- Glucose trend label: {trend.get("trend_label", "unknown")}
- Trend score: {trend.get("trend_score", "unknown")}
- Recent log count: {summary["log_count"]}
- Average glucose: {summary["avg_glucose"] if summary["avg_glucose"] is not None else "unknown"} mg/dL
- Glucose range: {summary["min_glucose"] if summary["min_glucose"] is not None else "unknown"}-{summary["max_glucose"] if summary["max_glucose"] is not None else "unknown"} mg/dL
- Latest glucose: {summary["latest_glucose"] if summary["latest_glucose"] is not None else "unknown"} mg/dL
- Fasting readings: {summary["fasting_count"]}
- Not-fasting readings: {summary["non_fasting_count"]}
- Latest log: {summary["latest_log"] or "none"}
- Learned tone preference: {learning.get("preferred_tone", "balanced")}
- Learned action focus: {learning.get("preferred_action_type", "monitoring")}
- Recent adaptive glucose pattern: {(learning.get("recent_glucose_pattern") or {}).get("label", "unknown")}
- Adaptive next action: {next_action.get("title", "Keep glucose logging consistent")} - {next_action.get("body", "")}

{forecast_text}

{care_plan_text}

Patient Recent Glucose and Lifestyle Logs (past 7 days):
{logs_block}

Top factors:
{factor_lines}

Flags and trend notes:
{flag_lines}

Curated guidance:
{guidance_lines}

Write the response with exactly these sections in {target_language}:

Bottom line
- Give a direct answer in 1-2 sentences.

What I see
- Include 3-5 bullets.
- Mention the risk level, monitoring trend, glucose pattern, and at least one relevant factor or flag.
- Explicitly say whether the risk and trend results came from trained models or fallback scorers.
- Explain that the Bayesian layer smooths risk over time.

Why it matters
- Include 2-4 bullets.
- Explain the practical meaning of the readings without diagnosing.

What to do this week
- Include 4-6 concrete, low-risk actions.
- Make the actions specific enough that the patient or family could do them today.
- Include the adaptive next action unless it conflicts with safety or the user's question.

Questions for the doctor
- Include 2-4 useful questions to bring to a clinician.

Safety note
- End with one brief sentence that Glyco supports preparation and does not replace medical care.

If the user asks about family support, add a "How family can help" section before "Questions for the doctor" with 3-5 concrete actions.
Target length: 240-380 words. Complete every section. End with a full sentence."""



def _is_probably_incomplete(answer: str, finish_reason: str | None = None) -> bool:
    if finish_reason in {"MAX_TOKENS", "RECITATION"}:
        return True
    stripped = answer.rstrip()
    if not stripped:
        return True
    return stripped[-1] not in {".", "!", "?", ")", "]"}


class GeminiClient:
    def __init__(self) -> None:
        self.provider_name = "gemini"
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GLYCO_GEMINI_API_KEY", "")
        self.model = os.getenv("GLYCO_GEMINI_MODEL", "gemini-2.5-flash")
        self.model_name = self.model
        self.base_url = os.getenv("GLYCO_GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta")
        self.timeout = float(os.getenv("GLYCO_GEMINI_TIMEOUT_SECONDS", "45"))
        self.max_output_tokens = int(os.getenv("GLYCO_GEMINI_MAX_OUTPUT_TOKENS", "1800"))

    def _post_generate(self, prompt: str, max_output_tokens: int | None = None) -> tuple[str | None, str | None]:
        response = httpx.post(
            f"{self.base_url}/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.25,
                    "topP": 0.85,
                    "maxOutputTokens": max_output_tokens or self.max_output_tokens,
                },
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        candidate = payload.get("candidates", [{}])[0]
        parts = candidate.get("content", {}).get("parts", [])
        answer = "".join(part.get("text", "") for part in parts).strip()
        return (answer or None), candidate.get("finishReason")

    def generate(self, messages: list[dict], tools_context: dict) -> str | None:
        if not llm_network_enabled():
            return None
        if gemini_is_rate_limited():
            logger.warning("Gemini generation skipped: rate-limit cooldown is active")
            return None
        if not self.api_key:
            logger.warning("Gemini generation skipped: GEMINI_API_KEY is not set")
            return None
        prompt = _build_gemini_prompt(messages, tools_context)
        try:
            answer, finish_reason = self._post_generate(prompt)
            if answer and not _is_probably_incomplete(answer, finish_reason):
                return answer
            logger.warning("Gemini answer looked incomplete; finish_reason=%s", finish_reason)
            repair_prompt = f"""{prompt}

The previous answer was cut off. Rewrite the answer from scratch.
Keep it complete, concise, and formatted with the required section headings.
Target 220-320 words. End with the Safety note as a complete sentence."""
            repaired_answer, repaired_finish_reason = self._post_generate(repair_prompt, max_output_tokens=1200)
            if repaired_answer and not _is_probably_incomplete(repaired_answer, repaired_finish_reason):
                return repaired_answer
            return repaired_answer
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                note_gemini_rate_limit()
            logger.warning("Gemini generation failed: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Gemini generation failed: %s", exc)
            return None


class OllamaClient:
    def __init__(self) -> None:
        self.provider_name = "ollama"
        self.base_url = os.getenv("GLYCO_OLLAMA_URL", "http://127.0.0.1:11434")
        self.model = os.getenv("GLYCO_OLLAMA_MODEL", "llama3.2:1b")
        self.model_name = self.model
        self.timeout = float(os.getenv("GLYCO_OLLAMA_TIMEOUT_SECONDS", "120"))

    def generate(self, messages: list[dict], tools_context: dict) -> str | None:
        if not llm_network_enabled():
            return None
        prompt = _build_concise_prompt(messages, tools_context)
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "top_p": 0.7, "num_predict": 220},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            answer = payload.get("response")
            return answer.strip() if isinstance(answer, str) and answer.strip() else None
        except Exception as exc:
            logger.warning("Ollama generation failed: %s", exc)
            return None


class ChainedLLMClient:
    def __init__(self, clients: list[LLMClient]) -> None:
        self.clients = clients
        self.provider_name = "fallback"
        self.model_name = "fallback"

    def generate(self, messages: list[dict], tools_context: dict) -> str | None:
        for client in self.clients:
            answer = client.generate(messages, tools_context)
            if answer:
                self.provider_name = getattr(client, "provider_name", "configured")
                self.model_name = getattr(client, "model_name", "configured")
                return answer
        return None


def _provider_order() -> list[str]:
    _load_env_files()
    provider = os.getenv("GLYCO_LLM_PROVIDER", "").lower()
    
    has_deepseek = bool(_first_env("DEEPSEEK_API_KEY", "GLYCO_DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "GLYCO_OPENROUTER_API_KEY"))
    has_gemini = bool(_first_env("GEMINI_API_KEY", "GLYCO_GEMINI_API_KEY"))
    has_groq = bool(_first_env("GROQ_API_KEY", "GLYCO_GROQ_API_KEY"))
    
    if provider == "groq":
        res = ["groq"]
        if has_deepseek:
            res.append("deepseek")
        if has_gemini:
            res.append("gemini")
        return res
        
    if provider == "deepseek":
        res = ["deepseek"]
        if has_groq:
            res.append("groq")
        if has_gemini:
            res.append("gemini")
        return res
        
    if provider in {"gemini", "google"}:
        res = ["gemini"]
        if has_groq:
            res.append("groq")
        if has_deepseek:
            res.append("deepseek")
        res.append("ollama")
        return res
        
    if provider == "ollama":
        return ["ollama"]
        
    # If provider is unset, determine based on available keys
    if has_groq:
        res = ["groq"]
        if has_deepseek:
            res.append("deepseek")
        if has_gemini:
            res.append("gemini")
        return res
        
    if has_deepseek:
        res = ["deepseek"]
        if has_gemini:
            res.append("gemini")
        return res
        
    if has_gemini:
        return ["gemini", "ollama"]
        
    return []


def get_llm_client() -> LLMClient:
    _load_env_files()
    clients: list[LLMClient] = []
    for provider in _provider_order():
        if provider == "deepseek":
            clients.append(DeepSeekClient())
        elif provider == "gemini":
            clients.append(GeminiClient())
        elif provider == "groq":
            clients.append(GroqClient())
        elif provider == "ollama":
            clients.append(OllamaClient())
    return ChainedLLMClient(clients) if clients else FallbackLLMClient()



def _get_deepseek_status() -> dict:
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("GLYCO_DEEPSEEK_API_KEY", "")
    return {
        "configured": bool(api_key),
        "model": os.getenv("GLYCO_DEEPSEEK_MODEL", "deepseek/deepseek-v4-flash:free"),
        "url": os.getenv("GLYCO_DEEPSEEK_URL", "https://openrouter.ai/api/v1"),
    }


def _get_gemini_status() -> dict:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GLYCO_GEMINI_API_KEY", "")
    return {
        "configured": bool(api_key),
        "model": os.getenv("GLYCO_GEMINI_MODEL", "gemini-2.5-flash"),
        "url": os.getenv("GLYCO_GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta"),
    }


def _get_groq_status() -> dict:
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("GLYCO_GROQ_API_KEY", "")
    return {
        "configured": bool(api_key),
        "model": os.getenv("GLYCO_GROQ_MODEL", "llama-3.3-70b-versatile"),
        "url": os.getenv("GLYCO_GROQ_URL", "https://api.groq.com/openai/v1"),
    }


def _get_ollama_status() -> dict:
    base_url = os.getenv("GLYCO_OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.getenv("GLYCO_OLLAMA_MODEL", "llama3.2:1b")
    status = {
        "configured": True,
        "url": base_url,
        "model": model,
        "reachable": False,
        "model_available": False,
        "models": [],
    }
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=10)
        response.raise_for_status()
        models = [item.get("name") for item in response.json().get("models", []) if item.get("name")]
        status.update({"reachable": True, "model_available": model in models, "models": models})
    except Exception as exc:
        status["error"] = str(exc)
    return status


def get_llm_status() -> dict:
    _load_env_files()
    provider_order = _provider_order()
    deepseek = _get_deepseek_status()
    gemini = _get_gemini_status()
    groq = _get_groq_status()
    ollama = _get_ollama_status() if "ollama" in provider_order else {
        "configured": False,
        "url": os.getenv("GLYCO_OLLAMA_URL", "http://127.0.0.1:11434"),
        "model": os.getenv("GLYCO_OLLAMA_MODEL", "llama3.2:1b"),
        "reachable": False,
        "model_available": False,
        "models": [],
    }
    active_provider = provider_order[0] if provider_order else "fallback"
    if active_provider == "deepseek":
        active_model = deepseek["model"]
        primary_configured = deepseek["configured"]
    elif active_provider == "gemini":
        active_model = gemini["model"]
        primary_configured = gemini["configured"]
    elif active_provider == "groq":
        active_model = groq["model"]
        primary_configured = groq["configured"]
    elif active_provider == "ollama":
        active_model = ollama["model"]
        primary_configured = ollama["configured"]
    else:
        active_model = "fallback"
        primary_configured = False

    fallback_available = "ollama" in provider_order and ollama["reachable"] and ollama["model_available"]
    return {
        "provider": active_provider,
        "provider_order": provider_order or ["fallback"],
        "model": active_model,
        "configured": bool(provider_order) and (primary_configured or fallback_available),
        "primary_configured": primary_configured,
        "fallback_available": fallback_available,
        "deepseek": deepseek,
        "gemini": gemini,
        "groq": groq,
        "ollama": ollama,
        # Backward-compatible fields for the current frontend.
        "ollama_url": ollama["url"],
        "ollama_model": ollama["model"],
        "reachable": ollama["reachable"],
        "model_available": ollama["model_available"],
        "models": ollama["models"],
    }

