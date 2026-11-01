from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, g, request
from sqlalchemy import or_

from ..auth.security import audit, hash_password, validate_password_strength
from ..extensions import db
from ..models import AuditLog, Clinic, ClinicSetting, Permission, Role, User
from ..permissions.rbac import PERMISSIONS, permission_required
from ..permissions.tenant import current_clinic, get_scoped_or_404
from ..services.clinic_service import generate_temporary_password
from ..services.sequence_service import format_document_number
from ..utils.crypto import normalize_email
from ..utils.datetime_utils import parse_date, parse_time
from ..utils.errors import ConflictError, ForbiddenError, ValidationError
from ..utils.responses import ok, pagination_meta, parse_pagination
from ..utils.serializers import (
    audit_dict,
    clinic_detail,
    role_dict,
    settings_dict,
    staff_dict,
)
from ..utils.uploads import save_logo
from .helpers import json_body

clinic_bp = Blueprint("clinic", __name__)

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@clinic_bp.get("/api/clinic")
@permission_required("settings.view")
def get_clinic():
    return ok({"clinic": clinic_detail(current_clinic())})


@clinic_bp.put("/api/clinic")
@permission_required("settings.manage")
def update_clinic():
    clinic = current_clinic()
    payload = json_body()
    for field in (
        "name", "legal_name", "registration_number", "address_line1", "address_line2",
        "city", "state", "postal_code", "country", "phone", "email", "website",
    ):
        if field in payload:
            value = (payload.get(field) or "").strip()
            if field == "name" and not value:
                raise ValidationError("Clinic name is required.")
            if field == "email" and value and "@" not in value:
                raise ValidationError("Enter a valid clinic email address.")
            setattr(clinic, field, value[:200] if value else None)
    audit("clinic.updated", "clinic", clinic.id, clinic_id=clinic.id, user_id=g.user.id)
    db.session.commit()
    return ok({"clinic": clinic_detail(clinic)})


@clinic_bp.put("/api/clinic/settings")
@permission_required("settings.manage")
def update_settings():
    clinic = current_clinic()
    settings = clinic.settings
    if settings is None:
        settings = ClinicSetting(clinic_id=clinic.id)
        db.session.add(settings)
        db.session.flush()
    payload = json_body()

    if "timezone" in payload:
        timezone_name = (payload.get("timezone") or "").strip()
        try:
            ZoneInfo(timezone_name)
        except Exception:
            raise ValidationError("Select a valid timezone.")
        settings.timezone = timezone_name
    for field in ("currency", "locale", "tax_label", "invoice_prefix", "patient_prefix", "token_prefix"):
        if field in payload:
            value = (payload.get(field) or "").strip()
            if not value:
                raise ValidationError(f"{field.replace('_', ' ').title()} cannot be empty.")
            setattr(settings, field, value[:30])
    if "tax_rate" in payload:
        try:
            rate = float(payload.get("tax_rate") or 0)
        except (TypeError, ValueError):
            raise ValidationError("Tax rate must be a number.")
        if rate < 0 or rate > 100:
            raise ValidationError("Tax rate must be between 0 and 100.")
        settings.tax_rate = rate
    if "token_mode" in payload:
        if payload.get("token_mode") not in ("doctor", "clinic"):
            raise ValidationError("Token mode must be doctor-wise or clinic-wide.")
        settings.token_mode = payload.get("token_mode")
    if "working_days" in payload:
        days = payload.get("working_days")
        if not isinstance(days, list) or not days:
            raise ValidationError("Select at least one working day.")
        if any(day not in WEEKDAY_KEYS for day in days):
            raise ValidationError("Working days contain an invalid value.")
        settings.working_days = [day for day in WEEKDAY_KEYS if day in days]
    for field in ("open_time", "close_time", "reminder_time"):
        if field in payload:
            setattr(settings, field, parse_time(payload.get(field), field.replace("_", " ").title()))
    if settings.open_time >= settings.close_time:
        raise ValidationError("Closing time must be after opening time.")
    if "slot_minutes" in payload:
        try:
            slot_minutes = int(payload.get("slot_minutes") or 15)
        except (TypeError, ValueError):
            raise ValidationError("Slot duration must be a number.")
        if slot_minutes < 5 or slot_minutes > 240:
            raise ValidationError("Slot duration must be between 5 and 240 minutes.")
        settings.slot_minutes = slot_minutes
    for field in ("consultation_fee_default", "follow_up_fee_default"):
        if field in payload:
            try:
                value = float(payload.get(field) or 0)
            except (TypeError, ValueError):
                raise ValidationError("Fees must be numbers.")
            if value < 0:
                raise ValidationError("Fees cannot be negative.")
            setattr(settings, field, value)
    for field in (
        "reminder_email_enabled", "reminder_sms_enabled", "reminder_whatsapp_enabled",
        "reminder_day_before", "reminder_on_day", "overdue_followup_alert",
        "appointment_reminders", "low_stock_alerts", "public_display_enabled",
        "allow_walk_in", "auto_invoice_on_completion",
    ):
        if field in payload:
            setattr(settings, field, bool(payload.get(field)))
    for field in ("receipt_footer", "display_message"):
        if field in payload:
            value = (payload.get(field) or "").strip()
            setattr(settings, field, value[:300] if value else None)
    if "appointment_override_roles" in payload:
        roles = payload.get("appointment_override_roles") or []
        if not isinstance(roles, list):
            raise ValidationError("Override roles must be a list.")
        settings.appointment_override_roles = [str(role)[:60] for role in roles]
    audit(
        "clinic.settings_updated",
        "clinic",
        clinic.id,
        {"token_mode": settings.token_mode, "timezone": settings.timezone},
        clinic_id=clinic.id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"settings": settings_dict(settings), "clinic": clinic_detail(clinic)})


