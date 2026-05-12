import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.database import SessionLocal
from app.db import models
from app.services.pdf_service import generate_pdf_report


def test_pdf_is_generated_and_valid_bytes() -> None:
    """PDF service writes a valid PDF document for an existing report."""
    db = SessionLocal()
    report = models.Report(user_id=1, report_type="doctor", content_json={"title": "Doctor Report", "sections": []})
    try:
        db.add(report)
        db.commit()
        db.refresh(report)
        path = generate_pdf_report(db, report.id)
        data = Path(path).read_bytes()
        assert data.startswith(b"%PDF")
        assert len(data) > 500
    finally:
        db.query(models.Report).filter(models.Report.id == report.id).delete()
        db.commit()
        db.close()
