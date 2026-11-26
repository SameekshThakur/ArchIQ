"""Optional OCR for scanned PDFs and images.

Needs the Tesseract program plus two Python packages (``pip install -r requirements-ocr.txt``). When any of them is missing the app still works;
scanned files are rejected with a message that says exactly what to install. Everything runs locally.
"""

from __future__ import annotations

import io
import os
import shutil
from functools import lru_cache

from app.core.errors import ApiError

MAX_OCR_PAGES = 15
WINDOWS_PATHS = (r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe")
INSTALL_HINT = (
    "OCR is not set up. Install the Tesseract program (Windows: https://github.com/UB-Mannheim/tesseract/wiki; macOS: brew install tesseract; Linux: apt install tesseract-ocr), "
    "then run: pip install -r backend/requirements-ocr.txt"
)


@lru_cache(maxsize=1)
def status() -> dict:
    """What OCR can do on this machine, for /files/supported and the doctor script."""
    try:
        import pypdfium2  # noqa: F401
        import pytesseract
        from PIL import Image  # noqa: F401
    except ImportError as e:
        return dict(available=False, reason=f"Python package missing: {e.name}")
    cmd = shutil.which("tesseract") or next((p for p in WINDOWS_PATHS if os.path.exists(p)), None)
    if not cmd:
        return dict(available=False, reason="The Tesseract program was not found")
    pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        return dict(available=True, version=str(pytesseract.get_tesseract_version()))
    except Exception as e:  # noqa: BLE001
        return dict(available=False, reason=f"Tesseract could not start: {e}")


def available() -> bool:
    return bool(status()["available"])


def _require() -> None:
    if not available():
        raise ApiError(422, "ocr_unavailable", f"This file has no selectable text and needs OCR. {INSTALL_HINT}", dict(reason=status().get("reason")))


def ocr_image(data: bytes) -> tuple[str, dict]:
    _require()
    import pytesseract
    from PIL import Image, UnidentifiedImageError

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as e:
        raise ApiError(400, "bad_request", "This image could not be read") from e
    text = pytesseract.image_to_string(img.convert("L"), timeout=60)
    return text, dict(ocr=True, pages=1)


def ocr_pdf(data: bytes) -> tuple[str, dict]:
    _require()
    import pypdfium2 as pdfium
    import pytesseract

    pdf = pdfium.PdfDocument(data)
    total = len(pdf)
    texts: list[str] = []
    for i in range(min(total, MAX_OCR_PAGES)):
        img = pdf[i].render(scale=2.5).to_pil().convert("L")  # about 180 dpi: a good accuracy/speed balance
        texts.append(pytesseract.image_to_string(img, timeout=60))
    meta = dict(ocr=True, pages=total, pages_read=len(texts))
    if total > MAX_OCR_PAGES:
        meta["note"] = f"Only the first {MAX_OCR_PAGES} of {total} pages were read."
    return "\n\n".join(texts), meta
