from __future__ import annotations

from datetime import datetime
from math import sqrt

from sqlalchemy.orm import Session

from app.db import models

DEFAULT_ALPHA = 2.0
DEFAULT_BETA = 5.0


# Returns an approximate 95% credible interval for a Beta posterior without
# adding a heavy SciPy dependency to the MVP.
def beta_credible_interval(alpha: float, beta: float) -> tuple[float, float]:
    """Approximate the 95% credible interval for a Beta distribution."""
    total = alpha + beta
    mean = alpha / total
    variance = (alpha * beta) / ((total * total) * (total + 1.0))
    radius = 1.96 * sqrt(max(variance, 0.0))
    return max(0.0, mean - radius), min(1.0, mean + radius)


# Builds the prior row lazily so existing users do not need a migration before
# requesting Bayesian risk.
def get_or_create_bayesian_state(db: Session, user_id: int) -> models.BayesianRiskState:
    """Load a user's Bayesian state, creating the default low-risk prior if missing."""
    row = db.query(models.BayesianRiskState).filter(models.BayesianRiskState.user_id == user_id).first()
    if row:
        return row
    low, high = beta_credible_interval(DEFAULT_ALPHA, DEFAULT_BETA)
    row = models.BayesianRiskState(
        user_id=user_id,
        alpha=DEFAULT_ALPHA,
        beta=DEFAULT_BETA,
        posterior_mean=DEFAULT_ALPHA / (DEFAULT_ALPHA + DEFAULT_BETA),
        credible_interval_low=low,
        credible_interval_high=high,
        updates_count=0,
        prior_alpha=DEFAULT_ALPHA,
        prior_beta=DEFAULT_BETA,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# Applies one soft observation from the Random Forest probability; probability
# mass increases alpha, and the complementary mass increases beta.
def update_bayesian_state(db: Session, user_id: int, rf_probability: float) -> models.BayesianRiskState:
    """Update and persist a user's Bayesian posterior from a model probability."""
    probability = min(1.0, max(0.0, float(rf_probability)))
    row = get_or_create_bayesian_state(db, user_id)
    row.alpha += probability
    row.beta += 1.0 - probability
    row.posterior_mean = row.alpha / (row.alpha + row.beta)
    row.credible_interval_low, row.credible_interval_high = beta_credible_interval(row.alpha, row.beta)
    row.updates_count += 1
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


# Converts the ORM row into a stable response contract used by the v1 endpoint,
# agent tools, and PDF report generation.
def serialize_bayesian_state(row: models.BayesianRiskState) -> dict:
    """Return a JSON-serializable Bayesian state with prior/posterior comparison."""
    prior_mean = row.prior_alpha / (row.prior_alpha + row.prior_beta)
    return {
        "user_id": row.user_id,
        "posterior_mean": row.posterior_mean,
        "credible_interval": {
            "low": row.credible_interval_low,
            "high": row.credible_interval_high,
        },
        "number_of_updates": row.updates_count,
        "prior": {
            "alpha": row.prior_alpha,
            "beta": row.prior_beta,
            "mean": prior_mean,
        },
        "posterior": {
            "alpha": row.alpha,
            "beta": row.beta,
            "mean": row.posterior_mean,
        },
        "comparison": {
            "absolute_change": row.posterior_mean - prior_mean,
            "relative_change": (row.posterior_mean - prior_mean) / prior_mean if prior_mean else 0.0,
        },
        "updated_at": row.updated_at,
    }
