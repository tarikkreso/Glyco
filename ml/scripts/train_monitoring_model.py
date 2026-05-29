from __future__ import annotations

import json
import zipfile
from pathlib import Path
import re

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight

ROOT = Path(__file__).resolve().parents[2]
ZIP_PATH = ROOT / "diabetes.zip"
RAW_DIR = ROOT / "data" / "raw" / "uci_diabetes"
DATA_DIR = RAW_DIR / "Diabetes-Data"
ARTIFACTS = ROOT / "ml" / "artifacts"
PROCESSED = ROOT / "data" / "processed"

GLUCOSE_CODES = {48, 57, 58, 59, 60, 61, 62, 63, 64}
INSULIN_CODES = {33, 34, 35}
MEAL_CODES = {66, 67, 68}
EXERCISE_CODES = {69, 70, 71}


def is_lfs_pointer(path: Path) -> bool:
    if not path.exists() or path.stat().st_size > 1024:
        return False
    try:
        return path.read_text(encoding="utf-8").startswith("version https://git-lfs.github.com/spec/v1")
    except UnicodeDecodeError:
        return False


def ensure_extracted() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if DATA_DIR.exists():
        return
    with zipfile.ZipFile(ZIP_PATH) as archive:
        archive.extractall(RAW_DIR)


def parse_patient_file(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        sep="\t",
        header=None,
        names=["date", "time", "code", "value"],
        dtype={"date": str, "time": str, "code": str, "value": str},
        on_bad_lines="skip",
    )
    df["code"] = pd.to_numeric(df["code"], errors="coerce")
    # The raw UCI files contain a few messy tokens such as "0Hi"; keep the numeric portion.
    df["value"] = (
        df["value"]
        .astype(str)
        .str.extract(r"(-?\d+\.?\d*)", expand=False)
        .pipe(pd.to_numeric, errors="coerce")
    )
    df["timestamp"] = pd.to_datetime(df["date"] + " " + df["time"], format="%m-%d-%Y %H:%M", errors="coerce")
    df = df.dropna(subset=["timestamp", "code", "value"]).copy()
    df["code"] = df["code"].astype(int)
    df["patient_id"] = path.name
    return df


def load_events() -> pd.DataFrame:
    ensure_extracted()
    patient_files = sorted(DATA_DIR.glob("data-*"))
    frames = [parse_patient_file(path) for path in patient_files]
    return pd.concat(frames, ignore_index=True)


def load_prepared_split() -> tuple[pd.DataFrame, pd.DataFrame] | None:
    train_path = PROCESSED / "trend_train.csv.gz"
    test_path = PROCESSED / "trend_test.csv.gz"
    if not train_path.exists() or not test_path.exists() or is_lfs_pointer(train_path) or is_lfs_pointer(test_path):
        return None
    return pd.read_csv(train_path), pd.read_csv(test_path)


def load_dataset_summary() -> dict | None:
    summary_path = PROCESSED / "trend_dataset_summary.json"
    if not summary_path.exists() or is_lfs_pointer(summary_path):
        return None
    return json.loads(summary_path.read_text(encoding="utf-8"))


