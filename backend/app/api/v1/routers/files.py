"""File upload: extract readable text so any module can analyse a real document. Also serves the bundled demo files."""

import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from app.core.config import BACKEND_ROOT
from app.core.errors import BadRequest, NotFound
from app.services import files, ocr

router = APIRouter(tags=["files"])


@router.get("/files/supported")
def supported() -> dict:
    return dict(extensions=files.SUPPORTED, max_mb=files.MAX_BYTES // (1024 * 1024), ocr=ocr.status())


@router.post("/files/extract")
async def extract(file: UploadFile = File(...)) -> dict:
    data = await file.read(files.MAX_BYTES + 1)
    if file.filename is None:
        raise BadRequest("The upload has no file name")
    return files.extract(file.filename, data)


def _samples_dir() -> Path:
    return Path(os.environ.get("ARCHIQ_SAMPLES") or BACKEND_ROOT.parent / "sample-files")


def _sample_names() -> dict[str, Path]:
    d = _samples_dir()
    return {p.name: p for p in sorted(d.iterdir()) if p.is_file() and not p.name.startswith(".")} if d.is_dir() else {}


@router.get("/files/samples")
def list_samples() -> dict:
    """Demo files bundled with the project (built from the seeded estate by backend/scripts/build_samples.py)."""
    items = [dict(name=n, size=p.stat().st_size, kind=p.suffix.lstrip(".").lower()) for n, p in _sample_names().items()]
    return dict(items=items, total=len(items))


@router.get("/files/samples/{name}")
def get_sample(name: str) -> FileResponse:
    # only names that exist in the samples folder are served, so '..' and absolute paths can never match
    path = _sample_names().get(name)
    if path is None:
        raise NotFound(f"Sample file {name} not found")
    return FileResponse(path, filename=name, media_type=mimetypes.guess_type(name)[0] or "application/octet-stream")
