from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from logging.handlers import RotatingFileHandler

from flask import Flask, g, request
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from .config import CONFIG_MAP
from .extensions import db, limiter, migrate


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
        }
        for key in ("request_id", "method", "path", "status", "duration_ms", "user_id", "ip"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _configure_logging(app: Flask) -> None:
    level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if app.config.get("LOG_JSON"):
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    handler.setLevel(level)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    app.logger.handlers = [handler]
    app.logger.setLevel(level)
    # Avoid duplicate werkzeug logs at INFO in production.
    logging.getLogger("werkzeug").setLevel(logging.WARNING if not app.debug else logging.INFO)


def _validate_production_config(app: Flask) -> None:
    if app.config.get("ENV") == "production" or os.environ.get("APP_ENV") == "production":
        if app.config["SECRET_KEY"].startswith("dev-only"):
            raise RuntimeError("SECRET_KEY must be set in production.")
        if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
            raise RuntimeError("A PostgreSQL DATABASE_URL is required in production.")
        if not os.environ.get("FIELD_ENCRYPTION_KEY"):
            app.logger.warning(
                "FIELD_ENCRYPTION_KEY is not set; it is derived from SECRET_KEY. "
                "Set a stable dedicated key before storing real patient data."
            )


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, connection_record):
    try:
        import sqlite3

        if isinstance(dbapi_connection, sqlite3.Connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()
    except Exception:
        pass


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )
    env_name = config_name or os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or "development"
    if env_name not in CONFIG_MAP:
        env_name = "development"
    app.config.from_object(CONFIG_MAP[env_name])
    app.config["ENV"] = env_name
    app.config["APP_ENV"] = env_name

    _configure_logging(app)
    _validate_production_config(app)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    # Importing models registers all metadata before migrations/queries run.
    from . import models  # noqa: F401

    from .auth.hooks import register_hooks
    from .auth.routes import auth_bp
    from .routes.pages import pages_bp

    register_hooks(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)

    _register_api_blueprints(app)
    _register_error_handlers(app)
    _register_template_helpers(app)
    _register_request_logging(app)

    from .commands import register_cli

    register_cli(app)

    if app.config.get("ENABLE_SCHEDULER") and not app.config.get("TESTING"):
        from .tasks.scheduler import start_scheduler

        start_scheduler(app)

    return app


def _register_api_blueprints(app: Flask) -> None:
    """Imported lazily so the app factory stays free of circular imports."""
    from .routes.api_admin import admin_bp
    from .routes.api_appointments import appointments_bp
    from .routes.api_auth_extra import auth_extra_bp
    from .routes.api_billing import billing_bp
    from .routes.api_clinic import clinic_bp
    from .routes.api_consultations import consultations_bp
    from .routes.api_dashboard import dashboard_bp
    from .routes.api_doctors import doctors_bp
    from .routes.api_followups import followups_bp
    from .routes.api_lab import lab_bp
    from .routes.api_notifications import notifications_bp
    from .routes.api_patients import patients_bp
    from .routes.api_pharmacy import pharmacy_bp
    from .routes.api_public import public_bp
    from .routes.api_reports import reports_bp
    from .routes.api_tokens import tokens_bp

    for blueprint in (
        dashboard_bp,
        patients_bp,
        doctors_bp,
        appointments_bp,
        tokens_bp,
        followups_bp,
        consultations_bp,
        billing_bp,
        pharmacy_bp,
        lab_bp,
        reports_bp,
        notifications_bp,
        clinic_bp,
        admin_bp,
        public_bp,
        auth_extra_bp,
    ):
        app.register_blueprint(blueprint)


def _register_error_handlers(app: Flask) -> None:
    from .utils.errors import ApiError
    from .utils.responses import fail

    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        return fail(error.code, error.message, error.status, error.details)

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(error: IntegrityError):
        db.session.rollback()
        app.logger.warning("Database integrity error on %s", request.path)
        if request.path.startswith("/api/"):
            return fail("conflict", "The record could not be saved because it conflicts with existing data.", 409)
        return "A database conflict occurred.", 409

    @app.errorhandler(404)
    def handle_404(error):
        if request.path.startswith("/api/"):
            return fail("not_found", "The requested resource was not found.", 404)
        return (
            "<!doctype html><html><head><title>Not found</title></head><body "
            "style=\"font-family:system-ui;padding:48px\"><h1>Page not found</h1>"
            "<p><a href=\"/\">Return to ClinicFlow</a></p></body></html>",
            404,
        )

    @app.errorhandler(405)
    def handle_405(error):
        if request.path.startswith("/api/"):
            return fail("method_not_allowed", "This method is not allowed.", 405)
        return "Method not allowed.", 405

    @app.errorhandler(413)
    def handle_413(error):
        return fail("file_too_large", "The uploaded file is too large.", 413)

    @app.errorhandler(429)
    def handle_429(error):
        return fail("rate_limited", "Too many requests. Please wait and try again.", 429)

    @app.errorhandler(500)
    def handle_500(error):
        db.session.rollback()
        if app.config.get("TESTING"):
            raise error
        app.logger.exception("Unhandled server error on %s", request.path)
        if request.path.startswith("/api/"):
            return fail("server_error", "An unexpected server error occurred.", 500)
        return "An unexpected server error occurred.", 500


def _register_template_helpers(app: Flask) -> None:
    from .auth.security import csrf_token
    from .utils.datetime_utils import to_clinic
    from .utils.serializers import iso

    @app.context_processor
    def inject_globals():
        return {
            "app_name": app.config.get("APP_NAME", "ClinicFlow"),
            "app_version": app.config.get("APP_VERSION", "1.0.0"),
            "demo_mode": app.config.get("DEMO_MODE", False),
            "demo_notice": app.config.get("DEMO_NOTICE", ""),
            "current_user": g.get("user"),
            "current_clinic": g.get("clinic"),
            "csrf_token": csrf_token,
        }

    @app.template_filter("money")
    def money_filter(value, currency=None):
        try:
            amount = float(value or 0)
        except (TypeError, ValueError):
            amount = 0
        code = currency or (g.clinic.settings.currency if g.get("clinic") and g.clinic.settings else "INR")
        symbol = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "AED": "AED "}.get(code, code + " ")
        return f"{symbol}{amount:,.2f}"

    @app.template_filter("clinic_dt")
    def clinic_dt_filter(value, fmt="%d %b %Y, %I:%M %p"):
        clinic = g.get("clinic")
        if not value:
            return "—"
        if clinic:
            value = to_clinic(value, clinic)
        return value.strftime(fmt) if value else "—"

    @app.template_filter("initials")
    def initials_filter(name):
        parts = [p for p in str(name or "").split() if p]
        return "".join(p[0].upper() for p in parts[:2]) or "U"

    @app.template_global("asset")
    def asset(path):
        return f"/static/{path}?v={app.config.get('APP_VERSION', '1')}"


def _register_request_logging(app: Flask) -> None:
    @app.before_request
    def start_timer():
        g.request_start = time.perf_counter()
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]

    @app.after_request
    def log_request(response):
        duration = int((time.perf_counter() - getattr(g, "request_start", time.perf_counter())) * 1000)
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        if request.path not in ("/healthz", "/readyz") and not request.path.startswith("/static/"):
            app.logger.info(
                "%s %s %s %sms",
                request.method,
                request.path,
                response.status_code,
                duration,
                extra={
                    "request_id": getattr(g, "request_id", ""),
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": duration,
                    "user_id": getattr(getattr(g, "user", None), "id", None),
                    "ip": request.headers.get("X-Forwarded-For", request.remote_addr or "")[:64],
                },
            )
        return response
