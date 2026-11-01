"""Role-based access control definitions and helpers."""
from __future__ import annotations

from functools import wraps

from flask import g, jsonify

from ..extensions import db
from ..models import Permission, Role, User
from ..utils.errors import ApiError

# code: (label, group)
PERMISSIONS: dict[str, tuple[str, str]] = {
    "platform.view": ("View platform dashboard", "Platform"),
    "platform.manage": ("Manage clinics and platform", "Platform"),
    "dashboard.view": ("View dashboard", "General"),
    "patients.view": ("View patients", "Patients"),
    "patients.create": ("Register patients", "Patients"),
    "patients.edit": ("Edit patients", "Patients"),
    "patients.merge": ("Merge duplicate patients", "Patients"),
    "patients.export": ("Export patient data", "Patients"),
    "doctors.view": ("View doctors", "Doctors"),
    "doctors.manage": ("Manage doctors and schedules", "Doctors"),
    "appointments.view": ("View appointments", "Appointments"),
    "appointments.create": ("Book appointments", "Appointments"),
    "appointments.edit": ("Reschedule appointments", "Appointments"),
    "appointments.cancel": ("Cancel appointments", "Appointments"),
    "appointments.override": ("Override appointment conflicts", "Appointments"),
    "tokens.view": ("View token queues", "Queue"),
    "tokens.create": ("Generate tokens", "Queue"),
    "tokens.call": ("Call next token", "Queue"),
    "tokens.recall": ("Recall tokens", "Queue"),
    "tokens.skip": ("Skip tokens", "Queue"),
    "tokens.cancel": ("Cancel tokens", "Queue"),
    "tokens.transfer": ("Transfer tokens between doctors", "Queue"),
    "tokens.manage_all": ("Manage every doctor's queue", "Queue"),
    "followups.view": ("View follow-ups", "Follow-ups"),
    "followups.manage": ("Confirm, reschedule and cancel follow-ups", "Follow-ups"),
    "followups.complete": ("Complete follow-ups", "Follow-ups"),
    "consultations.view": ("View consultations", "Clinical"),
    "consultations.create": ("Create consultations", "Clinical"),
    "consultations.complete": ("Complete consultations", "Clinical"),
    "prescriptions.view": ("View prescriptions", "Clinical"),
    "prescriptions.create": ("Issue prescriptions", "Clinical"),
    "billing.view": ("View invoices and payments", "Billing"),
    "billing.create": ("Create invoices", "Billing"),
    "billing.payment": ("Record payments", "Billing"),
    "billing.refund": ("Issue refunds", "Billing"),
    "billing.export": ("Export billing reports", "Billing"),
    "pharmacy.view": ("View pharmacy and inventory", "Pharmacy"),
    "pharmacy.manage": ("Manage medicines and stock", "Pharmacy"),
    "pharmacy.dispense": ("Dispense medicines", "Pharmacy"),
    "lab.view": ("View laboratory orders", "Laboratory"),
    "lab.manage": ("Manage lab orders and samples", "Laboratory"),
    "lab.results": ("Enter and verify lab results", "Laboratory"),
    "reports.view": ("View reports", "Reports"),
    "reports.export": ("Export reports", "Reports"),
    "settings.view": ("View clinic settings", "Administration"),
    "settings.manage": ("Manage clinic settings", "Administration"),
    "staff.view": ("View staff", "Administration"),
    "staff.manage": ("Manage staff accounts", "Administration"),
    "audit.view": ("View audit log", "Administration"),
    "notifications.view": ("View notifications", "Notifications"),
    "notifications.manage": ("Manage and retry notifications", "Notifications"),
}

