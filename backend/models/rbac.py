from __future__ import annotations

from ..extensions import db
from .base import TimestampMixin, UUIDMixin, utcnow

role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.String(36), db.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    db.Column(
        "permission_id",
        db.String(36),
        db.ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Permission(UUIDMixin, db.Model):
    __tablename__ = "permissions"

    code = db.Column(db.String(80), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    group_name = db.Column(db.String(60), nullable=False, default="General")
    description = db.Column(db.String(255))

    def __repr__(self) -> str:
        return f"<Permission {self.code}>"


class Role(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "roles"
    __table_args__ = (
        db.UniqueConstraint("clinic_id", "slug", name="uq_role_clinic_slug"),
        db.Index("ix_role_clinic", "clinic_id"),
    )

    clinic_id = db.Column(
        db.String(36), db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=True
    )
    name = db.Column(db.String(80), nullable=False)
    slug = db.Column(db.String(60), nullable=False)
    description = db.Column(db.String(255))
    is_system = db.Column(db.Boolean, nullable=False, default=True)

    permissions = db.relationship(
        "Permission", secondary=role_permissions, lazy="selectin", backref="roles"
    )
    users = db.relationship("User", back_populates="role", foreign_keys="User.role_id")

    def __repr__(self) -> str:
        return f"<Role {self.slug}>"


class UserRole(UUIDMixin, db.Model):
    __tablename__ = "user_roles"
    __table_args__ = (
        db.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )

    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id = db.Column(
        db.String(36), db.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    clinic_id = db.Column(
        db.String(36), db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=True
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
