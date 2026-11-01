"""Application configuration.

Secrets are read from environment variables only. Development has safe,
convenience defaults; production refuses to boot with weak defaults.
"""
from __future__ import annotations

import os
from datetime import timedelta


def _bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return "sqlite:///clinicflow.db"
    # Render / Heroku style URLs use postgres://; SQLAlchemy requires postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    # Ensure TLS for remote PostgreSQL (e.g. Render) when not already specified.
    if url.startswith("postgresql://") and "sslmode" not in url.lower():
        try:
            from sqlalchemy.engine import make_url

            parsed = make_url(url)
            host = (parsed.host or "").lower()
            if host and host not in {"localhost", "127.0.0.1", "::1"}:
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}sslmode=require"
        except Exception:  # noqa: BLE001
            pass
    return url


class BaseConfig:
    APP_NAME = "ClinicFlow"
    APP_VERSION = "1.0.2"
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-change-me")
    DATABASE_URL = _database_url()
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }
    if DATABASE_URL.startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {
            "timeout": 30,
            "check_same_thread": False,
        }
    else:
        SQLALCHEMY_ENGINE_OPTIONS.update(
            {
                "pool_size": int(os.environ.get("DB_POOL_SIZE", "10")),
                "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "20")),
                "pool_recycle": 280,
            }
        )

    # Security
    SESSION_COOKIE_NAME = "clinicflow_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get("SESSION_HOURS", "8")))
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    CSRF_ENABLED = True
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "10")) * 1024 * 1024
    PASSWORD_MIN_LENGTH = 10
    LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCK_MINUTES = int(os.environ.get("LOGIN_LOCK_MINUTES", "15"))
    RESET_TOKEN_MINUTES = int(os.environ.get("RESET_TOKEN_MINUTES", "30"))

    # Field-level encryption. Derive from SECRET_KEY if no dedicated key is
    # supplied so local development works; production must set a stable key.
    FIELD_ENCRYPTION_KEY = os.environ.get("FIELD_ENCRYPTION_KEY", "")
    BLIND_INDEX_KEY = os.environ.get("BLIND_INDEX_KEY", "")
    if not FIELD_ENCRYPTION_KEY:
        import base64
        import hashlib

        digest = hashlib.sha256(("enc:" + SECRET_KEY).encode()).digest()
        FIELD_ENCRYPTION_KEY = base64.urlsafe_b64encode(digest).decode()
    if not BLIND_INDEX_KEY:
        import hashlib

        BLIND_INDEX_KEY = hashlib.sha256(("idx:" + SECRET_KEY).encode()).hexdigest()

    # Uploads
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", os.path.join(os.getcwd(), "instance", "uploads")
    )
    ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp", "doc", "docx"}
    MAX_DOCUMENT_MB = 10

    # Rate limiting
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "1000 per hour")
    RATELIMIT_HEADERS_ENABLED = True

    # Mail / messaging providers. When unset, messages are recorded as skipped
    # rather than pretending they were delivered (demo mode simulates delivery).
    MAIL_PROVIDER = os.environ.get("MAIL_PROVIDER", "smtp" if os.environ.get("SMTP_HOST") else "console")
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_USE_TLS = _bool("SMTP_USE_TLS", True)
    MAIL_FROM = os.environ.get("MAIL_FROM", "no-reply@clinicflow.app")
    MAIL_FROM_NAME = os.environ.get("MAIL_FROM_NAME", "ClinicFlow")

    SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "")  # twilio
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")

    WHATSAPP_PROVIDER = os.environ.get("WHATSAPP_PROVIDER", "")  # meta
    WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "")
    WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")

    # Background jobs
    ENABLE_SCHEDULER = _bool("ENABLE_SCHEDULER", False)
    SCHEDULER_INTERVAL_MINUTES = int(os.environ.get("SCHEDULER_INTERVAL_MINUTES", "15"))
    REMINDER_BATCH_SIZE = int(os.environ.get("REMINDER_BATCH_SIZE", "200"))

    # Demo / platform
    DEMO_MODE = _bool("DEMO_MODE", False)
    DEMO_NOTICE = "Demonstration environment — all data is fictional."
    BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")
    SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support@clinicflow.app")

    # Logging
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_JSON = _bool("LOG_JSON", False)


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    CSRF_ENABLED = True


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
        "pool_pre_ping": True,
    }
    CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    ENABLE_SCHEDULER = False
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    SECRET_KEY = "test-secret-key-for-clinicflow-tests-only"
    FIELD_ENCRYPTION_KEY = "zJ8QeY7mB1nX4pL6vT2sR9wK3cF5hD0aG7uJ1oM8qE4="
    BLIND_INDEX_KEY = "test-blind-index-key"


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
