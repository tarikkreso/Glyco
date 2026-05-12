import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.bayesian import beta_credible_interval, update_bayesian_state
from app.db.database import SessionLocal
from app.db import models


def test_prior_update_and_posterior_calculation() -> None:
    """Bayesian updates add RF probability mass to alpha and complement to beta."""
    db = SessionLocal()
    user = models.User(full_name="Bayes Test", email_or_demo_id="bayes-test")
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        state = update_bayesian_state(db, user.id, 0.75)
        assert state.alpha == 2.75
        assert state.beta == 5.25
        assert state.posterior_mean == state.alpha / (state.alpha + state.beta)
        assert state.updates_count == 1
    finally:
        db.query(models.BayesianRiskState).filter(models.BayesianRiskState.user_id == user.id).delete()
        db.query(models.User).filter(models.User.email_or_demo_id == "bayes-test").delete()
        db.commit()
        db.close()


def test_credible_interval_bounds() -> None:
    """Credible interval helper always returns bounded low/high values."""
    low, high = beta_credible_interval(2.0, 5.0)
    assert 0.0 <= low <= high <= 1.0
