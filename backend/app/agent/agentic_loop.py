from __future__ import annotations

import logging
import json
import os
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.agent.llm_client import gemini_is_rate_limited, note_gemini_rate_limit
from app.agent.language import detect_language, language_name
from app.agent.tool_registry import context_from_tool_results, execute_agent_tool, gemini_tool_declarations

logger = logging.getLogger(__name__)


def _gemini_configured() -> bool:
    provider = os.getenv("GLYCO_LLM_PROVIDER", "").lower()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GLYCO_GEMINI_API_KEY", "")
    return provider in {"gemini", "google"} and bool(api_key)


def _system_prompt(user_message: str) -> str:
    target_language = language_name(detect_language(user_message))
    return f"""You are Glyco, a real tool-calling diabetes support agent.

You must use tools before answering. Do not answer from memory alone.
The backend binds tools to the current user; never ask for or invent a user id.

Choose tools based on the user's question. For broad questions such as "Should I worry this week?", "What changed?", "What should I do next?", or family/doctor preparation, use the full clinical context: profile, logs, risk, Bayesian state, trend, guidelines, learning memory, and Thompson-ranked recommendations. For narrower questions, call only the tools needed to answer safely.

Safety rules:
- Required response language: {target_language}. Write the whole final answer in {target_language}.
- Answer in the same language as the user's latest message. If the language is unclear, use clear English.
- Do not diagnose diabetes.
- Do not prescribe treatment or medication changes.
- Tell the user to contact a qualified clinician for medical decisions.
- If data is missing, say what is missing.
- Do not reveal raw JSON or internal implementation details.
- You have access to a glucose forecasting tool that predicts the user's glucose levels up to 4 hours ahead based on their recent readings and a LightGBM model trained on real Type 2 diabetes CGM data. Always clarify that forecasts are estimates.

Final answer requirements:
- Answer the user's actual question.
- Mention what the active risk source and monitoring source found.
- Mention the Bayesian posterior in plain language.
- Use the Thompson-ranked recommendation as the next best action unless safety overrides it.
- Keep it concise and practical.

User question: {user_message}"""


def _extract_parts(payload: dict) -> tuple[list[dict], str | None]:
    candidate = (payload.get("candidates") or [{}])[0]
    content = candidate.get("content") or {}
    return content.get("parts") or [], candidate.get("finishReason")


def _part_text(parts: list[dict]) -> str | None:
    text = "".join(part.get("text", "") for part in parts if isinstance(part.get("text"), str)).strip()
    return text or None


def _function_calls(parts: list[dict]) -> list[dict]:
    calls = []
    for part in parts:
        call = part.get("functionCall")
        if isinstance(call, dict) and call.get("name"):
            calls.append({"name": call["name"], "args": call.get("args") or {}})
    return calls


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def run_gemini_agentic_chat(db: Session, user_id: int, user_message: str) -> dict | None:
    """Run a Gemini function-calling loop where the model chooses and receives tools."""
    if not _gemini_configured() or gemini_is_rate_limited():
        return None

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GLYCO_GEMINI_API_KEY", "")
    model = os.getenv("GLYCO_GEMINI_MODEL", "gemini-2.5-flash")
    base_url = os.getenv("GLYCO_GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta")
    timeout = float(os.getenv("GLYCO_GEMINI_TIMEOUT_SECONDS", "45"))
    max_output_tokens = int(os.getenv("GLYCO_GEMINI_MAX_OUTPUT_TOKENS", "1800"))

    contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": _system_prompt(user_message)}]}]
    tool_results: dict[str, Any] = {}
    tool_calls: list[dict] = []

    for _ in range(8):
        try:
            response = httpx.post(
                f"{base_url}/models/{model}:generateContent",
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json={
                    "contents": contents,
                    "tools": [{"functionDeclarations": gemini_tool_declarations()}],
                    "generationConfig": {
                        "temperature": 0.2,
                        "topP": 0.85,
                        "maxOutputTokens": max_output_tokens,
                    },
                },
                timeout=timeout,
            )
            response.raise_for_status()
            parts, finish_reason = _extract_parts(response.json())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                note_gemini_rate_limit()
            logger.warning("Gemini agentic loop failed: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Gemini agentic loop failed: %s", exc)
            return None

        calls = _function_calls(parts)
        if not calls:
            answer = _part_text(parts)
            if not answer:
                return None
            context = context_from_tool_results(tool_results)
            if not tool_results:
                logger.warning("Gemini answered before calling any tools; finish_reason=%s", finish_reason)
                return None
            return {
                "answer": answer,
                "tool_calls": tool_calls,
                "context": context,
                "llm_mode": "gemini-agentic",
                "llm_model": model,
            }

        contents.append({"role": "model", "parts": parts})
        response_parts = []
        for call in calls:
            result, visible_call = execute_agent_tool(db, user_id, call["name"], call.get("args"), user_message)
            tool_results[call["name"]] = result
            tool_calls.append(visible_call)
            response_parts.append({"functionResponse": {"name": call["name"], "response": {"result": _json_safe(result)}}})
        contents.append({"role": "user", "parts": response_parts})

    logger.warning("Gemini agentic loop reached max tool iterations without final answer")
    return None
