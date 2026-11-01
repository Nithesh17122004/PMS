"""First-time deployment setup: create the first clinic and administrator.

Setup is only allowed when the database contains no users. The check runs
against the actual database inside a transaction, with a PostgreSQL advisory
lock to serialise concurrent attempts.
"""
from __future__ import annotations

from sqlalchemy import text

from ..auth.security import validate_password_strength
from ..extensions import db
from ..models import User
from ..utils.errors import ConflictError, ValidationError
from .clinic_service import create_clinic


def setup_required() -> bool:
    """Return True when no user account exists yet (first-time setup)."""
    return User.query.count() == 0


def perform_setup(payload: dict, *, request_ip: str | None = None) -> tuple:
    """Create the first clinic + admin atomically. Raises on any validation issue."""
    # Open a transaction and serialise concurrent setup attempts.
    try:
        if db.engine.dialect.name == "postgresql":
            db.session.execute(text("SELECT pg_advisory_xact_lock(987654321)"))

        if User.query.count() > 0:
            db.session.rollback()
            raise ConflictError("Setup has already been completed.")

        clinic_name = (payload.get("clinic_name") or "").strip()
        clinic_email = (payload.get("clinic_email") or "").strip()
        admin_name = (payload.get("admin_name") or "").strip()
        admin_email = (payload.get("admin_email") or "").strip()
        password = payload.get("password") or ""
        confirm = payload.get("confirm_password") or ""

        if not clinic_name:
            raise ValidationError("Clinic name is required.")
        if not clinic_email or "@" not in clinic_email:
            raise ValidationError("A valid clinic email is required.")
        if not admin_name:
            raise ValidationError("Administrator name is required.")
        if not admin_email or "@" not in admin_email:
            raise ValidationError("A valid administrator email is required.")
        if not password or password != confirm:
            raise ValidationError("Passwords do not match.")
        validate_password_strength(password)

        clinic_payload = {
            "name": clinic_name,
            "email": clinic_email,
            "phone": (payload.get("clinic_phone") or "").strip() or None,
            "address_line1": (payload.get("clinic_address") or "").strip() or None,
            "admin_name": admin_name,
            "admin_email": admin_email,
            "admin_password": password,
            "timezone": "Asia/Kolkata",
            "currency": "INR",
            "token_mode": "doctor",
        }
        clinic, admin, _ = create_clinic(clinic_payload, actor=None, commit=False)
        db.session.commit()
        return clinic, admin
    except Exception:
        db.session.rollback()
        raise