@clinic_bp.post("/api/clinic/logo")
@permission_required("settings.manage")
def upload_logo():
    clinic = current_clinic()
    file = request.files.get("logo") or request.files.get("file")
    path = save_logo(file, clinic.id)
    old = clinic.logo_path
    clinic.logo_path = path
    audit("clinic.logo_updated", "clinic", clinic.id, clinic_id=clinic.id, user_id=g.user.id)
    db.session.commit()
    if old and old != path:
        old_path = os.path.join(current_app.config["UPLOAD_FOLDER"], old)
        try:
            if os.path.exists(old_path):
                os.remove(old_path)
        except OSError:
            pass
    return ok({"logo_url": f"/api/public/clinics/{clinic.slug}/logo", "clinic": clinic_detail(clinic)})


@clinic_bp.delete("/api/clinic/logo")
@permission_required("settings.manage")
def delete_logo():
    clinic = current_clinic()
    old = clinic.logo_path
    clinic.logo_path = None
    audit("clinic.logo_removed", "clinic", clinic.id, clinic_id=clinic.id, user_id=g.user.id)
    db.session.commit()
    if old:
        try:
            path = os.path.join(current_app.config["UPLOAD_FOLDER"], old)
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
    return ok({"message": "Logo removed."})


@clinic_bp.post("/api/clinic/display-key/rotate")
@permission_required("settings.manage")
def rotate_display_key():
    from ..models.clinic import generate_display_key

    clinic = current_clinic()
    new_key = generate_display_key()
    while Clinic.query.filter_by(display_key=new_key).first():
        new_key = generate_display_key()
    clinic.display_key = new_key
    audit("clinic.display_key_rotated", "clinic", clinic.id, clinic_id=clinic.id, user_id=g.user.id)
    db.session.commit()
    return ok(
        {
            "display_key": clinic.display_key,
            "display_url": f"/display/{clinic.display_key}",
        }
    )


@clinic_bp.get("/api/clinic/staff")
@permission_required("staff.view")
def list_staff():
    clinic = current_clinic()
    status = request.args.get("status", "all")
    query = User.query.filter(User.clinic_id == clinic.id)
    if status == "active":
        query = query.filter(User.is_active.is_(True))
    elif status == "inactive":
        query = query.filter(User.is_active.is_(False))
    term = (request.args.get("q") or "").strip()
    if term:
        query = query.filter(
            or_(User.full_name.ilike(f"%{term}%"), User.email.ilike(f"%{term}%"))
        )
    staff = query.order_by(User.is_active.desc(), User.full_name.asc()).all()
    return ok([staff_dict(user) for user in staff])


