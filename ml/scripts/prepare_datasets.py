from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold, train_test_split

from train_monitoring_model import assign_label, build_daily_features, load_events

ROOT = Path(__file__).resolve().parents[2]
RISK_ZIP_PATH = ROOT / "diabetes_binary_health_indicators_BRFSS2015.csv.zip"
PROCESSED = ROOT / "data" / "processed"

RISK_TARGET = "Diabetes_binary"
RANDOM_STATE = 42
TREND_LABEL_ORDER = ["stable", "watch", "concerning"]


def load_risk_source() -> pd.DataFrame:
    with zipfile.ZipFile(RISK_ZIP_PATH) as archive:
        with archive.open("diabetes_binary_health_indicators_BRFSS2015.csv") as handle:
            return pd.read_csv(handle)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def distribution(series: pd.Series) -> dict[str, int]:
    return {str(key): int(value) for key, value in series.value_counts().sort_index().items()}


def prepare_risk_dataset() -> dict:
    raw = load_risk_source()
    duplicate_rows = int(raw.duplicated().sum())
    prepared = raw.drop_duplicates().reset_index(drop=True)

    train, test = train_test_split(
        prepared,
        test_size=0.2,
        random_state=RANDOM_STATE,
        stratify=prepared[RISK_TARGET].astype(int),
    )
    train = train.reset_index(drop=True)
    test = test.reset_index(drop=True)

    train.to_csv(PROCESSED / "risk_train.csv.gz", index=False)
    test.to_csv(PROCESSED / "risk_test.csv.gz", index=False)

    summary = {
        "source": str(RISK_ZIP_PATH),
        "target": RISK_TARGET,
        "random_state": RANDOM_STATE,
        "raw_rows": int(len(raw)),
        "duplicate_rows_removed": duplicate_rows,
        "prepared_rows": int(len(prepared)),
        "null_values": int(prepared.isna().sum().sum()),
        "class_distribution": distribution(prepared[RISK_TARGET].astype(int)),
        "split": {
            "strategy": "row-wise stratified split after duplicate removal",
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "train_distribution": distribution(train[RISK_TARGET].astype(int)),
            "test_distribution": distribution(test[RISK_TARGET].astype(int)),
        },
        "outputs": {
            "train": str(PROCESSED / "risk_train.csv.gz"),
            "test": str(PROCESSED / "risk_test.csv.gz"),
        },
    }
    write_json(PROCESSED / "risk_dataset_summary.json", summary)
    return summary


def build_trend_dataset() -> pd.DataFrame:
    events = load_events()
    daily = build_daily_features(events)
    daily["trend_label"] = daily.apply(assign_label, axis=1)
    daily = daily.dropna(subset=["future_mean"]).copy()
    daily["day"] = pd.to_datetime(daily["day"]).dt.strftime("%Y-%m-%d")
    return daily.reset_index(drop=True)


def patient_wise_split(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    split_iterator = splitter.split(daily, daily["trend_label"], groups=daily["patient_id"])
    train_idx, test_idx = next(split_iterator)
    train = daily.iloc[train_idx].reset_index(drop=True)
    test = daily.iloc[test_idx].reset_index(drop=True)
    return train, test


def oversample_minority_classes(train: pd.DataFrame) -> pd.DataFrame:
    class_counts = train["trend_label"].value_counts()
    target_count = int(class_counts.max())
    balanced_parts = []
    for label in TREND_LABEL_ORDER:
        label_rows = train[train["trend_label"] == label]
        if label_rows.empty:
            continue
        balanced_parts.append(
            label_rows.sample(
                n=target_count,
                replace=len(label_rows) < target_count,
                random_state=RANDOM_STATE,
            )
        )
    balanced = pd.concat(balanced_parts, ignore_index=True)
    return balanced.sample(frac=1, random_state=RANDOM_STATE).reset_index(drop=True)


def prepare_trend_dataset() -> dict:
    daily = build_trend_dataset()
    train, test = patient_wise_split(daily)
    train_balanced = oversample_minority_classes(train)

    train_patients = set(train["patient_id"])
    test_patients = set(test["patient_id"])
    overlap = sorted(train_patients.intersection(test_patients))

    daily.to_csv(PROCESSED / "trend_prepared.csv.gz", index=False)
    train.to_csv(PROCESSED / "trend_train.csv.gz", index=False)
    test.to_csv(PROCESSED / "trend_test.csv.gz", index=False)
    train_balanced.to_csv(PROCESSED / "trend_train_balanced.csv.gz", index=False)

    summary = {
        "source": str(ROOT / "diabetes.zip"),
        "random_state": RANDOM_STATE,
        "rows": int(len(daily)),
        "patients": int(daily["patient_id"].nunique()),
        "label_distribution": distribution(daily["trend_label"]),
        "split": {
            "strategy": "patient-wise StratifiedGroupKFold, first fold held out as test",
            "patient_overlap": overlap,
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "train_patients": int(train["patient_id"].nunique()),
            "test_patients": int(test["patient_id"].nunique()),
            "train_distribution": distribution(train["trend_label"]),
            "test_distribution": distribution(test["trend_label"]),
        },
        "balanced_training": {
            "strategy": "random oversampling of minority labels inside train split only",
            "rows": int(len(train_balanced)),
            "patients": int(train_balanced["patient_id"].nunique()),
            "distribution": distribution(train_balanced["trend_label"]),
            "test_set_untouched": True,
        },
        "outputs": {
            "prepared": str(PROCESSED / "trend_prepared.csv.gz"),
            "train": str(PROCESSED / "trend_train.csv.gz"),
            "test": str(PROCESSED / "trend_test.csv.gz"),
            "balanced_train": str(PROCESSED / "trend_train_balanced.csv.gz"),
        },
    }
    write_json(PROCESSED / "trend_dataset_summary.json", summary)
    return summary


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    risk_summary = prepare_risk_dataset()
    trend_summary = prepare_trend_dataset()
    print(
        json.dumps(
            {
                "risk": {
                    "prepared_rows": risk_summary["prepared_rows"],
                    "duplicate_rows_removed": risk_summary["duplicate_rows_removed"],
                    "train_rows": risk_summary["split"]["train_rows"],
                    "test_rows": risk_summary["split"]["test_rows"],
                },
                "trend": {
                    "rows": trend_summary["rows"],
                    "patients": trend_summary["patients"],
                    "patient_overlap": trend_summary["split"]["patient_overlap"],
                    "train_rows": trend_summary["split"]["train_rows"],
                    "test_rows": trend_summary["split"]["test_rows"],
                    "balanced_train_rows": trend_summary["balanced_training"]["rows"],
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
