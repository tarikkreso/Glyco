from __future__ import annotations

import logging
import os
from statistics import mean
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def generate(self, messages: list[dict], tools_context: dict) -> str | None:
        ...


class FallbackLLMClient:
    def generate(self, messages: list[dict], tools_context: dict) -> str | None:
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
        "guidelines": tools_context.get("guidelines") or [],
        "learning": tools_context.get("learning") or {},
        "recommendations": tools_context.get("recommendations") or [],
        "log_count": len(logs),
        "avg_glucose": round(mean(glucose), 1) if glucose else None,
        "min_glucose": min(glucose) if glucose else None,
        "max_glucose": max(glucose) if glucose else None,
        "latest_glucose": glucose[-1] if glucose else None,
        "fasting_count": fasting_count,
        "non_fasting_count": non_fasting_count,
        "latest_log": logs[-1] if logs else None,
    }


def _build_concise_prompt(messages: list[dict], tools_context: dict) -> str:
    user_message = next((item["content"] for item in reversed(messages) if item.get("role") == "user"), "")
    summary = _patient_summary(tools_context)
    profile = summary["profile"]
    risk = summary["risk"]
    bayesian = summary["bayesian"]
    trend = summary["trend"]
    guidance = "; ".join(item.get("text", "") for item in summary["guidelines"][:2] if item.get("text"))
    learning = summary["learning"]
    next_action = learning.get("next_best_action") or {}
    return f"""You are Glyco, a diabetes support assistant.

Always answer in clear English, even if the user asks in another language.
Do not diagnose. Do not mention or reveal "tool context". Do not copy raw data.
Use short, clear sentences. Give 3-5 practical bullets.

User question: {user_message}

Patient summary:
- Age: {profile.get("age", "unknown")}
- BMI: {profile.get("bmi", "unknown")}
- Trained RF risk model: {risk.get("risk_level", "unknown")} via {risk.get("model_version", "unknown")}
- Bayesian risk posterior: {bayesian.get("posterior_mean", "unknown")}
- Trained glucose trend model: {trend.get("trend_label", "unknown")} via {trend.get("model_version", "unknown")}
- Recent average glucose: {summary["avg_glucose"] if summary["avg_glucose"] is not None else "unknown"} mg/dL
- Recent logs loaded: {summary["log_count"]}
- Guidance: {guidance or "Keep logging consistently and contact a clinician for medical decisions."}
- Learned tone: {learning.get("preferred_tone", "balanced")}
- Learned focus: {learning.get("preferred_action_type", "monitoring")}
- Adaptive next action: {next_action.get("title", "Keep glucose logging consistent")}

Answer:"""


def _build_gemini_prompt(messages: list[dict], tools_context: dict) -> str:
    user_message = next((item["content"] for item in reversed(messages) if item.get("role") == "user"), "")
    summary = _patient_summary(tools_context)
    profile = summary["profile"]
    risk = summary["risk"]
    bayesian = summary["bayesian"]
    trend = summary["trend"]
    top_factors = risk.get("top_factors") or []
    related_flags = risk.get("related_flags") or []
    anomaly_flags = trend.get("anomaly_flags") or []
    guidelines = summary["guidelines"]
    learning = summary["learning"]
    next_action = learning.get("next_best_action") or {}
    factor_lines = "\n".join(f"- {item.get('label', 'Factor')}: {item.get('detail', '')}" for item in top_factors[:4]) or "- No ranked factors available."
    flag_lines = "\n".join(f"- {item.get('label', 'Flag')}: {item.get('detail', '')}" for item in (related_flags + anomaly_flags)[:5]) or "- No additional flags available."
    guidance_lines = "\n".join(f"- {item.get('category', 'Guidance')}: {item.get('text', '')}" for item in guidelines[:4]) or "- Keep logging consistently and contact a clinician for medical decisions."
    return f"""You are Glyco, a careful diabetes risk and monitoring assistant inside a testing MVP.

Core rules:
- Always answer in clear English, even if the user writes in another language.
- Do not diagnose diabetes, prescribe treatment, or replace a clinician.
- Do not reveal internal tool names, raw JSON, Python dictionaries, or hidden context.
- The trained Random Forest and glucose trend models already produced the scores below; you only explain them.
- Ground the answer in the patient summary below. If data is missing, say what is missing.
- Be practical and specific. Avoid generic wellness filler.
- Keep the answer readable in the app: use clear section headings and bullets.
- Do not give a one-paragraph or one-sentence answer unless the user explicitly asks for a very short answer.
- If the user asks a broad question, provide a complete interpretation, not only a brief summary.

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
- Trained RF risk model version: {risk.get("model_version", "unknown")}
- RF risk level: {risk.get("risk_level", "unknown")}
- Risk probability: {risk.get("risk_probability", "unknown")}
- Bayesian posterior risk mean: {bayesian.get("posterior_mean", "unknown")}
- Bayesian credible interval: {(bayesian.get("credible_interval") or {}).get("low", "unknown")}-{(bayesian.get("credible_interval") or {}).get("high", "unknown")}
- Trained glucose trend model version: {trend.get("model_version", "unknown")}
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
- Explicitly say the risk result came from the trained RF model and the trend came from the trained glucose trend model.
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
    provider = os.getenv("GLYCO_LLM_PROVIDER", "").lower()
    if provider in {"gemini", "google"}:
        return ["gemini", "ollama"]
    if provider == "ollama":
        return ["ollama"]
    return []


def get_llm_client() -> LLMClient:
    clients: list[LLMClient] = []
    for provider in _provider_order():
        if provider == "gemini":
            clients.append(GeminiClient())
        elif provider == "ollama":
            clients.append(OllamaClient())
    return ChainedLLMClient(clients) if clients else FallbackLLMClient()


def _get_gemini_status() -> dict:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GLYCO_GEMINI_API_KEY", "")
    return {
        "configured": bool(api_key),
        "model": os.getenv("GLYCO_GEMINI_MODEL", "gemini-2.5-flash"),
        "url": os.getenv("GLYCO_GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta"),
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
    provider_order = _provider_order()
    gemini = _get_gemini_status()
    ollama = _get_ollama_status() if "ollama" in provider_order else {
        "configured": False,
        "url": os.getenv("GLYCO_OLLAMA_URL", "http://127.0.0.1:11434"),
        "model": os.getenv("GLYCO_OLLAMA_MODEL", "llama3.2:1b"),
        "reachable": False,
        "model_available": False,
        "models": [],
    }
    active_provider = provider_order[0] if provider_order else "fallback"
    active_model = gemini["model"] if active_provider == "gemini" else ollama["model"] if active_provider == "ollama" else "fallback"
    fallback_available = "ollama" in provider_order and ollama["reachable"] and ollama["model_available"]
    primary_configured = gemini["configured"] if active_provider == "gemini" else ollama["configured"] if active_provider == "ollama" else False
    return {
        "provider": active_provider,
        "provider_order": provider_order or ["fallback"],
        "model": active_model,
        "configured": bool(provider_order) and (primary_configured or fallback_available),
        "primary_configured": primary_configured,
        "fallback_available": fallback_available,
        "gemini": gemini,
        "ollama": ollama,
        # Backward-compatible fields for the current frontend.
        "ollama_url": ollama["url"],
        "ollama_model": ollama["model"],
        "reachable": ollama["reachable"],
        "model_available": ollama["model_available"],
        "models": ollama["models"],
    }