@clinic_bp.post("/api/clinic/staff")
@permission_required("staff.manage")
def create_staff():
    clinic = current_clinic()
    payload = json_body()
    raw_name = payload.get("full_name")
    raw_email = payload.get("email")
    if not isinstance(raw_name, str) or not isinstance(raw_email, str):
        raise ValidationError("Staff name and email are required.")
    full_name = raw_name.strip()
    email = normalize_email(raw_email)
    if not full_name or not email:
        raise ValidationError("Staff name and email are required.")
    if len(full_name) > 140:
        raise ValidationError("Staff name must be 140 characters or fewer.")
    if len(email) > 190 or not re.fullmatch(r"[^@\\s]+@[^@\\s]+\\.[^@\\s]+", email):
        raise ValidationError("Enter a valid email address (up to 190 characters).")
    if User.query.filter_by(email=email).first():
        raise ConflictError("A user with that email already exists.")
    role_id = payload.get("role_id")
    role = Role.query.filter_by(id=role_id, clinic_id=clinic.id).first() if isinstance(role_id, str) and role_id else None
    if role is None:
        raise ValidationError("Select a valid role for this clinic.")
    if role.slug == "doctor":
        raise ValidationError("Create doctor accounts from the Doctors module so a clinical profile is created.")
    password = payload.get("password")
    temp_password = None
    if password:
        if not isinstance(password, str):
            raise ValidationError("Password must be text.")
        validate_password_strength(password)
    else:
        password = generate_temporary_password()
        temp_password = password
    user = User(
        clinic_id=clinic.id,
        role_id=role.id,
        email=email,
        full_name=full_name[:140],
        phone=(str(payload.get("phone")).strip()[:30] or None) if payload.get("phone") else None,
        designation=(str(payload.get("designation") or role.name).strip()[:80] or role.name),
        password_hash=hash_password(password),
        must_change_password=temp_password is not None,
        avatar_color=(payload.get("avatar_color") or "#2563eb")[:16],
    )
    db.session.add(user)
    db.session.flush()
    audit(
        "staff.created",
        "user",
        user.id,
        {"role": role.slug},
        clinic_id=clinic.id,
        user_id=g.user.id,
    )
    db.session.commit()
    data = staff_dict(user)
    if temp_password:
        data["temporary_password"] = temp_password
    return ok({"staff": data}, status=201)


@clinic_bp.put("/api/clinic/staff/<user_id>")
@permission_required("staff.manage")
def update_staff(user_id):
    clinic = current_clinic()
    user = User.query.filter_by(id=user_id, clinic_id=clinic.id).first()
    if user is None:
        raise ConflictError("Staff member not found.")
    payload = json_body()
    if "full_name" in payload:
        name = (payload.get("full_name") or "").strip()
        if not name:
            raise ValidationError("Staff name is required.")
        user.full_name = name[:140]
    if "phone" in payload:
        user.phone = (payload.get("phone") or None)
    if "designation" in payload:
        user.designation = (payload.get("designation") or None)
    if "role_id" in payload:
        role = get_scoped_or_404(Role, payload.get("role_id") or "")
        if role.slug == "doctor" and user.doctor_profile is None:
            raise ValidationError("Assign the doctor role from the Doctors module.")
        if user.id == g.user.id and role.id != user.role_id:
            raise ForbiddenError("You cannot change your own role.")
        user.role_id = role.id
    if "is_active" in payload:
        active = bool(payload.get("is_active"))
        if user.id == g.user.id and not active:
            raise ForbiddenError("You cannot deactivate your own account.")
        user.is_active = active
    audit(
        "staff.updated",
        "user",
        user.id,
        {"role": user.role.slug if user.role else None, "is_active": user.is_active},
        clinic_id=clinic.id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"staff": staff_dict(user)})


