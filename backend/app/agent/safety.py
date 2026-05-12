from __future__ import annotations

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


def safety_note() -> str:
    return "Glyco can help you interpret logged patterns and prepare questions, but it does not diagnose or replace a clinician."


def urgent_message_if_needed(message: str) -> str | None:
    # This boundary runs before generation so urgent symptoms bypass normal
    # coaching and produce a direct escalation message.
    lowered = message.lower()
    if any(term in lowered for term in URGENT_TERMS):
        return (
            "Your message includes symptoms that may require urgent medical attention. "
            "If symptoms are severe, sudden, or worsening, contact emergency services or a clinician immediately."
        )
    return None
