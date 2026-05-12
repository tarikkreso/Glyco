from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from random import betavariate

from sqlalchemy.orm import Session

from app.db import models

RECOMMENDATION_ARMS = ("nutrition", "activity", "monitoring", "medication_check")


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
    def rerank(self, recommendations: list[dict], limit: int | None = None) -> list[dict]:
        """Rank recommendations using Thompson Sampling draws from each arm."""
        states = {
            row.arm_name: row
            for row in self.db.query(models.BanditArmState).filter(models.BanditArmState.user_id == self.user_id).all()
        }
        decorated: list[tuple[float, dict]] = []
        for item in recommendations:
            arm = str(item.get("type") or item.get("arm") or "monitoring")
            state = states.get(arm) or states["monitoring"]
            sampled_score = betavariate(state.alpha, state.beta)
            ranked = {**item, "type": arm, "bandit_score": sampled_score, "bandit_alpha": state.alpha, "bandit_beta": state.beta}
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
        {"type": "monitoring", "title": "Keep fasting glucose logging consistent", "body": "Add the next fasting reading so Glyco can detect whether the pattern is improving."},
        {"type": "medication_check", "title": "Prepare medication questions", "body": "Ask the clinician whether the current monitoring pattern changes medication review timing."},
    ]
