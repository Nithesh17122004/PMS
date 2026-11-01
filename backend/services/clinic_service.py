from __future__ import annotations

import re
import secrets
import string
from datetime import time
from zoneinfo import ZoneInfo

from ..auth.security import audit, hash_password, validate_password_strength
from ..extensions import db
from ..models import Clinic, ClinicSetting, User
from ..permissions.rbac import create_clinic_roles, seed_permissions
from ..utils.crypto import normalize_email
from ..utils.errors import ConflictError, ValidationError


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug[:70] or "clinic"


def unique_slug(base: str) -> str:
    slug = slugify(base)
    candidate = slug
    index = 2
    while Clinic.query.filter_by(slug=candidate).first():
        candidate = f"{slug}-{index}"
        index += 1
    return candidate


def generate_temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(14))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%&*" for c in password)
        ):
            return password


def create_clinic(payload: dict, actor, commit: bool = True) -> tuple[Clinic, User, str]:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValidationError("Clinic name is required.")
    email = normalize_email(payload.get("email"))
    if not email:
        raise ValidationError("Clinic email is required.")
    admin_email = normalize_email(payload.get("admin_email"))
    admin_name = (payload.get("admin_name") or "").strip()
    if not admin_email or not admin_name:
        raise ValidationError("Clinic administrator name and email are required.")
    if User.query.filter_by(email=admin_email).first():
        raise ConflictError("A user with the administrator email already exists.")
    timezone_name = payload.get("timezone") or "Asia/Kolkata"
    try:
        ZoneInfo(timezone_name)
    except Exception:
        raise ValidationError("Select a valid timezone.")
    password = payload.get("admin_password") or generate_temporary_password()
    if payload.get("admin_password"):
        validate_password_strength(password)
    slug = unique_slug(payload.get("slug") or name)
    permission_map = seed_permissions()
    clinic = Clinic(
        name=name[:160],
        slug=slug,
        legal_name=(payload.get("legal_name") or name)[:200],
        address_line1=(payload.get("address_line1") or None),
        address_line2=(payload.get("address_line2") or None),
        city=(payload.get("city") or None),
        state=(payload.get("state") or None),
        postal_code=(payload.get("postal_code") or None),
        country=(payload.get("country") or "India"),
        phone=(payload.get("phone") or None),
        email=email,
        website=(payload.get("website") or None),
        plan=(payload.get("plan") or "professional"),
        is_active=True,
        is_demo=bool(payload.get("is_demo", False)),
        created_by=actor.id if actor else None,
    )
    db.session.add(clinic)
    db.session.flush()
    settings = ClinicSetting(
        clinic_id=clinic.id,
        timezone=timezone_name,
        currency=(payload.get("currency") or "INR")[:8],
        tax_rate=payload.get("tax_rate") or 0,
        tax_label=(payload.get("tax_label") or "GST")[:30],
        invoice_prefix=(payload.get("invoice_prefix") or "INV")[:12],
        patient_prefix=(payload.get("patient_prefix") or "P")[:12],
        token_prefix=(payload.get("token_prefix") or "")[:12],
        token_mode=(payload.get("token_mode") if payload.get("token_mode") in ("doctor", "clinic") else "doctor"),
        working_days=payload.get("working_days") or ["mon", "tue", "wed", "thu", "fri", "sat"],
        open_time=payload.get("open_time") or time(9, 0),
        close_time=payload.get("close_time") or time(18, 0),
        slot_minutes=int(payload.get("slot_minutes") or 15),
        consultation_fee_default=payload.get("consultation_fee_default") or 500,
        follow_up_fee_default=payload.get("follow_up_fee_default") or 0,
        receipt_footer=payload.get("receipt_footer"),
        display_message=payload.get("display_message") or "Please wait for your token to be called.",
    )
    db.session.add(settings)
    roles = create_clinic_roles(clinic.id, permission_map)
    admin = User(
        clinic_id=clinic.id,
        role_id=roles["clinic_admin"].id,
        email=admin_email,
        full_name=admin_name[:140],
        password_hash=hash_password(password),
        phone=(payload.get("admin_phone") or None),
        designation="Clinic Administrator",
        must_change_password=not bool(payload.get("admin_password")),
        avatar_color="#1d4ed8",
    )
    db.session.add(admin)
    db.session.flush()
    audit(
        "platform.clinic_created",
        "clinic",
        clinic.id,
        {"slug": clinic.slug, "plan": clinic.plan, "admin_user_id": admin.id},
        clinic_id=clinic.id,
        user_id=actor.id if actor else None,
    )
    if commit:
        db.session.commit()
    return clinic, admin, password
