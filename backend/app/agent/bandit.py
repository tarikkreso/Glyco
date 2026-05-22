from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from random import betavariate

from sqlalchemy.orm import Session

from app.db import models

RECOMMENDATION_ARMS = (
    "nutrition",
    "activity",
    "monitoring",
    "medication_check",
    "clinician_questions",
    "fasting_routine",
    "post_meal_review",
    "sleep_stress",
    "family_support",
)


@dataclass(frozen=True)
class Recommendation:
    """Recommendation candidate associated with a Thompson Sampling arm."""

    arm: str
    title: str
    body: str


class RecommendationBandit:
    """Thompson Sampling reranker for agent recommendation types."""

    def __init__(self, db: Session, user_id: int) -> None:
        """Bind the bandit to a database session and patient-specific arm state."""
        self.db = db
        self.user_id = user_id
        self._ensure_arms()

    # Creates missing arms lazily so existing SQLite files remain compatible.
    def _ensure_arms(self) -> None:
        """Ensure every supported recommendation arm has persisted Beta state."""
        existing = {
            row.arm_name
            for row in self.db.query(models.BanditArmState).filter(models.BanditArmState.user_id == self.user_id).all()
        }
        for arm in RECOMMENDATION_ARMS:
            if arm not in existing:
                self.db.add(models.BanditArmState(user_id=self.user_id, arm_name=arm, alpha=1.0, beta=1.0))
        self.db.commit()

    # Samples from each arm's posterior and returns candidates in descending
    # sampled value, which balances exploration and exploitation.
    def rerank(self, recommendations: list[dict], limit: int | None = None, forecast: dict | None = None) -> list[dict]:
        """Rank recommendations using Thompson Sampling draws from each arm."""
        states = {
            row.arm_name: row
            for row in self.db.query(models.BanditArmState).filter(models.BanditArmState.user_id == self.user_id).all()
        }
        alpha_boosts = {"monitoring": 0.0, "activity": 0.0}
        if forecast and forecast.get("predicted_low_alert"):
            # Forecast low alert increases monitoring recommendation priority via bandit arm boost.
            alpha_boosts["monitoring"] += 1.0
        if forecast and forecast.get("predicted_high_alert"):
            # Forecast high alert increases activity recommendation priority.
            alpha_boosts["activity"] += 1.0
        decorated: list[tuple[float, dict]] = []
        for item in recommendations:
            arm = str(item.get("type") or item.get("arm") or "monitoring")
            state = states.get(arm) or states["monitoring"]
            boosted_alpha = state.alpha + alpha_boosts.get(arm, 0.0)
            sampled_score = betavariate(boosted_alpha, state.beta)
            ranked = {**item, "type": arm, "bandit_score": sampled_score, "bandit_alpha": boosted_alpha, "bandit_beta": state.beta}
            decorated.append((sampled_score, ranked))
        decorated.sort(key=lambda pair: pair[0], reverse=True)
        ranked_items = [item for _, item in decorated]
        return ranked_items[:limit] if limit else ranked_items

    # Feedback updates the conjugate prior: positive signals add success mass,
    # negative signals add failure mass.
    def update_feedback(self, arm: str, positive: bool) -> models.BanditArmState:
        """Apply a positive or negative feedback event to a recommendation arm."""
        normalized = arm if arm in RECOMMENDATION_ARMS else "monitoring"
        row = (
            self.db.query(models.BanditArmState)
            .filter(models.BanditArmState.user_id == self.user_id, models.BanditArmState.arm_name == normalized)
            .first()
        )
        if row is None:
            row = models.BanditArmState(user_id=self.user_id, arm_name=normalized, alpha=1.0, beta=1.0)
            self.db.add(row)
            self.db.flush()
        if positive:
            row.alpha += 1.0
        else:
            row.beta += 1.0
        row.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(row)
        return row


# Provides a shared recommendation vocabulary for chat, insight, and reports.
def default_recommendations() -> list[dict]:
    """Return baseline recommendation candidates before bandit reranking."""
    return [
        {"type": "nutrition", "title": "Pair carbohydrates with protein or fiber", "body": "Review the largest carbohydrate meal and add a lower-glycemic swap this week."},
        {"type": "activity", "title": "Walk after the largest meal", "body": "Aim for 10 to 15 minutes of light movement after the meal most linked with higher readings."},
        {"type": "monitoring", "title": "Keep glucose logging consistent", "body": "Add the next glucose reading so Glyco can detect whether the pattern is improving."},
        {"type": "medication_check", "title": "Prepare medication questions", "body": "Ask the clinician whether the current monitoring pattern changes medication review timing."},
        {"type": "clinician_questions", "title": "Write down doctor questions", "body": "Bring one question about targets, one about timing, and one about when to contact the clinic."},
        {"type": "fasting_routine", "title": "Standardize fasting checks", "body": "Take fasting readings at a similar morning time so week-to-week comparisons are cleaner."},
        {"type": "post_meal_review", "title": "Review post-meal patterns", "body": "When a not-fasting value is higher, connect it to the previous meal timing and portion."},
        {"type": "sleep_stress", "title": "Note sleep and stress context", "body": "Add a short note when sleep, stress, illness, or schedule changes might explain a reading."},
        {"type": "family_support", "title": "Ask family for one practical support", "body": "Choose one small support task, such as logging reminders, walking company, or appointment prep."},
    ]
