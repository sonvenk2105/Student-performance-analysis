from io import BytesIO

import pytest
from openpyxl import Workbook
from reportlab.pdfgen import canvas

from app.marksheets import MarksheetError, extract_marksheet


def make_workbook(rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def test_xlsx_extracts_subject_obtained_maximum_and_pass_marks():
    data = make_workbook([
        ["Subject", "Marks Obtained", "Maximum Marks", "Pass Marks"],
        ["Mathematics", 82, 100, 40],
        ["Science", 18, 20, 8],
    ])
    rows = extract_marksheet(data, "xlsx")
    assert rows == [
        {"subject": "Mathematics", "obtained": 82.0, "maximum": 100.0, "passing": 40.0},
        {"subject": "Science", "obtained": 18.0, "maximum": 20.0, "passing": 8.0},
    ]


def test_xlsx_leaves_pass_mark_blank_when_sheet_does_not_include_it():
    data = make_workbook([["Subject", "Obtained Marks", "Maximum Marks"], ["History", 75, 100]])
    assert extract_marksheet(data, "xlsx")[0]["passing"] is None


@pytest.mark.parametrize("row", [
    ["Mathematics", 82, 101, 40],
    ["Mathematics", 82, 100, 41],
])
def test_xlsx_rejects_values_outside_platform_limits(row):
    data = make_workbook([["Subject", "Marks Obtained", "Maximum Marks", "Pass Marks"], row])
    with pytest.raises(MarksheetError):
        extract_marksheet(data, "xlsx")


def test_text_pdf_extracts_aligned_mark_columns():
    stream = BytesIO()
    document = canvas.Canvas(stream)
    for y, values in [(760, ("Subject", "Marks Obtained", "Maximum Marks", "Pass Marks")),
                      (735, ("Mathematics", "82", "100", "40")),
                      (710, ("Science", "18", "20", "8"))]:
        for x, value in zip((40, 230, 390, 540), values):
            document.drawString(x, y, value)
    document.save()
    rows = extract_marksheet(stream.getvalue(), "pdf")
    assert [(row["subject"], row["obtained"], row["maximum"], row["passing"]) for row in rows] == [
        ("Mathematics", 82.0, 100.0, 40.0), ("Science", 18.0, 20.0, 8.0)
    ]


def test_plain_text_table_extraction_handles_compact_columns():
    from app.marksheets import _rows_from_text
    rows = _rows_from_text("Subject Marks Obtained Maximum Marks Pass Marks\nMathematics 82 100 40\nScience 18 20 8")
    assert [row["subject"] for row in rows] == ["Mathematics", "Science"]


def test_image_ocr_text_prefills_mark_rows(monkeypatch):
    from PIL import Image
    import pytesseract
    image = Image.new("RGB", (320, 120), "white")
    stream = BytesIO()
    image.save(stream, format="PNG")
    monkeypatch.setattr(pytesseract, "image_to_string", lambda *_args, **_kwargs: "Subject Marks Obtained Maximum Marks Pass Marks\nMathematics 82 100 40")
    rows = extract_marksheet(stream.getvalue(), "png")
    assert rows == [{"subject": "Mathematics", "obtained": 82.0, "maximum": 100.0, "passing": 40.0}]
