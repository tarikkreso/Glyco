from __future__ import annotations

import re


BOSNIAN_MARKERS = {
    "ako",
    "ali",
    "bol",
    "bosanski",
    "da li",
    "doktor",
    "glukoza",
    "hrana",
    "hvala",
    "kako",
    "korisnik",
    "liječnik",
    "mogu",
    "molim",
    "nivo",
    "odgovori",
    "pitanje",
    "pomoć",
    "šećer",
    "sta",
    "šta",
    "treba",
    "uputi",
    "zabrinut",
    "zdravlje",
}


def detect_language(text: str) -> str:
    """Detect whether a user message should be answered in Bosnian or English."""
    lowered = text.lower()
    if re.search(r"[čćđšž]", lowered):
        return "bs"
    marker_hits = sum(1 for marker in BOSNIAN_MARKERS if marker in lowered)
    return "bs" if marker_hits >= 2 else "en"


def language_name(code: str) -> str:
    """Return the natural-language name used inside LLM prompts."""
    return "Bosnian" if code == "bs" else "English"


def localize_safety_note(language: str) -> str:
    """Return the standard safety note in the requested language."""
    if language == "bs":
        return "Glyco može pomoći u tumačenju zabilježenih obrazaca i pripremi pitanja, ali ne postavlja dijagnozu i ne zamjenjuje ljekara."
    return "Glyco can help you interpret logged patterns and prepare questions, but it does not diagnose or replace a clinician."


def localize_urgent_message(language: str) -> str:
    """Return an urgent-care boundary message in the requested language."""
    if language == "bs":
        return (
            "Vaša poruka uključuje simptome koji mogu zahtijevati hitnu medicinsku pomoć. "
            "Ako su simptomi jaki, iznenadni ili se pogoršavaju, odmah kontaktirajte hitnu službu ili ljekara."
        )
    return (
        "Your message includes symptoms that may require urgent medical attention. "
        "If symptoms are severe, sudden, or worsening, contact emergency services or a clinician immediately."
    )


def localize_provider_error(language: str, detail: str, hint: str) -> str:
    """Return a chat provider error in the requested language."""
    if language == "bs":
        return f"Greška: Glyco chatbot trenutno ne može kontaktirati podešenog LLM provajdera.{detail} {hint}"
    return f"Error: Glyco chatbot couldn't reach the configured LLM provider.{detail} {hint}"
