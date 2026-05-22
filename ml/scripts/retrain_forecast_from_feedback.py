from __future__ import annotations

# Requirements: pandas, joblib, scikit-learn, lightgbm.

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pandas as pd
from lightgbm import LGBMRegressor
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
ARTIFACTS_DIR = ROOT / "ml" / "artifacts"
MIN_EVALUATIONS = 50
MAE_DEGRADATION_RATIO = 1.2
HORIZONS = (60, 120, 180, 240)

sys.path.insert(0, str(BACKEND_DIR))

from app.db.database import SessionLocal  # noqa: E402
from app.db import models  # noqa: E402


def _load_baseline_mae() -> dict[str, float]:
    """Load baseline MAE values from the deployed forecast metadata."""
    metadata_path = ARTIFACTS_DIR / "forecast_metadata.json"
    if not metadata_path.exists():
        return {str(horizon): 1.5 for horizon in HORIZONS}
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return {str(key): float(value) for key, value in metadata.get("mae_per_horizon", {}).items()}


def _evaluation_frame(db: Session) -> pd.DataFrame:
    """Read stored forecast evaluations into a tabular retraining dataset."""
    rows = db.query(models.GlucoseForecastEvaluation).all()
    return pd.DataFrame(
        [
            {
                "user_id": row.user_id,
                "forecast_id": row.forecast_id,
                "horizon_minutes": row.horizon_minutes,
                "predicted_mmol": row.predicted_mmol,
                "actual_mmol": row.actual_mmol,
                "signed_error": row.signed_error,
                "absolute_error": row.absolute_error,
            }
            for row in rows
        ]
    )


def _eligible_horizons(df: pd.DataFrame, baseline_mae: dict[str, float]) -> list[int]:
    """Return horizons with enough evidence and meaningfully degraded MAE."""
    eligible: list[int] = []
    for horizon in HORIZONS:
        subset = df[df["horizon_minutes"] == horizon]
        if len(subset) < MIN_EVALUATIONS:
            continue
        observed_mae = float(subset["absolute_error"].mean())
        if observed_mae >= baseline_mae.get(str(horizon), 1.5) * MAE_DEGRADATION_RATIO:
            eligible.append(horizon)
    return eligible


def retrain_feedback_models() -> dict[str, object]:
    """Train residual correction models from accumulated forecast evaluation data."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        df = _evaluation_frame(db)
    finally:
        db.close()
    baseline_mae = _load_baseline_mae()
    if df.empty:
        result = {"status": "skipped", "reason": "no forecast evaluations", "evaluations": 0}
        print(json.dumps(result, indent=2))
        return result
    eligible = _eligible_horizons(df, baseline_mae)
    if not eligible:
        result = {
            "status": "skipped",
            "reason": "insufficient degraded feedback",
            "evaluations": int(len(df)),
            "minimum_evaluations": MIN_EVALUATIONS,
            "mae_degradation_ratio": MAE_DEGRADATION_RATIO,
        }
        print(json.dumps(result, indent=2))
        return result

    trained: dict[str, dict[str, float | int]] = {}
    for horizon in eligible:
        subset = df[df["horizon_minutes"] == horizon].copy()
        features = subset[["predicted_mmol"]]
        target = subset["signed_error"]
        model = LGBMRegressor(
            n_estimators=150,
            learning_rate=0.05,
            max_depth=3,
            num_leaves=7,
            min_child_samples=5,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(features, target)
        path = ARTIFACTS_DIR / f"forecast_residual_correction_{horizon}min.pkl"
        joblib.dump(model, path)
        trained[str(horizon)] = {
            "rows": int(len(subset)),
            "observed_mae": float(subset["absolute_error"].mean()),
        }
    metadata = {
        "model_version": "forecast-feedback-residual-0.1",
        "status": "trained",
        "trained_horizons": trained,
        "training_date": datetime.now(UTC).isoformat(),
        "note": "Residual correction artifacts are candidates for review before deployment.",
    }
    (ARTIFACTS_DIR / "forecast_feedback_retrain_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return metadata


def main() -> None:
    """Run forecast feedback retraining when enough forecast errors have accumulated."""
    retrain_feedback_models()


if __name__ == "__main__":
    main()
