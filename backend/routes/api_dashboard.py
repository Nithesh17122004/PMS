from __future__ import annotations

from flask import Blueprint, g, request

from ..models import Doctor
from ..permissions.rbac import permission_required
from ..permissions.tenant import current_clinic, get_scoped_or_404
from ..services.dashboard_service import dashboard_data, platform_data
from ..utils.responses import ok

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/api/dashboard")
@permission_required("dashboard.view")
def dashboard():
    clinic = current_clinic()
    doctor_id = request.args.get("doctor_id") or None
    if g.user.doctor_profile and "tokens.manage_all" not in g.permissions:
        doctor_id = g.user.doctor_profile.id
    elif doctor_id:
        get_scoped_or_404(Doctor, doctor_id)
    return ok(dashboard_data(clinic, user=g.user, doctor_id=doctor_id))


@dashboard_bp.get("/api/platform/dashboard")
@permission_required("platform.view")
def platform_dashboard():
    return ok(platform_data())
