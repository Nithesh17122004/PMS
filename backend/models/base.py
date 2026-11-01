from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..extensions import db


def uuid4_str() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; treat stored values as UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class UUIDMixin:
    id = db.Column(db.String(36), primary_key=True, default=uuid4_str)


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class ClinicScopedMixin:
    clinic_id = db.Column(
        db.String(36),
        db.ForeignKey("clinics.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


class SoftDeleteMixin:
    is_active = db.Column(db.Boolean, nullable=False, default=True)