def build_daily_features(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for patient_id, patient_df in events.groupby("patient_id"):
        glucose_df = patient_df[patient_df["code"].isin(GLUCOSE_CODES)].copy()
        if glucose_df.empty:
            continue
        glucose_df["day"] = glucose_df["timestamp"].dt.floor("D")
        grouped = glucose_df.groupby("day")
        daily = grouped["value"].agg(["mean", "std", "min", "max", "count"]).reset_index()
        daily = daily.rename(
            columns={
                "mean": "glucose_mean",
                "std": "glucose_std",
                "min": "glucose_min",
                "max": "glucose_max",
                "count": "glucose_count",
            }
        )
        daily["glucose_std"] = daily["glucose_std"].fillna(0)
        daily["patient_id"] = patient_id
        daily["high_count"] = grouped["value"].apply(lambda series: int((series >= 180).sum())).values
        daily["low_count"] = grouped["value"].apply(lambda series: int((series < 70).sum())).values

        patient_df["day"] = patient_df["timestamp"].dt.floor("D")
        insulin = patient_df[patient_df["code"].isin(INSULIN_CODES)].groupby("day")["value"].sum()
        meals = patient_df[patient_df["code"].isin(MEAL_CODES)].groupby("day")["code"].count()
        exercise = patient_df[patient_df["code"].isin(EXERCISE_CODES)].groupby("day")["code"].count()
        symptoms = patient_df[patient_df["code"] == 65].groupby("day")["code"].count()

        daily["insulin_total"] = daily["day"].map(insulin).fillna(0.0)
        daily["meal_events"] = daily["day"].map(meals).fillna(0).astype(int)
        daily["exercise_events"] = daily["day"].map(exercise).fillna(0).astype(int)
        daily["hypo_events"] = daily["day"].map(symptoms).fillna(0).astype(int)

        daily = daily.sort_values("day").reset_index(drop=True)
        daily["glucose_slope"] = daily["glucose_mean"].diff().fillna(0)
        daily["mean_3day"] = daily["glucose_mean"].rolling(3, min_periods=1).mean()
        daily["std_3day"] = daily["glucose_std"].rolling(3, min_periods=1).mean()
        daily["count_3day"] = daily["glucose_count"].rolling(3, min_periods=1).sum()
        daily["future_mean"] = daily["glucose_mean"].shift(-1).rolling(2, min_periods=1).mean()
        daily["future_high"] = daily["high_count"].shift(-1).fillna(0) + daily["high_count"].shift(-2).fillna(0)
        rows.extend(daily.to_dict("records"))
    return pd.DataFrame(rows)


def assign_label(row: pd.Series) -> str:
    future_mean = row["future_mean"]
    slope = row["glucose_slope"]
    if pd.isna(future_mean):
        return "watch"
    if future_mean >= 180 or row["future_high"] >= 2 or slope >= 25:
        return "concerning"
    if future_mean >= 130 or slope >= 10 or row["glucose_std"] >= 35:
        return "watch"
    return "stable"


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    # Keep the production trend model aligned with the simplified app contract:
    # patient-entered glucose value + fasting/not-fasting status. Insulin,
    # exercise, and symptom events remain in the dataset pipeline for analysis,
    # but are not model inputs because the patient flow no longer collects them.
    feature_columns = [
        "glucose_mean",
        "glucose_std",
        "glucose_min",
        "glucose_max",
        "glucose_count",
        "high_count",
        "low_count",
        "glucose_slope",
        "mean_3day",
        "std_3day",
        "count_3day",
    ]
    prepared_split = load_prepared_split()
    dataset_summary = load_dataset_summary()
    if prepared_split:
        train_df, test_df = prepared_split
        x_train = train_df[feature_columns].fillna(0)
        y_train = train_df["trend_label"]
        x_test = test_df[feature_columns].fillna(0)
        y_test = test_df["trend_label"]
        split_strategy = "prepared patient-wise split with train-only oversampling"
        patient_overlap = sorted(set(train_df["patient_id"]).intersection(set(test_df["patient_id"])))
        source_rows = int(dataset_summary["rows"]) if dataset_summary else int(len(test_df))
        source_patients = int(dataset_summary["patients"]) if dataset_summary else int(test_df["patient_id"].nunique())
        label_distribution = dataset_summary["label_distribution"] if dataset_summary else test_df["trend_label"].value_counts().to_dict()
        train_rows = int(dataset_summary["split"]["train_rows"]) if dataset_summary else int(len(train_df))
        test_rows = int(len(test_df))
        balanced_train_rows = int(dataset_summary.get("balanced_training", {}).get("rows", 0)) if dataset_summary else None
    else:
        events = load_events()
        daily = build_daily_features(events)
        daily["trend_label"] = daily.apply(assign_label, axis=1)
        daily = daily.dropna(subset=["future_mean"]).copy()
        x = daily[feature_columns].fillna(0)
        y = daily["trend_label"]
        x_train, x_test, y_train, y_test = train_test_split(
            x,
            y,
            test_size=0.2,
            random_state=42,
            stratify=y,
        )
        split_strategy = "legacy row-wise stratified split"
        patient_overlap = []
        source_rows = int(len(daily))
        source_patients = int(daily["patient_id"].nunique())
        label_distribution = daily["trend_label"].value_counts().to_dict()
        train_rows = int(len(x_train))
        test_rows = int(len(x_test))
        balanced_train_rows = None

    baseline = Pipeline(
        [("scale", StandardScaler()), ("model", LogisticRegression(max_iter=2000, class_weight="balanced"))]
    )
    baseline.fit(x_train, y_train)
    baseline_accuracy = float(baseline.score(x_test, y_test))

    watch_weight_multiplier = 5.0
    sample_weights = compute_sample_weight("balanced", y_train)
    sample_weights[y_train.eq("watch")] *= watch_weight_multiplier
    model = RandomForestClassifier(
        n_estimators=400,
        random_state=42,
        max_features="sqrt",
        min_samples_leaf=2,
        n_jobs=1,
    )
    model.fit(x_train, y_train, sample_weight=sample_weights)
    predictions = model.predict(x_test)
    metadata = {
        "rows": source_rows,
        "patients": source_patients,
        "features": feature_columns,
        "label_distribution": label_distribution,
        "train_rows": train_rows,
        "test_rows": test_rows,
        "balanced_train_rows": balanced_train_rows,
        "baseline_accuracy": baseline_accuracy,
        "classification_report": classification_report(y_test, predictions, output_dict=True),
        "confusion_matrix": confusion_matrix(y_test, predictions, labels=["stable", "watch", "concerning"]).tolist(),
        "model_version": "glucose-trend-random-forest-0.3",
        "split_strategy": "prepared patient-wise split with glucose-only weighted training" if prepared_split else split_strategy,
        "patient_overlap": patient_overlap,
        "feature_contract": "glucose-only patient app inputs",
        "watch_weight_multiplier": watch_weight_multiplier,
    }

    joblib.dump(model, ARTIFACTS / "trend_model.joblib")
    joblib.dump({"features": feature_columns, "label_order": ["stable", "watch", "concerning"]}, ARTIFACTS / "trend_preprocessor.joblib")
    (ARTIFACTS / "trend_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"rows": metadata["rows"], "patients": metadata["patients"], "baseline_accuracy": baseline_accuracy, "artifacts": str(ARTIFACTS)}, indent=2))


if __name__ == "__main__":
    main()
