from __future__ import annotations

from ..extensions import db
from ..utils.crypto import EncryptedString
from .base import UUIDMixin, utcnow


class NotificationStatus:
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class NotificationChannel:
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    IN_APP = "in_app"

    ALL = [EMAIL, SMS, WHATSAPP, IN_APP]


class Notification(UUIDMixin, db.Model):
    __tablename__ = "notifications"
    __table_args__ = (
        db.UniqueConstraint("dedupe_key", name="uq_notification_dedupe"),
        db.Index("ix_notification_clinic_created", "clinic_id", "created_at"),
        db.Index("ix_notification_clinic_status", "clinic_id", "status"),
        db.Index("ix_notification_user_read", "user_id", "read_at"),
    )

    clinic_id = db.Column(
        db.String(36), db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=True
    )
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    patient_id = db.Column(
        db.String(36), db.ForeignKey("patients.id", ondelete="SET NULL"), nullable=True
    )
    notification_type = db.Column(db.String(40), nullable=False)
    channel = db.Column(db.String(20), nullable=False, default=NotificationChannel.IN_APP)
    recipient = db.Column(EncryptedString)
    recipient_masked = db.Column(db.String(160))
    subject = db.Column(db.String(200))
    body = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=NotificationStatus.QUEUED)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=3)
    next_attempt_at = db.Column(db.DateTime(timezone=True))
    sent_at = db.Column(db.DateTime(timezone=True))
    read_at = db.Column(db.DateTime(timezone=True))
    provider = db.Column(db.String(40))
    provider_message_id = db.Column(db.String(160))
    error = db.Column(db.String(300))
    dedupe_key = db.Column(db.String(190), nullable=False)
    related_type = db.Column(db.String(40))
    related_id = db.Column(db.String(36))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    user = db.relationship("User", foreign_keys=[user_id])
    patient = db.relationship("Patient", foreign_keys=[patient_id])
