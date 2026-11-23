from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from sqlalchemy import desc, select
from app import db
from app.models import Assessment

def make_report(assessment):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42)
    styles = getSampleStyleSheet()
    story = [Paragraph("Student Performance Analysis", styles["Title"]), Paragraph("Generated from this saved assessment", styles["Normal"]), Spacer(1,12)]
    s = assessment.student
    story += [Paragraph(f"Student: {s.name} · {s.student_id or 'ID unavailable'}", styles["Normal"]), Paragraph(f"Course: {assessment.course} · Semester {assessment.semester} · {assessment.label}", styles["Normal"]), Paragraph(f"Date: {assessment.assessed_at.strftime('%Y-%m-%d')} · Rule version: {assessment.rule_version}", styles["Normal"]), Spacer(1,12)]
    story.append(Paragraph(f"Total: {assessment.total_obtained:g} / {assessment.total_maximum:g} · {assessment.percentage:.2f}% · Grade {assessment.grade} · {'Pass' if assessment.passed else 'Needs improvement'}", styles["Heading2"]))
    data = [["Subject","Obtained","Maximum","Percent","Grade","Status"]]
    data += [[m.subject, f"{m.obtained:g}", f"{m.maximum:g}", f"{m.percentage:.1f}%", m.grade, "Pass" if m.passed else "Fail"] for m in assessment.marks]
    table = Table(data, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#5634a5")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#dddddd")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f6f4fb")]),("PADDING",(0,0),(-1,-1),6)]))
    story += [table, Spacer(1,14), Paragraph("Subject percentages", styles["Heading2"])]
    drawing = Drawing(460, 190)
    chart = VerticalBarChart(); chart.x=50; chart.y=25; chart.height=140; chart.width=390
    chart.data=[tuple(m.percentage for m in assessment.marks)]
    chart.categoryAxis.categoryNames=[m.subject[:18] for m in assessment.marks]
    chart.valueAxis.valueMin=0; chart.valueAxis.valueMax=100; chart.valueAxis.valueStep=20
    chart.bars[0].fillColor=colors.HexColor("#8061cc")
    drawing.add(chart); story.append(drawing)
    story += [Spacer(1,14), Paragraph("Improvement notes", styles["Heading2"])]
    for m in assessment.marks: story.append(Paragraph(f"{m.subject}: {m.recommendation}", styles["BodyText"]))
    previous = db.session.scalars(select(Assessment).where(Assessment.student_id == assessment.student_id, Assessment.id != assessment.id).order_by(desc(Assessment.assessed_at)).limit(3)).all()
    if previous:
        story += [Spacer(1,10), Paragraph("Recent saved assessments", styles["Heading2"])]
        history = [["Assessment", "Semester", "Date", "Percentage", "Grade"]]
        history += [[p.label, str(p.semester), p.assessed_at.strftime("%Y-%m-%d"), f"{p.percentage:.2f}%", p.grade] for p in previous]
        story.append(Table(history, repeatRows=1, hAlign="LEFT", style=TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#5634a5")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#dddddd")),("PADDING",(0,0),(-1,-1),6)])))
    story.append(Spacer(1,10)); story.append(Paragraph("Results describe this assessment and do not guarantee future outcomes. Predictions are not available until a model passes historical validation.", styles["Italic"]))
    doc.build(story); buffer.seek(0); return buffer
