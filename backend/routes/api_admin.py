from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, g, request
from sqlalchemy import or_

from ..auth.security import audit, hash_password
from ..extensions import db
from ..models import AuditLog, Clinic, Doctor, Patient, Role, User
from ..permissions.rbac import permission_required
from ..services.clinic_service import create_clinic, generate_temporary_password
from ..services.dashboard_service import platform_data
from ..utils.crypto import normalize_email
from ..utils.errors import ConflictError, NotFoundError, ValidationError
from ..utils.responses import ok, pagination_meta, parse_pagination
from ..utils.serializers import audit_dict, clinic_detail, clinic_brief, staff_dict
from .helpers import json_body

admin_bp = Blueprint("admin", __name__)


def _clinic_or_404(clinic_id: str) -> Clinic:
    clinic = db.session.get(Clinic, clinic_id)
    if clinic is None:
        raise NotFoundError("Clinic not found.")
    return clinic


@admin_bp.get("/api/admin/dashboard")
@permission_required("platform.view")
def admin_dashboard():
    data = platform_data()
    data["recent_activity"] = [
        audit_dict(log)
        for log in AuditLog.query.order_by(AuditLog.created_at.desc()).limit(20).all()
    ]
    return ok(data)


@admin_bp.get("/api/admin/clinics")
@permission_required("platform.view")
def list_clinics():
    page, per_page = parse_pagination(request.args, default_per_page=30)
    query = Clinic.query
    term = (request.args.get("q") or "").strip()
    if term:
        query = query.filter(or_(Clinic.name.ilike(f"%{term}%"), Clinic.slug.ilike(f"%{term}%")))
    status = request.args.get("status")
    if status == "active":
        query = query.filter(Clinic.is_active.is_(True))
    elif status == "suspended":
        query = query.filter(Clinic.is_active.is_(False))
    query = query.order_by(Clinic.created_at.desc())
    total = query.count()
    clinics = query.offset((page - 1) * per_page).limit(per_page).all()
    data = []
    for clinic in clinics:
        item = clinic_detail(clinic)
        item["patient_count"] = Patient.query.filter_by(clinic_id=clinic.id).count()
        item["doctor_count"] = Doctor.query.filter_by(clinic_id=clinic.id, is_active=True).count()
        item["staff_count"] = User.query.filter_by(clinic_id=clinic.id, is_active=True).count()
        data.append(item)
    return ok(data, pagination_meta(total, page, per_page))


@admin_bp.post("/api/admin/clinics")
@permission_required("platform.manage")
def create():
    payload = json_body()
    clinic, admin, password = create_clinic(payload, g.user)
    result = clinic_detail(clinic)
    result["administrator"] = staff_dict(admin)
    result["temporary_password"] = password
    return ok({"clinic": result}, status=201)


@admin_bp.get("/api/admin/clinics/<clinic_id>")
@permission_required("platform.view")
def get_clinic(clinic_id):
    clinic = _clinic_or_404(clinic_id)
    data = clinic_detail(clinic)
    data["patient_count"] = Patient.query.filter_by(clinic_id=clinic.id).count()
    data["doctor_count"] = Doctor.query.filter_by(clinic_id=clinic.id, is_active=True).count()
    data["staff"] = [
        staff_dict(user)
        for user in User.query.filter_by(clinic_id=clinic.id)
        .order_by(User.is_active.desc(), User.full_name.asc())
        .all()
    ]
    data["recent_audit"] = [
        audit_dict(log)
        for log in AuditLog.query.filter_by(clinic_id=clinic.id)
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    ]
    return ok({"clinic": data})


@admin_bp.put("/api/admin/clinics/<clinic_id>")
@permission_required("platform.manage")
def update_clinic(clinic_id):
    clinic = _clinic_or_404(clinic_id)
    payload = json_body()
    for field in (
        "name", "legal_name", "registration_number", "address_line1", "address_line2",
        "city", "state", "postal_code", "country", "phone", "email", "website", "plan",
    ):
        if field in payload:
            value = (payload.get(field) or "").strip()
            if field == "name" and not value:
                raise ValidationError("Clinic name is required.")
            setattr(clinic, field, value[:200] if value else None)
    if "is_active" in payload:
        clinic.is_active = bool(payload.get("is_active"))
    if "is_demo" in payload:
        clinic.is_demo = bool(payload.get("is_demo"))
    audit(
        "platform.clinic_updated",
        "clinic",
        clinic.id,
        {"is_active": clinic.is_active, "plan": clinic.plan},
        clinic_id=clinic.id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"clinic": clinic_detail(clinic)})


@admin_bp.post("/api/admin/clinics/<clinic_id>/status")
@permission_required("platform.manage")
def set_status(clinic_id):
    clinic = _clinic_or_404(clinic_id)
    payload = json_body()
    active = bool(payload.get("is_active"))
    if clinic.id == getattr(getattr(g, "user", None), "clinic_id", None):
        raise ValidationError("You cannot change the status of your own clinic here.")
    clinic.is_active = active
    audit(
        "platform.clinic_suspended" if not active else "platform.clinic_activated",
        "clinic",
        clinic.id,
        clinic_id=clinic.id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"clinic": clinic_detail(clinic)})


@admin_bp.post("/api/admin/clinics/<clinic_id>/reset-admin-password")
@permission_required("platform.manage")
def reset_admin_password(clinic_id):
    clinic = _clinic_or_404(clinic_id)
    admin = (
        User.query.join(Role, User.role_id == Role.id)
        .filter(User.clinic_id == clinic.id, Role.slug == "clinic_admin")
        .order_by(User.is_active.desc())
        .first()
    )
    if admin is None:
        raise ConflictError("This clinic has no administrator account.")
    password = generate_temporary_password()
    admin.password_hash = hash_password(password)
    admin.must_change_password = True
    admin.failed_login_attempts = 0
    admin.locked_until = None
    admin.password_changed_at = datetime.now(timezone.utc)
    audit(
        "platform.clinic_admin_password_reset",
        "user",
        admin.id,
        clinic_id=clinic.id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"temporary_password": password, "administrator": staff_dict(admin)})


@admin_bp.get("/api/admin/audit-logs")
@permission_required("platform.view")
def platform_audit_logs():
    page, per_page = parse_pagination(request.args, default_per_page=50)
    query = AuditLog.query
    clinic_id = request.args.get("clinic_id")
    if clinic_id:
        query = query.filter(AuditLog.clinic_id == clinic_id)
    action = (request.args.get("action") or "").strip()
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    query = query.order_by(AuditLog.created_at.desc())
    total = query.count()
    logs = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok([audit_dict(log) for log in logs], pagination_meta(total, page, per_page))
