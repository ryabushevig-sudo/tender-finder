"""Document parsing: DOCX / PDF / XLSX -> normalized markdown-like text."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from docx import Document as DocxDocument
from openpyxl import load_workbook

from app.core.logging import logger


def parse_document(path: Path) -> str:
    """Detect file type and parse it into plain text with table structure preserved."""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _parse_docx(path)
    if suffix == ".pdf":
        return _parse_pdf(path)
    if suffix in {".xlsx", ".xlsm"}:
        return _parse_xlsx(path)
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError(f"Unsupported document type: {suffix}")


def _parse_docx(path: Path) -> str:
    doc = DocxDocument(str(path))
    blocks: list[str] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            blocks.append(text)

    for ti, table in enumerate(doc.tables, start=1):
        blocks.append(f"\n[Таблица {ti}]")
        for row in table.rows:
            cells = []
            for cell in row.cells:
                # collapse internal newlines so rows stay one-per-line
                cell_text = " | ".join(p.text.strip() for p in cell.paragraphs if p.text.strip())
                cells.append(cell_text)
            if any(cells):
                blocks.append(" || ".join(cells))

    return "\n".join(blocks)


def _parse_pdf(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependency declared
        raise RuntimeError("pdfplumber is required for PDF parsing") from exc

    blocks: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            blocks.append(f"\n[Страница {page_num}]")
            text = page.extract_text() or ""
            if text.strip():
                blocks.append(text.strip())
            for ti, table in enumerate(page.extract_tables() or [], start=1):
                blocks.append(f"\n[Таблица {page_num}.{ti}]")
                for row in table:
                    cells = [(c or "").strip() for c in row]
                    if any(cells):
                        blocks.append(" || ".join(cells))
    return "\n".join(blocks)


def _parse_xlsx(path: Path) -> str:
    wb = load_workbook(str(path), data_only=True, read_only=True)
    blocks: list[str] = []
    for sheet in wb.worksheets:
        blocks.append(f"\n[Лист: {sheet.title}]")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c).strip() if c is not None else "" for c in row]
            if any(cells):
                blocks.append(" || ".join(cells))
    return "\n".join(blocks)


def parse_bytes(filename: str, data: bytes) -> str:
    """Parse a file from raw bytes; the suffix from filename selects the parser."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return _parse_docx_bytes(data)
    if suffix == ".pdf":
        return _parse_pdf_bytes(data)
    if suffix in {".xlsx", ".xlsm"}:
        return _parse_xlsx_bytes(data)
    if suffix == ".txt":
        return data.decode("utf-8", errors="replace")
    logger.warning("Unknown extension {} - attempting utf-8 decode", suffix)
    return data.decode("utf-8", errors="replace")


def _parse_docx_bytes(data: bytes) -> str:
    doc = DocxDocument(BytesIO(data))
    blocks: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            blocks.append(text)
    for ti, table in enumerate(doc.tables, start=1):
        blocks.append(f"\n[Таблица {ti}]")
        for row in table.rows:
            cells = []
            for cell in row.cells:
                cell_text = " | ".join(p.text.strip() for p in cell.paragraphs if p.text.strip())
                cells.append(cell_text)
            if any(cells):
                blocks.append(" || ".join(cells))
    return "\n".join(blocks)


def _parse_pdf_bytes(data: bytes) -> str:
    import pdfplumber

    blocks: list[str] = []
    with pdfplumber.open(BytesIO(data)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            blocks.append(f"\n[Страница {page_num}]")
            text = page.extract_text() or ""
            if text.strip():
                blocks.append(text.strip())
            for ti, table in enumerate(page.extract_tables() or [], start=1):
                blocks.append(f"\n[Таблица {page_num}.{ti}]")
                for row in table:
                    cells = [(c or "").strip() for c in row]
                    if any(cells):
                        blocks.append(" || ".join(cells))
    return "\n".join(blocks)


def _parse_xlsx_bytes(data: bytes) -> str:
    wb = load_workbook(BytesIO(data), data_only=True, read_only=True)
    blocks: list[str] = []
    for sheet in wb.worksheets:
        blocks.append(f"\n[Лист: {sheet.title}]")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c).strip() if c is not None else "" for c in row]
            if any(cells):
                blocks.append(" || ".join(cells))
    return "\n".join(blocks)
