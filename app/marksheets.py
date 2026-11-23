"""Private, best-effort extraction of subject marks from common marksheets."""
from __future__ import annotations

from io import BytesIO
import os
import re
import zipfile

MAX_SUBJECTS = 40
MAX_WORKSHEETS = 10
MAX_WORKSHEET_ROWS = 300
MAX_PDF_PAGES = 20
MAX_IMAGE_PIXELS = 20_000_000


class MarksheetError(ValueError):
    """A marksheet could not be read safely or reliably."""


def _text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _normal(value):
    return re.sub(r"[^a-z0-9]+", " ", _text(value).casefold()).strip()


def _column_index(headers, kind):
    aliases = {
        "subject": ("subject", "subject name", "paper", "paper name", "course name"),
        "obtained": ("obtained", "obtained marks", "marks obtained", "marks scored", "scored marks", "marks secured", "secured marks", "score", "your marks"),
        "maximum": ("maximum", "maximum marks", "max", "max marks", "full marks", "full mark", "out of", "total marks"),
        "passing": ("pass mark", "pass marks", "passing mark", "passing marks", "minimum pass", "minimum passing", "min pass", "min marks"),
    }[kind]
    for index, header in enumerate(headers):
        candidate = _normal(header)
        if candidate in aliases:
            return index
        if kind == "subject" and "subject" in candidate and "code" not in candidate:
            return index
        if kind == "obtained" and any(word in candidate for word in ("obtained", "secured", "scored")):
            return index
        if kind == "maximum" and any(word in candidate for word in ("maximum", "max mark", "full mark", "out of")):
            return index
        if kind == "passing" and any(word in candidate for word in ("pass mark", "passing", "minimum pass", "min pass")):
            return index
    return None


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = _text(value).replace(",", "")
    match = re.search(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", raw)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def _validated_row(subject, obtained, maximum, passing=None):
    subject = _text(subject)
    if not subject or subject.casefold() in {"total", "grand total", "percentage", "result", "remarks", "signature"}:
        return None
    if obtained is None and maximum is None:
        return None
    if obtained is None or maximum is None or maximum <= 0:
        raise MarksheetError(f"Could not read obtained and maximum marks for {subject}. Check the sheet and try again.")
    if maximum > 100:
        raise MarksheetError(f"{subject} has maximum marks above 100. Please correct the sheet to match the platform limit.")
    if obtained < 0 or obtained > maximum:
        raise MarksheetError(f"Obtained marks for {subject} are outside 0–{maximum:g}. Please check the sheet.")
    if passing is not None and (passing < 0 or passing > min(maximum, 40)):
        raise MarksheetError(f"The pass mark for {subject} cannot exceed 40 or its maximum marks.")
    return {"subject": subject[:120], "obtained": obtained, "maximum": maximum, "passing": passing}


def _rows_from_table(rows):
    header_position = None
    columns = None
    for index, row in enumerate(rows[:30]):
        headers = [_text(value) for value in row]
        subject = _column_index(headers, "subject")
        obtained = _column_index(headers, "obtained")
        maximum = _column_index(headers, "maximum")
        if len(headers) >= 3 and subject is not None and obtained is not None and maximum is not None and len({subject, obtained, maximum}) == 3:
            header_position = index
            columns = {"subject": subject, "obtained": obtained, "maximum": maximum, "passing": _column_index(headers, "passing")}
            break
    if header_position is None:
        return None

    parsed = []
    for row in rows[header_position + 1:MAX_WORKSHEET_ROWS]:
        if len(parsed) >= MAX_SUBJECTS:
            raise MarksheetError(f"A maximum of {MAX_SUBJECTS} subjects can be imported at once.")
        subject_index = columns["subject"]
        obtained_index = columns["obtained"]
        maximum_index = columns["maximum"]
        if max(subject_index, obtained_index, maximum_index) >= len(row):
            continue
        subject = row[subject_index]
        obtained = _number(row[obtained_index])
        maximum = _number(row[maximum_index])
        passing_index = columns["passing"]
        passing = _number(row[passing_index]) if passing_index is not None and passing_index < len(row) else None
        result = _validated_row(subject, obtained, maximum, passing)
        if result:
            parsed.append(result)
    return parsed or None


def _split_columns(line):
    return [cell.strip() for cell in re.split(r"\s{2,}|\t+|\s*\|\s*", line.strip()) if cell.strip()]


def _rows_from_text(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header_position = None
    columns = None
    loose_pass_column = False
    for index, line in enumerate(lines[:80]):
        cells = _split_columns(line)
        subject = _column_index(cells, "subject")
        obtained = _column_index(cells, "obtained")
        maximum = _column_index(cells, "maximum")
        if len(cells) >= 3 and subject is not None and obtained is not None and maximum is not None and len({subject, obtained, maximum}) == 3:
            header_position = index
            columns = {"subject": subject, "obtained": obtained, "maximum": maximum, "passing": _column_index(cells, "passing")}
            break
        normalized = _normal(line)
        if ("subject" in normalized or "paper" in normalized) and ("obtained" in normalized or "secured" in normalized or "scored" in normalized) and ("maximum" in normalized or "max marks" in normalized or "full marks" in normalized):
            header_position = index
            loose_pass_column = _column_index([line], "passing") is not None
            break
    if header_position is None:
        raise MarksheetError("We could not find a table with Subject, Obtained Marks, and Maximum Marks headings.")

    parsed = []
    for line in lines[header_position + 1:]:
        if len(parsed) >= MAX_SUBJECTS:
            raise MarksheetError(f"A maximum of {MAX_SUBJECTS} subjects can be imported at once.")
        if columns:
            cells = _split_columns(line)
            indices = columns
            if max(index for index in indices.values() if index is not None) >= len(cells):
                continue
            subject = cells[indices["subject"]]
            obtained = _number(cells[indices["obtained"]])
            maximum = _number(cells[indices["maximum"]])
            passing_index = indices["passing"]
            passing = _number(cells[passing_index]) if passing_index is not None else None
        else:
            numbers = list(re.finditer(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?", line))
            needed = 3 if loose_pass_column and len(numbers) >= 3 else 2
            if len(numbers) < needed:
                continue
            marks = numbers[-needed:]
            subject = line[:marks[0].start()].strip(" \t|:-")
            values = [_number(match.group()) for match in marks]
            obtained, maximum = values[0], values[1]
            passing = values[2] if needed == 3 else None
        result = _validated_row(subject, obtained, maximum, passing)
        if result:
            parsed.append(result)
    if not parsed:
        raise MarksheetError("We found the marks table but could not read any subject rows. Check the document is clear and try again.")
    return parsed


def _read_workbook(data, extension):
    try:
        if extension == "xlsx":
            from openpyxl import load_workbook
            with zipfile.ZipFile(BytesIO(data)) as archive:
                if len(archive.infolist()) > 2_000 or sum(item.file_size for item in archive.infolist()) > 50_000_000:
                    raise MarksheetError("This workbook expands beyond the safe upload limit. Save a smaller workbook and try again.")
            workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
            sheets = workbook.worksheets[:MAX_WORKSHEETS]
            for sheet in sheets:
                rows = list(sheet.iter_rows(min_row=1, max_row=min(sheet.max_row or 0, MAX_WORKSHEET_ROWS), values_only=True))
                extracted = _rows_from_table(rows)
                if extracted:
                    return extracted
            raise MarksheetError("We could not find a readable subject marks table in this workbook.")
        import xlrd
        workbook = xlrd.open_workbook(file_contents=data, on_demand=True)
        for sheet in workbook.sheets()[:MAX_WORKSHEETS]:
            rows = [[sheet.cell_value(row, column) for column in range(sheet.ncols)] for row in range(min(sheet.nrows, MAX_WORKSHEET_ROWS))]
            extracted = _rows_from_table(rows)
            if extracted:
                return extracted
        raise MarksheetError("We could not find a readable subject marks table in this workbook.")
    except MarksheetError:
        raise
    except ImportError as exc:
        raise MarksheetError("Spreadsheet reading is not installed. Install the project requirements and restart the app.") from exc
    except Exception as exc:
        raise MarksheetError("We could not open this spreadsheet. Save it as XLSX and upload it again.") from exc


def _read_pdf(data):
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise MarksheetError("This PDF is password protected. Upload an unlocked copy.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise MarksheetError(f"PDFs can contain up to {MAX_PDF_PAGES} pages for marksheet reading.")
        text = "\n".join(page.extract_text(extraction_mode="layout") or "" for page in reader.pages)
        if not text.strip():
            raise MarksheetError("This PDF appears scanned. Upload a spreadsheet, or a clear JPG/PNG image with Tesseract OCR installed.")
        return _rows_from_text(text[:250_000])
    except MarksheetError:
        raise
    except ImportError as exc:
        raise MarksheetError("PDF reading is not installed. Install the project requirements and restart the app.") from exc
    except Exception as exc:
        raise MarksheetError("We could not read this PDF. Try a text-based PDF or upload a spreadsheet.") from exc


def _read_image(data):
    try:
        from PIL import Image
        import pytesseract
        command = os.getenv("TESSERACT_CMD", "").strip()
        if not command and os.name == "nt":
            default_command = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.isfile(default_command):
                command = default_command
        if command:
            pytesseract.pytesseract.tesseract_cmd = command
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise MarksheetError("This image is too large to read. Resize it and upload it again.")
            text = pytesseract.image_to_string(image.convert("L"), config="--psm 6", timeout=15)
        if not text.strip():
            raise MarksheetError("No readable marks were found. Upload a clearer, upright image or a spreadsheet.")
        return _rows_from_text(text)
    except MarksheetError:
        raise
    except ImportError as exc:
        raise MarksheetError("Image reading is not installed. Install the project requirements and restart the app.") from exc
    except Exception as exc:
        if exc.__class__.__name__ == "TesseractNotFoundError":
            raise MarksheetError("Image OCR needs Tesseract installed. Configure TESSERACT_CMD or upload a PDF/XLSX instead.") from exc
        if exc.__class__.__name__ == "TimeoutError":
            raise MarksheetError("Image reading took too long. Use a smaller or clearer image and try again.") from exc
        raise MarksheetError("We could not read this image. Upload a clear, upright JPG or PNG and try again.") from exc


def extract_marksheet(data, extension):
    """Extract checked subject/mark rows; never saves the original upload."""
    extension = extension.casefold().lstrip(".")
    if extension == "xlsx" or extension == "xls":
        return _read_workbook(data, extension)
    if extension == "pdf":
        return _read_pdf(data)
    if extension in {"jpg", "jpeg", "png"}:
        return _read_image(data)
    raise MarksheetError("Choose a PDF, JPG, PNG, XLS, or XLSX marksheet.")
