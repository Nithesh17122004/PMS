from __future__ import annotations

import io
import os
import uuid
import zipfile

from flask import current_app
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

from .errors import ValidationError

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def _extension(filename: str) -> str:
    return secure_filename(filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""


def validate_upload(file, allowed=None) -> str:
    if file is None or not file.filename:
        raise ValidationError("Choose a file to upload.")
    ext = _extension(file.filename)
    allowed = allowed or current_app.config.get("ALLOWED_UPLOAD_EXTENSIONS", IMAGE_EXTENSIONS | {"pdf"})
    if ext not in allowed:
        raise ValidationError(f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}.")
    head = file.stream.read(16)
    file.stream.seek(0)
    if ext == "pdf" and not head.startswith(b"%PDF"):
        raise ValidationError("The uploaded file is not a valid PDF.")
    if ext in IMAGE_EXTENSIONS:
        try:
            image = Image.open(file.stream)
            image.verify()
            file.stream.seek(0)
        except (UnidentifiedImageError, Exception):
            raise ValidationError("The uploaded image is invalid or corrupted.")
    if ext == "docx":
        try:
            file.stream.seek(0)
            with zipfile.ZipFile(file.stream) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ValidationError("The uploaded file is not a valid DOCX document.")
            file.stream.seek(0)
        except zipfile.BadZipFile:
            raise ValidationError("The uploaded file is not a valid DOCX document.")
    return ext


def save_document(file, clinic_id: str) -> tuple[str, str, int]:
    ext = validate_upload(file)
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "documents", clinic_id)
    os.makedirs(folder, exist_ok=True)
    stored = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(folder, stored)
    file.save(path)
    size = os.path.getsize(path)
    if size > current_app.config.get("MAX_DOCUMENT_MB", 10) * 1024 * 1024:
        os.remove(path)
        raise ValidationError("The uploaded file exceeds the size limit.")
    return f"documents/{clinic_id}/{stored}", stored, size


def save_lab_attachment(file, clinic_id: str) -> tuple[str, str, int]:
    ext = validate_upload(file, {"pdf", "png", "jpg", "jpeg", "webp"})
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "lab", clinic_id)
    os.makedirs(folder, exist_ok=True)
    stored = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(folder, stored)
    file.save(path)
    return f"lab/{clinic_id}/{stored}", stored, os.path.getsize(path)


def save_logo(file, clinic_id: str) -> str:
    if file is None or not file.filename:
        raise ValidationError("Choose an image for the clinic logo.")
    ext = _extension(file.filename)
    if ext not in IMAGE_EXTENSIONS:
        raise ValidationError("Clinic logos must be PNG, JPG or WebP images.")
    try:
        image = Image.open(file.stream)
        image = image.convert("RGBA")
        image.thumbnail((640, 640))
        folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "logos")
        os.makedirs(folder, exist_ok=True)
        filename = f"{clinic_id}.png"
        image.save(os.path.join(folder, filename), "PNG", optimize=True)
        return f"logos/{filename}"
    except (UnidentifiedImageError, OSError):
        raise ValidationError("The uploaded logo is not a valid image.")


def absolute_upload_path(relative_path: str) -> str | None:
    if not relative_path:
        return None
    base = os.path.abspath(current_app.config["UPLOAD_FOLDER"])
    candidate = os.path.abspath(os.path.join(base, relative_path))
    if not candidate.startswith(base + os.sep):
        return None
    return candidate if os.path.exists(candidate) else None
