from __future__ import annotations

GUIDELINE_SNIPPETS = [
    {
        "id": "risk-factors",
        "category": "Type 2 diabetes risk factors",
        "text": "Type 2 diabetes risk is commonly associated with higher BMI, family history, reduced physical activity, high blood pressure, abnormal cholesterol, and increasing age.",
    },
    {
        "id": "fasting-monitoring",
        "category": "Fasting glucose monitoring",
        "text": "Consistent fasting glucose logs are useful because they make week-to-week patterns easier to compare than isolated readings.",
    },
    {
        "id": "activity",
        "category": "Lifestyle/activity guidance",
        "text": "Light activity after meals, when appropriate for the person, can support glucose management and can be tracked as part of a weekly care routine.",
    },
    {
        "id": "clinician-contact",
        "category": "When to contact a clinician",
        "text": "Persistent elevated readings, rapidly worsening trends, symptoms, or uncertainty about medication or treatment should be discussed with a qualified clinician.",
    },
    {
        "id": "family-support",
        "category": "Family support guidance",
        "text": "Family members can help by supporting logging routines, appointment preparation, meal planning, walking reminders, and medication routines already prescribed by clinicians.",
    },
    {
        "id": "safety-disclaimer",
        "category": "Medical safety",
        "text": "Digital health tools can support awareness and preparation, but they should not diagnose disease or replace clinician judgment.",
    },
]


def retrieve_guidelines(query: str, limit: int = 3) -> list[dict]:
    terms = {term.strip(".,?!:;()[]").lower() for term in query.split() if len(term.strip(".,?!:;()[]")) > 2}
    scored = []
    for snippet in GUIDELINE_SNIPPETS:
        haystack = f"{snippet['category']} {snippet['text']}".lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, snippet))
    if not scored:
        scored = [(1, snippet) for snippet in GUIDELINE_SNIPPETS if snippet["id"] in {"safety-disclaimer", "clinician-contact", "fasting-monitoring"}]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [snippet for _, snippet in scored[:limit]]
