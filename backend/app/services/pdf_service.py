from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir

from statistics import mean

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.db import models


# Generates a styled clinician-facing PDF from a stored Glyco report and the
# latest live model state.
def _palette(report_type: str) -> dict:
    if report_type == "doctor":
        return {
            "primary": "#1d4ed8",
            "accent": "#1e3a5f",
            "tag": "CLINICAL",
            "subtitle": "Clinical Summary Report",
            "header_bg": "#1d4ed8",
            "header_text": colors.white,
            "tag_bg": "#2563eb",
            "tag_text": colors.white,
        }
    if report_type == "family":
        return {
            "primary": "#be185d",
            "accent": "#831843",
            "tag": "FAMILY",
            "subtitle": "Family Update",
            "header_bg": "#fce7f3",
            "header_text": colors.HexColor("#9d174d"),
            "tag_bg": "#fce7f3",
            "tag_text": colors.HexColor("#9d174d"),
        }
    return {
        "primary": "#154539",
        "accent": "#154539",
        "tag": "WEEKLY",
        "subtitle": "Weekly Reflection",
        "header_bg": "#d1e8da",
        "header_text": colors.HexColor("#154539"),
        "tag_bg": "#d1e8da",
        "tag_text": colors.HexColor("#154539"),
    }


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 1) if values else None


def _build_metrics_table(metrics: list[list[str]], palette: dict) -> Table:
    rows = [["Metric", "Value"], *metrics]
    table = Table(rows, colWidths=[200, 280])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(palette["primary"])),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ccd7d2")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _build_log_table(recent_logs, palette: dict) -> Table | None:
    if not recent_logs:
        return None
    rows = [["Date", "Fasting", "Post-meal", "Activity", "BP"]]
    for log in recent_logs:
        bp = "-"
        if log.systolic_bp and log.diastolic_bp:
            bp = f"{log.systolic_bp}/{log.diastolic_bp}"
        rows.append([
            log.log_date.isoformat(),
            f"{log.glucose_level:g}" if getattr(log, "is_fasting", True) and log.glucose_level is not None else "-",
            f"{log.glucose_level:g}" if not getattr(log, "is_fasting", True) and log.glucose_level is not None else "-",
            str(log.activity_minutes or 0),
            bp,
        ])
    table = Table(rows, colWidths=[90, 70, 70, 60, 70])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(palette["primary"])),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ccd7d2")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _build_line_chart(values: list[float], palette: dict, title: str) -> Drawing | None:
    if not values:
        return None
    drawing = Drawing(420, 140)
    chart = LinePlot()
    chart.x = 30
    chart.y = 20
    chart.width = 360
    chart.height = 90
    chart.data = [list(enumerate(values))]
    chart.joinedLines = 1
    chart.lines[0].strokeColor = colors.HexColor(palette["primary"])
    chart.lines[0].strokeWidth = 2
    chart.xValueAxis.valueMin = 0
    chart.xValueAxis.valueMax = max(1, len(values) - 1)
    chart.xValueAxis.valueSteps = list(range(len(values)))
    y_min = min(values)
    y_max = max(values)
    pad = max(5, (y_max - y_min) * 0.2)
    chart.yValueAxis.valueMin = max(0, y_min - pad)
    chart.yValueAxis.valueMax = y_max + pad
    chart.yValueAxis.visibleGrid = 1
    chart.yValueAxis.gridStrokeColor = colors.HexColor("#e2e8f0")
    drawing.add(chart)
    drawing.add(String(30, 122, title, fontName="Helvetica-Bold", fontSize=9, fillColor=colors.HexColor(palette["primary"])))
    return drawing


def _build_bar_chart(values: list[float], labels: list[str], palette: dict, title: str) -> Drawing | None:
    if not values:
        return None
    drawing = Drawing(420, 140)
    chart = VerticalBarChart()
    chart.x = 30
    chart.y = 20
    chart.width = 360
    chart.height = 90
    chart.data = [values]
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(values) + 5
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.angle = 0
    chart.categoryAxis.labels.boxAnchor = "n"
    chart.barSpacing = 2
    chart.groupSpacing = 6
    chart.bars[0].fillColor = colors.HexColor(palette["primary"])
    drawing.add(chart)
    drawing.add(String(30, 122, title, fontName="Helvetica-Bold", fontSize=9, fillColor=colors.HexColor(palette["primary"])))
    return drawing


