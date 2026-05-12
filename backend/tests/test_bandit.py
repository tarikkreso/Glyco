import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.agent.bandit import RecommendationBandit, default_recommendations
from app.db import models
from app.db.database import SessionLocal


def test_thompson_sampling_returns_valid_arm() -> None:
    """Bandit reranking returns known recommendation arms."""
    db = SessionLocal()
    user = models.User(full_name="Bandit Test", email_or_demo_id="bandit-test")
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        ranked = RecommendationBandit(db, user.id).rerank(default_recommendations(), limit=1)
        assert ranked[0]["type"] in {"nutrition", "activity", "monitoring", "medication_check"}
    finally:
        db.query(models.BanditArmState).filter(models.BanditArmState.user_id == user.id).delete()
        db.query(models.User).filter(models.User.email_or_demo_id == "bandit-test").delete()
        db.commit()
        db.close()


def test_feedback_updates_alpha_beta() -> None:
    """Positive and negative feedback update the selected arm posterior."""
    db = SessionLocal()
    user = models.User(full_name="Bandit Feedback", email_or_demo_id="bandit-feedback")
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        bandit = RecommendationBandit(db, user.id)
        positive = bandit.update_feedback("activity", True)
        assert positive.alpha == 2.0
        negative = bandit.update_feedback("activity", False)
        assert negative.beta == 2.0
    finally:
        db.query(models.BanditArmState).filter(models.BanditArmState.user_id == user.id).delete()
        db.query(models.User).filter(models.User.email_or_demo_id == "bandit-feedback").delete()
        db.commit()
        db.close()
