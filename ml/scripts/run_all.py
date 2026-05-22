from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "ml" / "scripts"
ARTIFACTS_DIR = ROOT / "ml" / "artifacts"
PROCESSED_DIR = ROOT / "data" / "processed"

PIPELINE = [
    ("clean_cgm_data.py", "data cleaning"),
    ("build_forecast_features.py", "feature engineering"),
    ("train_forecast_model.py", "LightGBM training"),
    ("prepare_datasets.py", "existing risk + monitoring prep"),
    ("train_risk_model.py", "existing risk training"),
    ("prepare_monitoring_data.py", "existing monitoring prep"),
    ("train_monitoring_model.py", "existing monitoring training"),
]


def _run_script(script_name: str, label: str) -> None:
    """Run one pipeline script with a clear console section header."""
    print(f"\n=== {script_name} ({label}) ===")
    subprocess.run([sys.executable, str(SCRIPTS_DIR / script_name)], check=True, cwd=ROOT)


def _file_size(path: Path) -> str:
    """Return a compact file size label for an artifact path."""
    if not path.exists():
        return "missing"
    size = path.stat().st_size
    return f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MB"


def _metric_for(path: Path) -> str:
    """Extract a useful metric from adjacent metadata when available."""
    if path.name == "forecast_metadata.json" and path.exists():
        metadata = json.loads(path.read_text(encoding="utf-8"))
        return f"MAE 60={metadata.get('mae_per_horizon', {}).get('60', 'n/a')}"
    if path.name == "risk_metadata.json" and path.exists():
        metadata = json.loads(path.read_text(encoding="utf-8"))
        return f"ROC AUC={metadata.get('roc_auc', 'n/a')}"
    if path.name == "trend_metadata.json" and path.exists():
        metadata = json.loads(path.read_text(encoding="utf-8"))
        report = metadata.get("classification_report", {})
        return f"accuracy={report.get('accuracy', 'n/a')}"
    if path.name == "cgm_cleaning_report.json" and path.exists():
        metadata = json.loads(path.read_text(encoding="utf-8"))
        return f"rows={metadata.get('final_rows', 'n/a')}"
    if path.name == "forecast_feature_metadata.json" and path.exists():
        metadata = json.loads(path.read_text(encoding="utf-8"))
        return f"rows={metadata.get('n_rows', 'n/a')}"
    return "-"


def _summary_rows() -> list[tuple[str, str, str]]:
    """Collect artifact names, sizes, and headline metrics for the pipeline summary."""
    paths = [
        PROCESSED_DIR / "cgm_clean.csv",
        PROCESSED_DIR / "cgm_cleaning_report.json",
        PROCESSED_DIR / "cgm_features.csv",
        PROCESSED_DIR / "forecast_feature_metadata.json",
        ARTIFACTS_DIR / "forecast_metadata.json",
        ARTIFACTS_DIR / "risk_metadata.json",
        ARTIFACTS_DIR / "trend_metadata.json",
    ]
    paths.extend(ARTIFACTS_DIR / f"forecast_model_{horizon}min.pkl" for horizon in (60, 120, 180, 240))
    return [(path.name, _file_size(path), _metric_for(path)) for path in paths]


def main() -> None:
    """Run the full Glyco ML pipeline and print a compact artifact summary."""
    for script_name, label in PIPELINE:
        _run_script(script_name, label)
    print("\n=== Artifact Summary ===")
    print("artifact name | file size | key metric")
    for name, size, metric in _summary_rows():
        print(f"{name} | {size} | {metric}")


if __name__ == "__main__":
    main()
