from __future__ import annotations

import json
import zipfile
from pathlib import Path

import joblib
import pandas as pd
import numpy as np

from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight

ROOT = Path(__file__).resolve().parents[2]
ZIP_PATH = ROOT / "diabetes_binary_health_indicators_BRFSS2015.csv.zip"
ARTIFACTS = ROOT / "ml" / "artifacts"
PROCESSED = ROOT / "data" / "processed"


def is_lfs_pointer(path: Path) -> bool:
    if not path.exists() or path.stat().st_size > 1024:
        return False
    try:
        return path.read_text(encoding="utf-8").startswith("version https://git-lfs.github.com/spec/v1")
    except UnicodeDecodeError:
        return False


def load_cdc() -> pd.DataFrame:
    with zipfile.ZipFile(ZIP_PATH) as archive:
        with archive.open("diabetes_binary_health_indicators_BRFSS2015.csv") as handle:
            return pd.read_csv(handle)


def load_prepared_split() -> tuple[pd.DataFrame, pd.DataFrame] | None:
    train_path = PROCESSED / "risk_train.csv.gz"
    test_path = PROCESSED / "risk_test.csv.gz"
    if not train_path.exists() or not test_path.exists() or is_lfs_pointer(train_path) or is_lfs_pointer(test_path):
        return None
    return pd.read_csv(train_path), pd.read_csv(test_path)


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    target = "Diabetes_binary"
    prepared_split = load_prepared_split()
    if prepared_split:
        train_df, test_df = prepared_split
        df = pd.concat([train_df, test_df], ignore_index=True)
        x_train = train_df.drop(columns=[target])
        y_train = train_df[target].astype(int)
        x_test = test_df.drop(columns=[target])
        y_test = test_df[target].astype(int)
        split_strategy = "prepared stratified split from data/processed"
    else:
        df = load_cdc().drop_duplicates()
        x = df.drop(columns=[target])
        y = df[target].astype(int)
        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42, stratify=y)
        split_strategy = "inline stratified split after duplicate removal"

    baseline = Pipeline([("scale", StandardScaler()), ("model", LogisticRegression(max_iter=1000, class_weight="balanced"))])
    baseline.fit(x_train, y_train)

    sample_weights = compute_sample_weight("balanced", y_train)
    model = HistGradientBoostingClassifier(
        max_iter=360,
        learning_rate=0.035,
        l2_regularization=0.02,
        max_leaf_nodes=63,
        min_samples_leaf=30,
        random_state=42,
    )
    model.fit(x_train, y_train, sample_weight=sample_weights)

    probabilities = model.predict_proba(x_test)[:, 1]
    precision, recall, thresholds = precision_recall_curve(y_test, probabilities)
    f1_scores = 2 * precision * recall / (precision + recall + 1e-12)
    threshold_index = int(np.nanargmax(f1_scores[:-1]))
    threshold = float(thresholds[threshold_index])
    predictions = (probabilities >= threshold).astype(int)
    metrics = {
        "rows": int(len(df)),
        "features": list(x_train.columns),
        "roc_auc": float(roc_auc_score(y_test, probabilities)),
        "average_precision": float(average_precision_score(y_test, probabilities)),
        "brier_score": float(brier_score_loss(y_test, probabilities)),
        "classification_report": classification_report(y_test, predictions, output_dict=True),
        "classification_report_at_0_50": classification_report(y_test, (probabilities >= 0.50).astype(int), output_dict=True),
        "confusion_matrix": confusion_matrix(y_test, predictions).tolist(),
        "threshold": threshold,
        "operating_point": "max_positive_class_f1",
        "model_version": "hist-gradient-boosting-risk-0.3",
        "split_strategy": split_strategy,
        "baseline": {
            "model": "logistic_regression_balanced",
            "accuracy": float(baseline.score(x_test, y_test)),
        },
    }
    joblib.dump(model, ARTIFACTS / "risk_model.joblib")
    joblib.dump({"features": list(x_train.columns), "threshold": threshold}, ARTIFACTS / "risk_preprocessor.joblib")
    (ARTIFACTS / "risk_metadata.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps({"roc_auc": metrics["roc_auc"], "artifacts": str(ARTIFACTS)}, indent=2))


if __name__ == "__main__":
    main()