ROLE_DEFINITIONS: dict[str, dict] = {
    "super_admin": {
        "name": "Super Admin",
        "description": "Platform operator with access to clinic provisioning only.",
        "permissions": ["platform.view", "platform.manage"],
    },
    "clinic_admin": {
        "name": "Clinic Admin",
        "description": "Full operational and administrative control of a clinic.",
        "permissions": [p for p in PERMISSIONS if not p.startswith("platform.")],
    },
    "receptionist": {
        "name": "Receptionist",
        "description": "Front desk registration, appointments, queue and collections.",
        "permissions": [
            "dashboard.view", "patients.view", "patients.create", "patients.edit",
            "doctors.view", "appointments.view", "appointments.create", "appointments.edit",
            "appointments.cancel", "tokens.view", "tokens.create", "tokens.call",
            "tokens.recall", "tokens.skip", "tokens.cancel", "tokens.transfer",
            "followups.view", "followups.manage", "billing.view", "billing.create",
            "billing.payment", "reports.view", "notifications.view",
        ],
    },
    "doctor": {
        "name": "Doctor",
        "description": "Clinical consultations, prescriptions and own patient queue.",
        "permissions": [
            "dashboard.view", "patients.view", "doctors.view", "appointments.view",
            "tokens.view", "tokens.call", "tokens.recall", "tokens.skip",
            "followups.view", "followups.manage", "followups.complete",
            "consultations.view", "consultations.create", "consultations.complete",
            "prescriptions.view", "prescriptions.create", "lab.view", "lab.results",
            "billing.view", "reports.view", "notifications.view",
        ],
    },
    "nurse": {
        "name": "Nurse",
        "description": "Patient care support, vitals, queue and follow-up coordination.",
        "permissions": [
            "dashboard.view", "patients.view", "doctors.view", "appointments.view",
            "tokens.view", "tokens.call", "tokens.recall", "tokens.skip",
            "followups.view", "followups.manage", "followups.complete",
            "consultations.view", "lab.view", "notifications.view",
        ],
    },
    "accountant": {
        "name": "Accountant",
        "description": "Billing, payments, refunds and financial reporting.",
        "permissions": [
            "dashboard.view", "patients.view", "billing.view", "billing.create",
            "billing.payment", "billing.refund", "billing.export", "reports.view",
            "reports.export", "notifications.view",
        ],
    },
    "pharmacist": {
        "name": "Pharmacist",
        "description": "Pharmacy catalogue, stock, dispensing and expiry control.",
        "permissions": [
            "dashboard.view", "patients.view", "pharmacy.view", "pharmacy.manage",
            "pharmacy.dispense", "prescriptions.view", "billing.view", "reports.view",
            "notifications.view",
        ],
    },
    "lab_technician": {
        "name": "Laboratory Technician",
        "description": "Lab orders, samples, results and reports.",
        "permissions": [
            "dashboard.view", "patients.view", "lab.view", "lab.manage", "lab.results",
            "reports.view", "notifications.view",
        ],
    },
}

CLINIC_ROLE_ORDER = [
    "clinic_admin", "receptionist", "doctor", "nurse", "accountant", "pharmacist",
    "lab_technician",
]


def seed_permissions() -> dict[str, Permission]:
    existing = {p.code: p for p in Permission.query.all()}
    for code, (label, group) in PERMISSIONS.items():
        if code not in existing:
            permission = Permission(code=code, name=label, group_name=group)
            db.session.add(permission)
            existing[code] = permission
        else:
            existing[code].name = label
            existing[code].group_name = group
    db.session.flush()
    return existing


def create_clinic_roles(clinic_id: str, permission_map: dict[str, Permission] | None = None) -> dict[str, Role]:
    permission_map = permission_map or seed_permissions()
    roles: dict[str, Role] = {}
    for slug in CLINIC_ROLE_ORDER:
        definition = ROLE_DEFINITIONS[slug]
        role = Role.query.filter_by(clinic_id=clinic_id, slug=slug).first()
        if role is None:
            role = Role(
                clinic_id=clinic_id,
                slug=slug,
                name=definition["name"],
                description=definition["description"],
                is_system=True,
            )
            db.session.add(role)
        role.permissions = [permission_map[code] for code in definition["permissions"]]
        roles[slug] = role
    db.session.flush()
    return roles


def create_super_admin_role() -> Role:
    permission_map = seed_permissions()
    role = Role.query.filter_by(clinic_id=None, slug="super_admin").first()
    if role is None:
        role = Role(
            clinic_id=None,
            slug="super_admin",
            name="Super Admin",
            description=ROLE_DEFINITIONS["super_admin"]["description"],
            is_system=True,
        )
        db.session.add(role)
    role.permissions = [permission_map[c] for c in ROLE_DEFINITIONS["super_admin"]["permissions"]]
    db.session.flush()
    return role


def has_permission(user: User | None, code: str) -> bool:
    if not user or not user.is_active:
        return False
    if user.is_super_admin:
        return code in user.permission_codes()
    return code in user.permission_codes()


def permission_required(code: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = getattr(g, "user", None)
            if not user:
                raise ApiError("unauthorized", "Authentication required.", 401)
            if not has_permission(user, code):
                raise ApiError(
                    "forbidden", "You do not have permission to perform this action.", 403
                )
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def any_permission_required(*codes: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = getattr(g, "user", None)
            if not user:
                raise ApiError("unauthorized", "Authentication required.", 401)
            if not any(has_permission(user, code) for code in codes):
                raise ApiError(
                    "forbidden", "You do not have permission to perform this action.", 403
                )
            return fn(*args, **kwargs)

        return wrapper

    return decorator
