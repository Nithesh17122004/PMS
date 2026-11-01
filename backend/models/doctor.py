from __future__ import annotations

from ..extensions import db
from .base import ClinicScopedMixin, TimestampMixin, UUIDMixin


class Doctor(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "doctors"
    __table_args__ = (
        db.UniqueConstraint("clinic_id", "doctor_code", name="uq_doctor_clinic_code"),
        db.Index("ix_doctor_clinic_active", "clinic_id", "is_active"),
    )

    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )
    doctor_code = db.Column(db.String(30), nullable=False)
    full_name = db.Column(db.String(140), nullable=False)
    specialization = db.Column(db.String(120), nullable=False)
    qualifications = db.Column(db.String(200))
    registration_number = db.Column(db.String(80))
    experience_years = db.Column(db.Integer, default=0)
    consultation_fee = db.Column(db.Numeric(10, 2), nullable=False, default=500)
    follow_up_fee = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    bio = db.Column(db.Text)
    room_number = db.Column(db.String(30))
    avg_consult_minutes = db.Column(db.Integer, nullable=False, default=12)
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    clinic = db.relationship("Clinic", back_populates="doctors")
    user = db.relationship("User", back_populates="doctor_profile", foreign_keys=[user_id])
    schedules = db.relationship(
        "DoctorSchedule", back_populates="doctor", cascade="all, delete-orphan"
    )
    leaves = db.relationship("DoctorLeave", back_populates="doctor", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Doctor {self.full_name}>"


class DoctorSchedule(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "doctor_schedules"
    __table_args__ = (
        db.Index("ix_schedule_doctor_weekday", "doctor_id", "weekday"),
    )

    doctor_id = db.Column(
        db.String(36), db.ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weekday = db.Column(db.Integer, nullable=False)  # 0 = Monday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    break_start = db.Column(db.Time)
    break_end = db.Column(db.Time)
    slot_minutes = db.Column(db.Integer, nullable=False, default=15)
    max_tokens = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    doctor = db.relationship("Doctor", back_populates="schedules")


class DoctorLeave(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "doctor_leaves"
    __table_args__ = (
        db.Index("ix_leave_doctor_dates", "doctor_id", "start_date", "end_date"),
    )

    doctor_id = db.Column(
        db.String(36), db.ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    leave_type = db.Column(db.String(40), nullable=False, default="planned")
    reason = db.Column(db.String(255))
    status = db.Column(db.String(20), nullable=False, default="approved")
    created_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))

    doctor = db.relationship("Doctor", back_populates="leaves")
