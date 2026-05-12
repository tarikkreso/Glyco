from __future__ import annotations

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ZIP_PATH = ROOT / "diabetes.zip"
OUT = ROOT / "data" / "processed" / "monitoring_dataset_summary.json"


def main() -> None:
    with zipfile.ZipFile(ZIP_PATH) as archive:
        entries = [{"name": item.filename, "size": item.file_size} for item in archive.infolist()]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": str(ZIP_PATH),
        "entries": entries,
        "status": "Archive inspected. Full UCI tar.Z extraction can be added when local tooling supports it.",
        "fallback": "Backend monitoring currently uses engineered rules over user health logs.",
    }, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
