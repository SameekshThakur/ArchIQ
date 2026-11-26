"""Turn an uploaded file into plain text the analysis engines can read.

Supported: text-like formats (txt, md, csv, json, yaml, tf, bicep, html), Word (.docx), PDF, Excel (.xlsx, every sheet), and scanned PDFs or images when OCR is installed.
Everything is parsed locally; nothing leaves the process.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from html.parser import HTMLParser
from pathlib import PurePath

from app.core.errors import ApiError, BadRequest
from app.services import ocr

MAX_BYTES = 8 * 1024 * 1024
TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml", ".tf", ".tfvars", ".bicep", ".log", ".xml", ".rst"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
SUPPORTED = sorted(TEXT_EXT | {".docx", ".pdf", ".xlsx", ".html", ".htm"} | IMAGE_EXT)


class UnsupportedFile(ApiError):
    def __init__(self, ext: str):
        super().__init__(415, "unsupported_file", f"'{ext or 'this file type'}' is not supported. Use one of: {', '.join(SUPPORTED)}")


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeError:
            continue
    return data.decode("latin-1", errors="replace")


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):  # noqa: ANN001
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4"):
            self.out.append("\n")
        if tag in ("h1", "h2", "h3", "h4"):
            self.out.append("#" * int(tag[1]) + " ")

    def handle_endtag(self, tag):  # noqa: ANN001
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4"):
            self.out.append("\n")

    def handle_data(self, data):  # noqa: ANN001
        if not self.skip:
            self.out.append(data)


def _html(text: str) -> str:
    p = _Strip()
    p.feed(text)
    return re.sub(r"\n{3,}", "\n\n", "".join(p.out)).strip()


def _docx(data: bytes) -> tuple[str, dict]:
    from docx import Document  # local import: only needed for Word files

    try:
        doc = Document(io.BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise BadRequest("This file is not a valid .docx document") from e
    lines: list[str] = []
    body = doc.element.body
    paragraphs = {p._p: p for p in doc.paragraphs}  # noqa: SLF001
    tables = {t._tbl: t for t in doc.tables}  # noqa: SLF001
    for el in body.iterchildren():
        if el in paragraphs:
            p = paragraphs[el]
            t = p.text.strip()
            if not t:
                lines.append("")
                continue
            style = (p.style.name if p.style is not None else "") or ""
            m = re.match(r"Heading (\d)", style)
            if m:
                lines.append("#" * int(m.group(1)) + " " + t)
            elif style == "Title":
                lines.append("# " + t)
            elif "List" in style:
                lines.append("- " + t)
            else:
                lines.append(t)
        elif el in tables:
            for row in tables[el].rows:
                cells = []
                for c in row.cells:
                    v = c.text.strip().replace("\n", " ")
                    if not cells or cells[-1] != v:  # merged cells repeat their text
                        cells.append(v)
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip(), dict(paragraphs=len(doc.paragraphs), tables=len(doc.tables))


def _reflow(page: str) -> str:
    """PDFs hard-wrap lines. Re-join lines that continue a sentence so sentence-level extraction still works."""
    out: list[str] = []
    for ln in (x.rstrip() for x in page.splitlines()):
        if not ln.strip():
            out.append("")
            continue
        prev = out[-1] if out else ""
        starts_block = bool(re.match(r"^(\d+(\.\d+)*[.)]?\s|[-•*]\s|#|Status:|\|)", ln.strip()))
        if prev and not starts_block and not re.search(r"[.!?:;]$", prev) and len(prev) > 45 and not prev.startswith(("#", "|")):
            out[-1] = prev + " " + ln.strip()
        else:
            out.append(ln.strip())
    return "\n".join(out)


def _pdf(data: bytes) -> tuple[str, dict]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise BadRequest("This PDF is password protected")
        pages = [_reflow(p.extract_text() or "") for p in reader.pages]
    except PdfReadError as e:
        raise BadRequest("This file is not a readable PDF") from e
    text = "\n\n".join(p for p in pages if p.strip()).strip()
    if len(text) < 25 * max(1, len(pages)):  # essentially no text layer: a scan
        scanned, meta = ocr.ocr_pdf(data)
        return _reflow(scanned.strip()), meta
    return text, dict(pages=len(pages))


def _cell(v: object) -> object:
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()  # type: ignore[union-attr]
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _xlsx(data: bytes) -> tuple[str, dict]:
    """Every visible sheet becomes CSV. A single sheet is returned as plain CSV; several are separated by '## Sheet: name' lines."""
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise BadRequest("This file is not a valid .xlsx workbook") from e
    blocks: list[tuple[str, str]] = []
    info: list[dict] = []
    for ws in wb.worksheets:
        if getattr(ws, "sheet_state", "visible") != "visible":
            continue
        rows = [[_cell(v) for v in row] for row in ws.iter_rows(values_only=True, max_row=100_000) if row is not None and any(v not in (None, "") for v in row)]
        # skip title rows above the table: the header is the first row with at least two filled cells
        start = next((i for i, r in enumerate(rows) if sum(1 for v in r if v != "") >= 2), None)
        if start is None:
            continue
        rows = rows[start:]
        width = max(max((i for i, v in enumerate(r) if v != ""), default=-1) for r in rows) + 1
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        for r in rows:
            w.writerow((r + [""] * width)[:width])
        blocks.append((ws.title, buf.getvalue()))
        info.append(dict(name=ws.title, rows=len(rows) - 1, columns=width))
    if not blocks:
        raise BadRequest("The workbook has no visible sheet with data")
    text = blocks[0][1] if len(blocks) == 1 else "\n".join(f"## Sheet: {n}\n{b}" for n, b in blocks)
    return text, dict(sheet=info[0]["name"], rows=sum(i["rows"] for i in info), sheets=len(info), sheet_info=info)


def extract(filename: str, data: bytes) -> dict:
    if len(data) > MAX_BYTES:
        raise ApiError(413, "file_too_large", f"The file is {len(data) / 1e6:.1f} MB; the limit is {MAX_BYTES // (1024 * 1024)} MB")
    if not data:
        raise BadRequest("The file is empty")
    ext = PurePath(filename or "").suffix.lower()
    meta: dict = {}
    if ext == ".docx":
        text, meta = _docx(data)
    elif ext == ".pdf":
        text, meta = _pdf(data)
    elif ext == ".xlsx":
        text, meta = _xlsx(data)
    elif ext in IMAGE_EXT:
        text, meta = ocr.ocr_image(data)
    elif ext in (".html", ".htm"):
        text = _html(_decode(data))
    elif ext in TEXT_EXT:
        text = _decode(data)
    else:
        raise UnsupportedFile(ext)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("﻿")
    if not text.strip():
        raise BadRequest("The file contains no readable text")
    return dict(filename=filename, kind=ext.lstrip(".") or "txt", text=text, chars=len(text), size=len(data), meta=meta)
