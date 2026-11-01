from __future__ import annotations

from flask import Blueprint, g, redirect, render_template, url_for

from ..auth.security import csrf_token

auth_extra_bp = Blueprint("auth_extra", __name__)


@auth_extra_bp.get("/forgot-password")
def forgot_password_page():
    if g.get("user"):
        return redirect(url_for("pages.app_home"))
    return render_template("auth/forgot_password.html", page_title="Forgot password")
