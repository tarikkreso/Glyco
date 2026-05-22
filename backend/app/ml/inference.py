from __future__ import annotations

import json
import warnings
from functools import lru_cache
from pathlib import Path
from statistics import mean, pstdev

import joblib

from app.rules.engine import risk_level

ROOT = Path(__file__).resolve().parents[3]


def _artifact_dir() -> Path:
    """Return the first artifact directory that contains the model bundles."""
    candidates = [
        Path(__file__).resolve().parents[2] / "ml" / "artifacts",
        ROOT / "ml" / "artifacts",
    ]
    for candidate in candidates:
        if (candidate / "risk_model.joblib").exists() or (candidate / "trend_model.joblib").exists():
            return candidate
    return candidates[-1]


ARTIFACTS = _artifact_dir()


def _is_lfs_pointer(path: Path) -> bool:
    """Detect Git LFS pointer files before joblib/json parsing hides the cause."""
    if not path.exists() or path.stat().st_size > 1024:
        return False
    try:
        return path.read_text(encoding="utf-8").startswith("version https://git-lfs.github.com/spec/v1")
    except UnicodeDecodeError:
        return False


def _ensure_real_artifact(path: Path) -> None:
    if _is_lfs_pointer(path):
        raise RuntimeError(f"artifact-lfs-pointer:{path.name}")


@lru_cache(maxsize=1)
def _load_risk_bundle() -> dict:
    model_path = ARTIFACTS / "risk_model.joblib"
    preprocessor_path = ARTIFACTS / "risk_preprocessor.joblib"
    metadata_path = ARTIFACTS / "risk_metadata.json"
    for path in (model_path, preprocessor_path, metadata_path):
        _ensure_real_artifact(path)
    model = joblib.load(model_path)
    preprocessor = joblib.load(preprocessor_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return {"model": model, "preprocessor": preprocessor, "metadata": metadata}


@lru_cache(maxsize=1)
def _load_trend_bundle() -> dict:
    model_path = ARTIFACTS / "trend_model.joblib"
    preprocessor_path = ARTIFACTS / "trend_preprocessor.joblib"
    metadata_path = ARTIFACTS / "trend_metadata.json"
    for path in (model_path, preprocessor_path, metadata_path):
        _ensure_real_artifact(path)
    model = joblib.load(model_path)
    preprocessor = joblib.load(preprocessor_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return {"model": model, "preprocessor": preprocessor, "metadata": metadata}


def _age_bucket(age: int) -> int:
    boundaries = [24, 29, 34, 39, 44, 49, 54, 59, 64, 69, 74, 79]
    for idx, limit in enumerate(boundaries, start=1):
        if age <= limit:
            return idx
    return 13


def build_risk_feature_row(profile) -> dict[str, float | int]:
    return {
        "HighBP": int(profile.high_bp),
        "HighChol": int(profile.high_chol),
        "CholCheck": 1,
        "BMI": float(profile.bmi),
        "Smoker": int(profile.smoker),
        "Stroke": int(profile.stroke_history),
        "HeartDiseaseorAttack": int(profile.heart_disease_history),
        "PhysActivity": int(profile.phys_activity),
        "Fruits": int(profile.fruits),
        "Veggies": int(profile.veggies),
        "HvyAlcoholConsump": 0,
        "AnyHealthcare": 1,
        "NoDocbcCost": 0,
        "GenHlth": int(profile.general_health),
        "MentHlth": 3,
        "PhysHlth": 5 if profile.difficulty_walking else 2,
        "DiffWalk": int(profile.difficulty_walking),
        "Sex": 1 if str(profile.sex).lower() == "male" else 0,
        "Age": _age_bucket(profile.age),
        "Education": 4,
        "Income": 5,
    }


def predict_risk(profile) -> dict:
    try:
        bundle = _load_risk_bundle()
        features = bundle["preprocessor"]["features"]
        row = build_risk_feature_row(profile)
        vector = [row[name] for name in features]
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="X does not have valid feature names")
            probability = float(bundle["model"].predict_proba([vector])[0][1])
        threshold = float(bundle["preprocessor"].get("threshold", 0.35))
        return {
            "ok": True,
            "probability": round(probability, 4),
            "risk_level": risk_level(probability),
            "feature_row": row,
            "threshold": threshold,
            "model_version": bundle["metadata"]["model_version"],
        }
    except Exception as exc:
        # If artifacts are unavailable, callers fall back to deterministic rules
        # so the agent can still provide transparent support during demos.
        return {"ok": False, "reason": f"risk-model-fallback:{exc.__class__.__name__}"}


def _rolling_mean(values: list[float], window: int) -> float:
    sample = values[-window:]
    return mean(sample) if sample else 0.0


def _build_daily_monitoring_rows(logs: list) -> list[dict]:
    records: list[dict] = []
    for log in sorted(logs, key=lambda item: item.log_date):
        glucose_values = [log.glucose_level] if log.glucose_level is not None else []
        if not glucose_values:
            continue
        mean_value = mean(glucose_values)
        std_value = pstdev(glucose_values) if len(glucose_values) > 1 else 0.0
        records.append(
            {
                "day": log.log_date,
                "glucose_mean": mean_value,
                "glucose_std": std_value,
                "glucose_min": min(glucose_values),
                "glucose_max": max(glucose_values),
                "glucose_count": len(glucose_values),
                "high_count": sum(1 for value in glucose_values if value >= (130 if getattr(log, "is_fasting", True) else 180)),
                "low_count": sum(1 for value in glucose_values if value < 70),
                "insulin_total": 0.0,
                "meal_events": int(not getattr(log, "is_fasting", True)),
                "exercise_events": 0,
                "hypo_events": 0,
            }
        )
    records.sort(key=lambda item: item["day"])
    for index, record in enumerate(records):
        previous = records[index - 1]["glucose_mean"] if index > 0 else record["glucose_mean"]
        record["glucose_slope"] = record["glucose_mean"] - previous if index > 0 else 0.0
        mean_values = [item["glucose_mean"] for item in records[: index + 1]]
        std_values = [item["glucose_std"] for item in records[: index + 1]]
        count_values = [item["glucose_count"] for item in records[: index + 1]]
        record["mean_3day"] = _rolling_mean(mean_values, 3)
        record["std_3day"] = _rolling_mean(std_values, 3)
        record["count_3day"] = float(sum(count_values[-3:]))
    return records


def predict_monitoring(logs: list) -> dict:
    try:
        bundle = _load_trend_bundle()
        features = bundle["preprocessor"]["features"]
        rows = _build_daily_monitoring_rows(logs)
        if len(rows) < 3:
            return {"ok": False, "reason": "trend-model-fallback:insufficient-history"}
        latest = rows[-1]
        vector = [float(latest[name]) for name in features]
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="X does not have valid feature names")
            probabilities = bundle["model"].predict_proba([vector])[0]
            predicted = str(bundle["model"].predict([vector])[0])
        labels = list(bundle["model"].classes_)
        score_map = {label: float(probability) for label, probability in zip(labels, probabilities)}
        return {
            "ok": True,
            "trend_label": predicted,
            "trend_score": round(score_map[predicted], 4),
            "feature_row": {name: float(latest[name]) for name in features},
            "score_map": score_map,
            "model_version": bundle["metadata"]["model_version"],
        }
    except Exception as exc:
        # Monitoring follows the same resilience contract as risk scoring: the
        # API returns an explainable rules result instead of failing hard.
        return {"ok": False, "reason": f"trend-model-fallback:{exc.__class__.__name__}"}
