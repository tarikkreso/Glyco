from __future__ import annotations

import json
import zipfile
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
ZIP_PATH = ROOT / "diabetes_binary_health_indicators_BRFSS2015.csv.zip"
ARTIFACTS = ROOT / "ml" / "artifacts"
PROCESSED = ROOT / "data" / "processed"


def load_cdc() -> pd.DataFrame:
    with zipfile.ZipFile(ZIP_PATH) as archive:
        with archive.open("diabetes_binary_health_indicators_BRFSS2015.csv") as handle:
            return pd.read_csv(handle)


def load_prepared_split() -> tuple[pd.DataFrame, pd.DataFrame] | None:
    train_path = PROCESSED / "risk_train.csv.gz"
    test_path = PROCESSED / "risk_test.csv.gz"
    if not train_path.exists() or not test_path.exists():
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

    model = RandomForestClassifier(n_estimators=220, random_state=42, class_weight="balanced_subsample", min_samples_leaf=4, n_jobs=1)
    model.fit(x_train, y_train)

    probabilities = model.predict_proba(x_test)[:, 1]
    threshold = 0.50
    predictions = (probabilities >= threshold).astype(int)
    metrics = {
        "rows": int(len(df)),
        "features": list(x_train.columns),
        "roc_auc": float(roc_auc_score(y_test, probabilities)),
        "classification_report": classification_report(y_test, predictions, output_dict=True),
        "confusion_matrix": confusion_matrix(y_test, predictions).tolist(),
        "threshold": threshold,
        "operating_point": "balanced_precision_recall",
        "model_version": "random-forest-0.2",
        "split_strategy": split_strategy,
    }
    joblib.dump(model, ARTIFACTS / "risk_model.joblib")
    joblib.dump({"features": list(x_train.columns), "threshold": threshold}, ARTIFACTS / "risk_preprocessor.joblib")
    (ARTIFACTS / "risk_metadata.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps({"roc_auc": metrics["roc_auc"], "artifacts": str(ARTIFACTS)}, indent=2))


if __name__ == "__main__":
    main()
