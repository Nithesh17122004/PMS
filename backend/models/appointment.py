from __future__ import annotations

from ..extensions import db
from .base import ClinicScopedMixin, TimestampMixin, UUIDMixin


class AppointmentStatus:
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"

    ALL = [SCHEDULED, CONFIRMED, CHECKED_IN, COMPLETED, CANCELLED, NO_SHOW, RESCHEDULED]
    ACTIVE = [SCHEDULED, CONFIRMED, CHECKED_IN]


class Appointment(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "appointments"
    __table_args__ = (
        db.UniqueConstraint("clinic_id", "appointment_code", name="uq_appointment_clinic_code"),
        db.Index("ix_appt_clinic_doctor_date", "clinic_id", "doctor_id", "appointment_date"),
        db.Index("ix_appt_clinic_patient_date", "clinic_id", "patient_id", "appointment_date"),
        db.Index("ix_appt_clinic_date_status", "clinic_id", "appointment_date", "status"),
    )

    appointment_code = db.Column(db.String(30), nullable=False, index=True)
    patient_id = db.Column(
        db.String(36), db.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doctor_id = db.Column(
        db.String(36), db.ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    appointment_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=AppointmentStatus.SCHEDULED)
    visit_type = db.Column(db.String(30), nullable=False, default="consultation")
    reason = db.Column(db.String(255))
    notes = db.Column(db.Text)
    source = db.Column(db.String(30), nullable=False, default="reception")
    reminder_sent = db.Column(db.Boolean, nullable=False, default=False)

    created_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    cancelled_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    cancelled_at = db.Column(db.DateTime(timezone=True))
    cancellation_reason = db.Column(db.String(255))
    rescheduled_from_id = db.Column(
        db.String(36), db.ForeignKey("appointments.id", ondelete="SET NULL")
    )
    override_reason = db.Column(db.String(255))
    override_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))

    patient = db.relationship("Patient", foreign_keys=[patient_id])
    doctor = db.relationship("Doctor", foreign_keys=[doctor_id])
    token = db.relationship("DailyToken", back_populates="appointment", uselist=False)

    def __repr__(self) -> str:
        return f"<Appointment {self.appointment_code}>"
