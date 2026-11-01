from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, g, redirect, render_template, request, session, url_for
from flask_limiter.util import get_remote_address

from ..extensions import db, limiter
from ..models import PasswordResetToken, User
from ..services.notification_service import send_password_reset
from ..utils.crypto import blind_index, normalize_email
from ..utils.datetime_utils import as_utc
from ..utils.errors import ApiError, ValidationError
from ..utils.responses import ok
from ..utils.serializers import user_me
from .security import (
    audit,
    csrf_token,
    establish_session,
    generate_reset_token,
    hash_reset_token,
    hash_password,
    mark_login_failure,
    mark_login_success,
    validate_password_strength,
    verify_password,
)

auth_bp = Blueprint("auth", __name__)

# Constant-time-ish dummy hash so unknown accounts take similar time to reject.
_DUMMY_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEe.7YVbH0NQ0VvJ8sD4h7dQx1lR0m3z3G2"


@auth_bp.get("/login")
def login_page():
    if g.get("user"):
        return redirect(url_for("pages.app_home"))
    return render_template("auth/login.html", page_title="Sign in")


@auth_bp.get("/reset-password")
def reset_password_page():
    token = request.args.get("token", "")
    return render_template("auth/reset_password.html", token=token, page_title="Reset password")


@auth_bp.post("/api/auth/login")
@limiter.limit("10 per minute")
def api_login():
    payload = request.get_json(silent=True) or request.form
    email = normalize_email(payload.get("email"))
    password = payload.get("password") or ""
    if not email or not password:
        raise ApiError("invalid_credentials", "Invalid email or password.", 401)
    user = User.query.filter_by(email=email).first()
    password_ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok:
        mark_login_failure(user, email)
        db.session.commit()
        raise ApiError("invalid_credentials", "Invalid email or password.", 401)
    if user.is_locked:
        db.session.commit()
        raise ApiError(
            "account_locked",
            "Too many failed attempts. This account is temporarily locked. Try again later.",
            423,
        )
    if not user.is_active:
        audit("auth.login_disabled", "user", user.id, clinic_id=user.clinic_id)
        db.session.commit()
        raise ApiError("account_disabled", "This account has been disabled. Contact your administrator.", 403)
    if user.clinic and not user.clinic.is_active:
        raise ApiError("clinic_suspended", "This clinic account is suspended. Contact support.", 403)
    mark_login_success(user)
    establish_session(user)
    db.session.commit()
    return ok({"user": user_me(user), "redirect": "/app"})


@auth_bp.post("/api/auth/logout")
def api_logout():
    user = g.get("user")
    if user:
        audit("auth.logout", "user", user.id)
        db.session.commit()
    session.clear()
    return ok({"redirect": "/login"})


@auth_bp.get("/api/auth/me")
def api_me():
    if not g.get("user"):
        raise ApiError("unauthorized", "Authentication required.", 401)
    return ok({"user": user_me(g.user)})


@auth_bp.get("/api/auth/csrf")
def api_csrf():
    return ok({"csrf_token": csrf_token()})


@auth_bp.post("/api/auth/change-password")
def api_change_password():
    user = g.get("user")
    if not user:
        raise ApiError("unauthorized", "Authentication required.", 401)
    payload = request.get_json(silent=True) or {}
    current = payload.get("current_password") or ""
    new_password = payload.get("new_password") or ""
    if not verify_password(current, user.password_hash):
        raise ValidationError("Your current password is incorrect.")
    validate_password_strength(new_password)
    if verify_password(new_password, user.password_hash):
        raise ValidationError("Choose a password you have not used before.")
    user.password_hash = hash_password(new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    user.must_change_password = False
    session["login_at"] = datetime.now(timezone.utc).isoformat()
    audit("auth.password_changed", "user", user.id)
    db.session.commit()
    return ok({"message": "Password updated successfully."})


@auth_bp.post("/api/auth/profile")
def api_update_profile():
    user = g.get("user")
    if not user:
        raise ApiError("unauthorized", "Authentication required.", 401)
    payload = request.get_json(silent=True) or {}
    if "notification_email" in payload:
        user.notification_email = bool(payload["notification_email"])
    if "notification_in_app" in payload:
        user.notification_in_app = bool(payload["notification_in_app"])
    if payload.get("phone") is not None:
        user.phone = str(payload.get("phone"))[:30]
    audit("auth.profile_updated", "user", user.id)
    db.session.commit()
    return ok({"user": user_me(user)})


@auth_bp.post("/api/auth/forgot-password")
@limiter.limit("5 per minute")
def api_forgot_password():
    payload = request.get_json(silent=True) or request.form
    email = normalize_email(payload.get("email"))
    generic = {"message": "If an account exists for that email, a reset link has been sent."}
    if not email:
        return ok(generic)
    user = User.query.filter_by(email=email, is_active=True).first()
    if user:
        raw, token_hash = generate_reset_token()
        expires = datetime.now(timezone.utc) + timedelta(
            minutes=current_app.config.get("RESET_TOKEN_MINUTES", 30)
        )
        PasswordResetToken.query.filter_by(user_id=user.id, used_at=None).update(
            {"used_at": datetime.now(timezone.utc)}
        )
        db.session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires,
                requested_ip=get_remote_address(),
            )
        )
        reset_url = f"{current_app.config.get('BASE_URL', request.host_url.rstrip('/'))}/reset-password?token={raw}"
        send_password_reset(user, reset_url)
        audit(
            "auth.password_reset_requested",
            "user",
            user.id,
            {"email_hash": blind_index(email)},
            clinic_id=user.clinic_id,
        )
        db.session.commit()
        if current_app.config.get("DEMO_MODE"):
            generic["demo_reset_url"] = reset_url
    else:
        audit("auth.password_reset_unknown", details={"email_hash": blind_index(email)})
        db.session.commit()
    return ok(generic)


@auth_bp.post("/api/auth/reset-password")
@limiter.limit("10 per minute")
def api_reset_password():
    payload = request.get_json(silent=True) or request.form
    raw = payload.get("token") or ""
    new_password = payload.get("new_password") or ""
    if not raw:
        raise ValidationError("Reset token is required.")
    validate_password_strength(new_password)
    token = PasswordResetToken.query.filter_by(token_hash=hash_reset_token(raw)).first()
    now = datetime.now(timezone.utc)
    if token is None or token.used_at is not None:
        raise ApiError("invalid_token", "This reset link is invalid or has already been used.", 400)
    if as_utc(token.expires_at) < now:
        raise ApiError("expired_token", "This reset link has expired. Request a new one.", 400)
    user = db.session.get(User, token.user_id)
    if user is None or not user.is_active:
        raise ApiError("invalid_token", "This reset link is no longer valid.", 400)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
    user.failed_login_attempts = 0
    user.locked_until = None
    user.must_change_password = False
    token.used_at = now
    audit("auth.password_reset_completed", "user", user.id, clinic_id=user.clinic_id, user_id=user.id)
    db.session.commit()
    return ok({"message": "Password reset successfully. You can now sign in."})
