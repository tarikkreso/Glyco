import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.main import app


def test_bayesian_risk_endpoint_schema() -> None:
    """The v1 Bayesian risk endpoint returns the required schema."""
    client = TestClient(app)
    payload = client.get("/v1/risk/bayesian/1").json()
    assert {"posterior_mean", "credible_interval", "number_of_updates", "prior", "posterior", "comparison"}.issubset(payload)
    assert "low" in payload["credible_interval"]
    assert "high" in payload["credible_interval"]