def generate_pdf_report(db: Session, report_id: int) -> Path:
    """Produce a styled PDF for a report and return its filesystem path."""
    report = db.get(models.Report, report_id)
    if not report:
        raise ValueError("Report not found")
    user = db.get(models.User, report.user_id)
    logs = db.query(models.HealthLog).filter(models.HealthLog.user_id == report.user_id).order_by(models.HealthLog.log_date.asc()).all()
    recent_logs = logs[-7:]
    latest_log = recent_logs[-1] if recent_logs else None
    fasting_values = [log.glucose_level for log in recent_logs if log.glucose_level is not None and getattr(log, "is_fasting", True)]
    post_values = [log.glucose_level for log in recent_logs if log.glucose_level is not None and not getattr(log, "is_fasting", True)]
    activity_values = [float(log.activity_minutes or 0) for log in recent_logs]
    avg_fasting = _avg(fasting_values)
    avg_post = _avg(post_values)
    avg_activity = _avg(activity_values)
    content = report.content_json or {}
    sections = content.get("sections", [])
    palette = _palette(report.report_type)

    output_dir = Path(gettempdir()) / "glyco_reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"glyco_report_{report_id}.pdf"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor(palette["accent"]),
        spaceAfter=12,
    )
    section_title_style = ParagraphStyle(
        "sectionTitle",
        parent=styles["Heading4"],
        fontSize=10,
        leading=12,
        textColor=colors.HexColor(palette["primary"]),
        spaceAfter=4,
        spaceBefore=10,
    )
    body_style = ParagraphStyle(
        "body",
        parent=styles["BodyText"],
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#222222"),
    )
    meta_style = ParagraphStyle(
        "meta",
        parent=styles["BodyText"],
        fontSize=9,
        textColor=colors.HexColor("#6b7280"),
    )

    doc = SimpleDocTemplate(str(path), pagesize=letter, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=36)
    story = []

    header_left = Paragraph(
        f"<b>Glyco Health</b><br/><font size='9'>{palette['subtitle']}</font>",
        ParagraphStyle(
            "headerLeft",
            parent=styles["BodyText"],
            fontSize=10,
            textColor=palette["header_text"],
            leading=12,
        ),
    )
    header_right = Paragraph(
        f"<para align='right'><font size='9'>{report.created_at.date().isoformat()}</font><br/>{palette['tag']}</para>",
        ParagraphStyle(
            "headerRight",
            parent=styles["BodyText"],
            fontSize=9,
            textColor=palette["header_text"],
            leading=12,
        ),
    )
    header = Table([[header_left, header_right]], colWidths=[330, 150])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(palette["header_bg"])),
        ("TEXTCOLOR", (0, 0), (-1, -1), palette["header_text"]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.extend([header, Spacer(1, 16)])

    if user:
        story.append(Paragraph(f"Patient: {user.full_name}", meta_style))
        story.append(Spacer(1, 6))

    story.append(Paragraph(content.get("title", "Glyco Report"), title_style))

    for section in sections:
        title = section.get("title", "").upper()
        body = section.get("body", "")
        story.append(Paragraph(title, section_title_style))
        story.append(Paragraph(body, body_style))

    if report.report_type == "doctor":
        metrics = [
            ["Avg fasting", f"{avg_fasting} mg/dL" if avg_fasting is not None else "n/a"],
            ["Avg post-meal", f"{avg_post} mg/dL" if avg_post is not None else "n/a"],
            ["Avg activity", f"{avg_activity} min/day" if avg_activity is not None else "n/a"],
            ["Latest BP", f"{latest_log.systolic_bp}/{latest_log.diastolic_bp} mmHg" if latest_log and latest_log.systolic_bp and latest_log.diastolic_bp else "n/a"],
        ]
        story.extend([Spacer(1, 12), Paragraph("SUMMARY METRICS", section_title_style), _build_metrics_table(metrics, palette)])
        log_table = _build_log_table(recent_logs, palette)
        if log_table:
            story.extend([Spacer(1, 12), Paragraph("RECENT LOGS", section_title_style), log_table])
        chart = _build_line_chart(fasting_values, palette, "Fasting Glucose Trend (last 7)")
        if chart:
            story.extend([Spacer(1, 12), chart])
    elif report.report_type == "family":
        metrics = [
            ["Avg fasting", f"{avg_fasting} mg/dL" if avg_fasting is not None else "n/a"],
            ["Latest reading", f"{latest_log.glucose_level} mg/dL" if latest_log and latest_log.glucose_level is not None else "n/a"],
            ["Avg activity", f"{avg_activity} min/day" if avg_activity is not None else "n/a"],
        ]
        story.extend([Spacer(1, 12), Paragraph("KEY NUMBERS", section_title_style), _build_metrics_table(metrics, palette)])
        chart = _build_line_chart(fasting_values, palette, "Fasting Glucose Snapshot")
        if chart:
            story.extend([Spacer(1, 12), chart])
    else:
        metrics = [
            ["Avg fasting", f"{avg_fasting} mg/dL" if avg_fasting is not None else "n/a"],
            ["Avg post-meal", f"{avg_post} mg/dL" if avg_post is not None else "n/a"],
            ["Avg activity", f"{avg_activity} min/day" if avg_activity is not None else "n/a"],
        ]
        story.extend([Spacer(1, 12), Paragraph("WEEKLY METRICS", section_title_style), _build_metrics_table(metrics, palette)])
        chart = _build_line_chart(fasting_values, palette, "Fasting Trend (last 7)")
        if chart:
            story.extend([Spacer(1, 12), chart])
        activity_chart = _build_bar_chart(activity_values, [log.log_date.strftime("%m/%d") for log in recent_logs], palette, "Activity Minutes")
        if activity_chart:
            story.extend([Spacer(1, 12), activity_chart])

    disclaimer = content.get("disclaimer")
    if disclaimer:
        story.extend([Spacer(1, 14), Paragraph(disclaimer, meta_style)])

    doc.build(story)
    return path
