from __future__ import annotations

from datetime import datetime, timezone

from ..extensions import db
from .base import TimestampMixin, UUIDMixin, utcnow


class User(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        db.Index("ix_users_clinic_active", "clinic_id", "is_active"),
    )

    clinic_id = db.Column(
        db.String(36), db.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=True
    )
    role_id = db.Column(
        db.String(36), db.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    email = db.Column(db.String(190), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(140), nullable=False)
    phone = db.Column(db.String(30))
    designation = db.Column(db.String(80))
    avatar_color = db.Column(db.String(16), default="#2563eb")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))
    last_login_at = db.Column(db.DateTime(timezone=True))
    last_login_ip = db.Column(db.String(64))
    password_changed_at = db.Column(db.DateTime(timezone=True))
    notification_email = db.Column(db.Boolean, nullable=False, default=True)
    notification_in_app = db.Column(db.Boolean, nullable=False, default=True)

    clinic = db.relationship("Clinic", back_populates="users", foreign_keys=[clinic_id])
    role = db.relationship("Role", back_populates="users", foreign_keys=[role_id], lazy="joined")
    doctor_profile = db.relationship(
        "Doctor", back_populates="user", uselist=False, foreign_keys="Doctor.user_id"
    )

    @property
    def is_super_admin(self) -> bool:
        return bool(self.role and self.role.slug == "super_admin")

    @property
    def initials(self) -> str:
        parts = [p for p in (self.full_name or "").split() if p]
        return "".join(p[0].upper() for p in parts[:2]) or "U"

    @property
    def is_locked(self) -> bool:
        if not self.locked_until:
            return False
        until = self.locked_until
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return until > datetime.now(timezone.utc)

    def permission_codes(self) -> set[str]:
        if not self.role:
            return set()
        return {p.code for p in self.role.permissions}

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class PasswordResetToken(UUIDMixin, db.Model):
    __tablename__ = "password_reset_tokens"

    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash = db.Column(db.String(128), nullable=False, unique=True, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True))
    requested_ip = db.Column(db.String(64))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    user = db.relationship("User")
