from __future__ import annotations

from flask import g, request, session

from ..utils.errors import ApiError
from ..utils.responses import fail
from .security import csrf_valid, load_logged_in_user

PUBLIC_API_PATHS = {
    "/api/auth/login",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/csrf",
    "/api/setup",
}

CSRF_EXEMPT_PATHS = {
    "/api/auth/login",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/csrf",
}

PASSWORD_CHANGE_ALLOWED = {
    "/api/auth/me",
    "/api/auth/logout",
    "/api/auth/change-password",
    "/api/auth/csrf",
}


def register_hooks(app):
    @app.before_request
    def load_context_and_protect():
        load_logged_in_user()

        path = request.path
        is_api = path.startswith("/api/")
        is_public_api = path.startswith("/api/public/") or path in PUBLIC_API_PATHS
        unsafe = request.method not in ("GET", "HEAD", "OPTIONS")
        is_public_api_path = path.startswith("/api/public/") or path in PUBLIC_API_PATHS

        if unsafe and not csrf_valid() and path not in CSRF_EXEMPT_PATHS:
            if is_api:
                return fail("csrf_failed", "Your session security token is missing or expired. Refresh the page.", 403)
            return "Security token missing or invalid.", 403

        if is_api and not is_public_api_path and request.method != "OPTIONS":
            if not g.get("user"):
                return fail("unauthorized", "Authentication required.", 401)
            if not g.user.is_super_admin and g.get("clinic") is None:
                return fail("clinic_required", "Your account is not assigned to an active clinic.", 403)
            if g.user.must_change_password and path not in PASSWORD_CHANGE_ALLOWED:
                return fail(
                    "password_change_required",
                    "You must change your password before continuing.",
                    428,
                )

        if not is_api and path.startswith("/app"):
            if not g.get("user"):
                from flask import redirect, url_for

                return redirect(url_for("auth.login_page"))
            if not g.user.is_super_admin and g.get("clinic") is None:
                return "Your account is not assigned to an active clinic.", 403

    @app.after_request
    def apply_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
        )
        if request.path.startswith("/api/") or request.path.startswith("/app"):
            response.headers.setdefault("Cache-Control", "no-store")
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response