@clinic_bp.post("/api/clinic/staff/<user_id>/reset-password")
@permission_required("staff.manage")
def reset_staff_password(user_id):
    clinic = current_clinic()
    user = User.query.filter_by(id=user_id, clinic_id=clinic.id).first()
    if user is None:
        raise ConflictError("Staff member not found.")
    if user.id == g.user.id:
        raise ForbiddenError("Use your profile settings to change your own password.")
    password = generate_temporary_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.failed_login_attempts = 0
    user.locked_until = None
    user.password_changed_at = datetime.now(timezone.utc)
    audit("staff.password_reset", "user", user.id, clinic_id=clinic.id, user_id=g.user.id)
    db.session.commit()
    return ok({"temporary_password": password, "staff": staff_dict(user)})


@clinic_bp.get("/api/clinic/roles")
@permission_required("staff.view")
def list_roles():
    clinic = current_clinic()
    roles = Role.query.filter_by(clinic_id=clinic.id).order_by(Role.name.asc()).all()
    return ok([role_dict(role) for role in roles])


@clinic_bp.get("/api/clinic/permissions")
@permission_required("staff.view")
def list_permissions():
    permissions = Permission.query.order_by(Permission.group_name.asc(), Permission.code.asc()).all()
    groups: dict[str, list] = {}
    for permission in permissions:
        groups.setdefault(permission.group_name, []).append(
            {"code": permission.code, "name": permission.name, "group": permission.group_name}
        )
    return ok(
        {
            "permissions": [
                {"code": code, "name": label, "group": group}
                for code, (label, group) in PERMISSIONS.items()
            ],
            "groups": groups,
        }
    )


@clinic_bp.put("/api/clinic/roles/<role_id>")
@permission_required("staff.manage")
def update_role(role_id):
    clinic = current_clinic()
    role = Role.query.filter_by(id=role_id, clinic_id=clinic.id).first()
    if role is None:
        raise ConflictError("Role not found.")
    payload = json_body()
    codes = payload.get("permissions")
    if not isinstance(codes, list):
        raise ValidationError("Permissions must be a list.")
    permissions = Permission.query.filter(Permission.code.in_(codes)).all()
    if len(permissions) != len(set(codes)):
        raise ValidationError("One or more permissions are invalid.")
    if role.id == g.user.role_id and "staff.manage" not in codes:
        raise ForbiddenError("You cannot remove your own ability to manage staff.")
    role.permissions = permissions
    audit(
        "rbac.role_updated",
        "role",
        role.id,
        {"permission_count": len(permissions)},
        clinic_id=clinic.id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"role": role_dict(role)})


@clinic_bp.get("/api/clinic/audit-logs")
@permission_required("audit.view")
def audit_logs():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args, default_per_page=50)
    query = AuditLog.query.filter(AuditLog.clinic_id == clinic.id)
    action = (request.args.get("action") or "").strip()
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    entity_type = request.args.get("entity_type")
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    user_id = request.args.get("user_id")
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    start = parse_date(request.args.get("start"), "Start date", required=False)
    end = parse_date(request.args.get("end"), "End date", required=False)
    if start:
        query = query.filter(AuditLog.created_at >= datetime.combine(start, datetime.min.time()).replace(tzinfo=timezone.utc))
    if end:
        query = query.filter(AuditLog.created_at <= datetime.combine(end, datetime.max.time()).replace(tzinfo=timezone.utc))
    query = query.order_by(AuditLog.created_at.desc())
    total = query.count()
    logs = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok([audit_dict(log) for log in logs], pagination_meta(total, page, per_page))


@clinic_bp.get("/api/clinic/integrations")
@permission_required("settings.view")
def integrations():
    config = current_app.config
    return ok(
        {
            "email": {
                "configured": bool(config.get("SMTP_HOST")),
                "provider": config.get("MAIL_PROVIDER"),
                "from": config.get("MAIL_FROM"),
            },
            "sms": {
                "configured": bool(config.get("TWILIO_ACCOUNT_SID") and config.get("TWILIO_FROM_NUMBER")),
                "provider": "twilio" if config.get("TWILIO_ACCOUNT_SID") else None,
            },
            "whatsapp": {
                "configured": bool(config.get("WHATSAPP_PHONE_ID") and config.get("WHATSAPP_TOKEN")),
                "provider": "meta_cloud" if config.get("WHATSAPP_PHONE_ID") else None,
            },
            "demo_mode": bool(config.get("DEMO_MODE")),
        }
    )
