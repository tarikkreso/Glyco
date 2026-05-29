from __future__ import annotations

from app.agent.language import detect_language, localize_safety_note, localize_urgent_message

URGENT_TERMS = {
    "chest pain",
    "shortness of breath",
    "fainting",
    "confusion",
    "severe weakness",
    "unconscious",
    "emergency",
    "hitna",
    "bol u prsima",
    "otezano disanje",
}


def safety_note(language: str = "en") -> str:
    """Return the standard safety note localized for the active conversation."""
    return localize_safety_note(language)


def urgent_message_if_needed(message: str) -> str | None:
    """Return a localized urgent boundary message if the text contains red flags."""
    # This boundary runs before generation so urgent symptoms bypass normal
    # coaching and produce a direct escalation message.
    lowered = message.lower()
    if any(term in lowered for term in URGENT_TERMS):
        return localize_urgent_message(detect_language(message))
    return None
