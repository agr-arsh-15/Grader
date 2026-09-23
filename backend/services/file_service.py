"""File validation and storage service."""
import os
import uuid
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile, status

from backend.config import settings

# Allowed extensions per upload type
ALLOWED_ASSIGNMENT_ZIP = {".zip"}
ALLOWED_SUBMISSION_CODE = {".zip"}
ALLOWED_LOG_FILES = {".txt", ".md", ".json", ".log"}

_MAX_BYTES = settings.max_upload_size_mb * 1024 * 1024


def _upload_root() -> Path:
    p = Path(settings.upload_dir)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent.parent / p
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def _check_extension(filename: str, allowed: set[str]) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File type '{suffix}' not allowed. Allowed: {sorted(allowed)}",
        )
    return suffix


async def _save_upload(upload: UploadFile, dest: Path) -> None:
    """Stream upload to dest, enforcing max size."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    async with aiofiles.open(dest, "wb") as f:
        while chunk := await upload.read(1024 * 256):  # 256 KB chunks
            total += len(chunk)
            if total > _MAX_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds maximum size of {settings.max_upload_size_mb} MB",
                )
            await f.write(chunk)


async def save_assignment_zip(upload: UploadFile, assignment_id: uuid.UUID) -> str:
    """Saves assignment zip. Returns path relative to upload root."""
    _check_extension(upload.filename or "file.zip", ALLOWED_ASSIGNMENT_ZIP)
    rel = Path("assignments") / str(assignment_id) / "assignment.zip"
    await _save_upload(upload, _upload_root() / rel)
    return str(rel)


async def save_bug_manifest(upload: UploadFile, assignment_id: uuid.UUID) -> str:
    """Saves bug manifest JSON. Returns path relative to upload root."""
    suffix = Path(upload.filename or "manifest.json").suffix.lower()
    if suffix != ".json":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Bug manifest must be a .json file",
        )
    rel = Path("assignments") / str(assignment_id) / "bug_manifest.json"
    await _save_upload(upload, _upload_root() / rel)
    return str(rel)


async def save_submission_code(upload: UploadFile, submission_id: uuid.UUID) -> str:
    """Saves candidate code zip. Returns relative path."""
    _check_extension(upload.filename or "code.zip", ALLOWED_SUBMISSION_CODE)
    rel = Path("submissions") / str(submission_id) / "code.zip"
    await _save_upload(upload, _upload_root() / rel)
    return str(rel)


async def save_log_file(upload: UploadFile, submission_id: uuid.UUID, index: int) -> str:
    """Saves a single log file. Returns relative path."""
    suffix = _check_extension(upload.filename or f"log_{index}.txt", ALLOWED_LOG_FILES)
    rel = Path("submissions") / str(submission_id) / f"log_{index}{suffix}"
    await _save_upload(upload, _upload_root() / rel)
    return str(rel)


def absolute_path(rel: str) -> str:
    """Convert an upload path to an absolute filesystem path string."""
    p = Path(rel)
    if p.is_absolute():
        return str(p.resolve())
    return str((_upload_root() / p).resolve())


def get_assignment_zip_path(rel: str) -> Path:
    """Get absolute Path object for an assignment zip."""
    p = Path(rel)
    if p.is_absolute():
        return p.resolve()
    return (_upload_root() / p).resolve()
