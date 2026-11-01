from __future__ import annotations

import secrets
import string

from ..extensions import db
from .base import ClinicScopedMixin, TimestampMixin, UUIDMixin, utcnow


def generate_display_key() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(20))


class Clinic(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "clinics"

    name = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(80), nullable=False, unique=True, index=True)
    legal_name = db.Column(db.String(200))
    registration_number = db.Column(db.String(80))
    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    country = db.Column(db.String(80), default="India")
    phone = db.Column(db.String(30))
    email = db.Column(db.String(160))
    website = db.Column(db.String(160))
    logo_path = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_demo = db.Column(db.Boolean, nullable=False, default=False)
    plan = db.Column(db.String(40), nullable=False, default="professional")
    display_key = db.Column(
        db.String(40), nullable=False, unique=True, default=generate_display_key
    )
    created_by = db.Column(db.String(36))  # soft reference avoids a table cycle

    settings = db.relationship(
        "ClinicSetting", back_populates="clinic", uselist=False, cascade="all, delete-orphan"
    )
    users = db.relationship("User", back_populates="clinic", foreign_keys="User.clinic_id")
    doctors = db.relationship("Doctor", back_populates="clinic")

    def __repr__(self) -> str:
        return f"<Clinic {self.name}>"


class ClinicSetting(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "clinic_settings"

    clinic_id = db.Column(
        db.String(36),
        db.ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    timezone = db.Column(db.String(64), nullable=False, default="Asia/Kolkata")
    currency = db.Column(db.String(8), nullable=False, default="INR")
    locale = db.Column(db.String(16), nullable=False, default="en-IN")
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    tax_label = db.Column(db.String(30), nullable=False, default="GST")
    invoice_prefix = db.Column(db.String(12), nullable=False, default="INV")
    patient_prefix = db.Column(db.String(12), nullable=False, default="P")
    token_prefix = db.Column(db.String(12), nullable=False, default="")
    token_mode = db.Column(db.String(20), nullable=False, default="doctor")  # doctor|clinic
    working_days = db.Column(
        db.JSON, nullable=False, default=lambda: ["mon", "tue", "wed", "thu", "fri", "sat"]
    )
    open_time = db.Column(db.Time, nullable=False, default=lambda: __import__("datetime").time(9, 0))
    close_time = db.Column(db.Time, nullable=False, default=lambda: __import__("datetime").time(18, 0))
    slot_minutes = db.Column(db.Integer, nullable=False, default=15)
    consultation_fee_default = db.Column(db.Numeric(10, 2), nullable=False, default=500)
    follow_up_fee_default = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    appointment_override_roles = db.Column(db.JSON, nullable=False, default=lambda: ["clinic_admin"])
    reminder_email_enabled = db.Column(db.Boolean, nullable=False, default=False)
    reminder_sms_enabled = db.Column(db.Boolean, nullable=False, default=False)
    reminder_whatsapp_enabled = db.Column(db.Boolean, nullable=False, default=False)
    reminder_day_before = db.Column(db.Boolean, nullable=False, default=True)
    reminder_on_day = db.Column(db.Boolean, nullable=False, default=True)
    overdue_followup_alert = db.Column(db.Boolean, nullable=False, default=True)
    reminder_time = db.Column(db.Time, nullable=False, default=lambda: __import__("datetime").time(18, 0))
    appointment_reminders = db.Column(db.Boolean, nullable=False, default=True)
    low_stock_alerts = db.Column(db.Boolean, nullable=False, default=True)
    receipt_footer = db.Column(db.String(300))
    display_message = db.Column(db.String(200), default="Please wait for your token to be called.")
    public_display_enabled = db.Column(db.Boolean, nullable=False, default=True)
    allow_walk_in = db.Column(db.Boolean, nullable=False, default=True)
    auto_invoice_on_completion = db.Column(db.Boolean, nullable=False, default=False)

    clinic = db.relationship("Clinic", back_populates="settings")


class DocumentSequence(UUIDMixin, db.Model):
    """Race-safe sequential document numbers per clinic (patients, invoices...)."""

    __tablename__ = "document_sequences"
    __table_args__ = (
        db.UniqueConstraint("clinic_id", "kind", "period", name="uq_doc_seq_clinic_kind_period"),
    )

    clinic_id = db.Column(
        db.String(36), db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False
    )
    kind = db.Column(db.String(30), nullable=False)
    period = db.Column(db.String(20), nullable=False, default="")
    last_number = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class AuditLog(UUIDMixin, db.Model):
    __tablename__ = "audit_logs"
    __table_args__ = (
        db.Index("ix_audit_clinic_created", "clinic_id", "created_at"),
        db.Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    clinic_id = db.Column(
        db.String(36), db.ForeignKey("clinics.id", ondelete="SET NULL"), nullable=True
    )
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    action = db.Column(db.String(80), nullable=False)
    entity_type = db.Column(db.String(60))
    entity_id = db.Column(db.String(36))
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(255))
    details = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )

    user = db.relationship("User", foreign_keys=[user_id])
