from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import text

from ..extensions import db
from ..models import Clinic
from ..utils.responses import ok

pages_bp = Blueprint("pages", __name__)


@pages_bp.get("/")
def index():
    if g.get("user"):
        return redirect(url_for("pages.app_home"))
    from ..models import User

    if User.query.count() == 0:
        return redirect(url_for("pages.setup_page"))
    return redirect(url_for("auth.login_page"))


@pages_bp.get("/setup")
def setup_page():
    from ..models import User

    if User.query.count() > 0:
        return redirect(url_for("auth.login_page"))
    return render_template("auth/setup.html", page_title="First-time setup")


@pages_bp.get("/app")
def app_home():
    return render_template(
        "app/app.html",
        page_title="ClinicFlow",
        demo_mode=current_app.config.get("DEMO_MODE"),
    )


@pages_bp.get("/display/<display_key>")
def public_display(display_key):
    clinic = Clinic.query.filter_by(display_key=display_key, is_active=True).first()
    if clinic is None or not clinic.settings or not clinic.settings.public_display_enabled:
        abort(404)
    return render_template(
        "public/display.html",
        clinic=clinic,
        display_key=display_key,
        page_title=f"{clinic.name} Queue",
    )


@pages_bp.get("/healthz")
def healthz():
    try:
        db.session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    status = 200 if db_ok else 503
    response = jsonify(
        {
            "status": "ok" if db_ok else "degraded",
            "database": "ok" if db_ok else "unavailable",
            "version": current_app.config.get("APP_VERSION"),
            "time": datetime.now(timezone.utc).isoformat(),
        }
    )
    response.status_code = status
    return response


@pages_bp.get("/readyz")
def readyz():
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        response = jsonify({"status": "not_ready"})
        response.status_code = 503
        return response
    return jsonify({"status": "ready"})


@pages_bp.get("/robots.txt")
def robots():
    return "User-agent: *\nDisallow: /\n", 200, {"Content-Type": "text/plain"}
