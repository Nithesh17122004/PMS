from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from flask import current_app, g, has_request_context, request, session

from ..extensions import db
from ..models import AuditLog, Clinic, User
from ..utils.crypto import blind_index
from ..utils.errors import ApiError, ValidationError


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str) -> None:
    minimum = current_app.config.get("PASSWORD_MIN_LENGTH", 10)
    if not password or len(password) < minimum:
        raise ValidationError(f"Password must be at least {minimum} characters long.")
    if len(password) > 72:
        raise ValidationError("Password must be 72 characters or fewer.")
    checks = [
        (re.search(r"[A-Z]", password), "an uppercase letter"),
        (re.search(r"[a-z]", password), "a lowercase letter"),
        (re.search(r"\d", password), "a number"),
        (re.search(r"[^A-Za-z0-9]", password), "a symbol"),
    ]
    missing = [label for ok, label in checks if not ok]
    if missing:
        raise ValidationError("Password must include " + ", ".join(missing) + ".")


def generate_reset_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(40)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def csrf_valid() -> bool:
    if not current_app.config.get("CSRF_ENABLED", True):
        return True
    expected = session.get("_csrf_token")
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("_csrf_token")
    if not supplied:
        payload = request.get_json(silent=True) or {}
        supplied = payload.get("_csrf_token")
    if not expected or not supplied:
        return False
    return secrets.compare_digest(str(expected), str(supplied))


def load_logged_in_user() -> None:
    user_id = session.get("user_id")
    g.user = None
    g.clinic = None
    g.permissions = set()
    if not user_id:
        return
def load_logged_in_user() -> None:
    user_id = session.get("user_id")
    g.user = None
    g.clinic = None
    g.permissions = set()
    if not user_id:
        return
    try:
        user = db.session.get(User, user_id)
    except Exception:  # noqa: BLE001
        # Database may not be initialized or temporarily unavailable.
        session.clear()
        return
    if user is None or not user.is_active or user.is_locked:
        session.clear()
        return
    login_at = session.get("login_at")
    if login_at and user.password_changed_at:
        changed_at = user.password_changed_at
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=timezone.utc)
        try:
            if datetime.fromisoformat(login_at) < changed_at:
                session.clear()
                return
        except (TypeError, ValueError):
            pass
    if user.clinic_id:
        clinic = db.session.get(Clinic, user.clinic_id)
        if clinic is None or not clinic.is_active:
            session.clear()
            return
        g.clinic = clinic
    g.user = user
    g.permissions = user.permission_codes()


def audit(
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict | None = None,
    clinic_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Write a non-PHI audit event. Never store medical free text here."""
    actor = getattr(g, "user", None)
    if has_request_context():
        ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "")[:64]
        user_agent = (request.user_agent.string or "")[:255] if request.user_agent else None
    else:
        ip_address = None
        user_agent = "system"
    log = AuditLog(
        clinic_id=clinic_id or (getattr(g, "clinic", None).id if getattr(g, "clinic", None) else None),
        user_id=user_id or (actor.id if actor else None),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details or {},
    )
    db.session.add(log)


def mark_login_success(user: User) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = (
        request.headers.get("X-Forwarded-For", request.remote_addr or "")[:64]
        if has_request_context()
        else None
    )
    audit("auth.login", "user", user.id, {"role": user.role.slug if user.role else None})


def mark_login_failure(user: User | None, email: str) -> None:
    max_attempts = current_app.config.get("LOGIN_MAX_ATTEMPTS", 5)
    lock_minutes = current_app.config.get("LOGIN_LOCK_MINUTES", 15)
    if user:
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= max_attempts:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=lock_minutes)
        audit(
            "auth.login_failed",
            "user",
            user.id,
            {"attempts": user.failed_login_attempts, "locked": user.is_locked},
            clinic_id=user.clinic_id,
        )
    else:
        audit("auth.login_failed_unknown", details={"email_hash": blind_index(email)})


def establish_session(user: User) -> None:
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    session["_csrf_token"] = secrets.token_urlsafe(32)
    session["clinic_id"] = user.clinic_id
    session["login_at"] = datetime.now(timezone.utc).isoformat()
