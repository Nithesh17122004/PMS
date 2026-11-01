from __future__ import annotations

from ..extensions import db
from .base import ClinicScopedMixin, TimestampMixin, UUIDMixin, utcnow


class FollowUpStatus:
    UPCOMING = "upcoming"
    CONFIRMED = "confirmed"
    ARRIVED = "arrived"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    MISSED = "missed"
    RESCHEDULED = "rescheduled"

    ALL = [UPCOMING, CONFIRMED, ARRIVED, COMPLETED, CANCELLED, MISSED, RESCHEDULED]


class FollowUpPlan(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "follow_up_plans"
    __table_args__ = (
        db.Index("ix_followup_clinic_due_status", "clinic_id", "due_date", "status"),
        db.Index("ix_followup_clinic_patient", "clinic_id", "patient_id", "due_date"),
        db.Index("ix_followup_clinic_doctor", "clinic_id", "doctor_id", "due_date"),
    )

    patient_id = db.Column(
        db.String(36), db.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doctor_id = db.Column(
        db.String(36), db.ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False
    )
    consultation_id = db.Column(
        db.String(36), db.ForeignKey("consultations.id", ondelete="SET NULL"), nullable=True
    )
    appointment_id = db.Column(
        db.String(36), db.ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    due_date = db.Column(db.Date, nullable=False, index=True)
    original_due_date = db.Column(db.Date, nullable=False)
    instructions = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default=FollowUpStatus.UPCOMING)
    priority = db.Column(db.String(20), nullable=False, default="normal")
    contact_notes = db.Column(db.Text)
    confirmed_at = db.Column(db.DateTime(timezone=True))
    arrived_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    cancelled_at = db.Column(db.DateTime(timezone=True))
    cancellation_reason = db.Column(db.String(255))
    rescheduled_count = db.Column(db.Integer, nullable=False, default=0)
    reminder_count = db.Column(db.Integer, nullable=False, default=0)
    last_reminder_at = db.Column(db.DateTime(timezone=True))
    created_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))

    patient = db.relationship("Patient", foreign_keys=[patient_id])
    doctor = db.relationship("Doctor", foreign_keys=[doctor_id])
    consultation = db.relationship("Consultation", back_populates="follow_ups", foreign_keys=[consultation_id])
    appointment = db.relationship("Appointment", foreign_keys=[appointment_id])
    tokens = db.relationship("DailyToken", back_populates="follow_up_plan", foreign_keys="DailyToken.follow_up_plan_id")
    reminders = db.relationship(
        "FollowUpReminder", back_populates="plan", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<FollowUp {self.due_date} {self.status}>"


class ReminderStatus:
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class FollowUpReminder(UUIDMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "follow_up_reminders"
    __table_args__ = (
        db.UniqueConstraint("dedupe_key", name="uq_followup_reminder_dedupe"),
        db.Index("ix_followup_reminder_plan", "follow_up_plan_id", "created_at"),
    )

    follow_up_plan_id = db.Column(
        db.String(36), db.ForeignKey("follow_up_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel = db.Column(db.String(20), nullable=False)
    reminder_type = db.Column(db.String(30), nullable=False)
    scheduled_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=ReminderStatus.QUEUED)
    sent_at = db.Column(db.DateTime(timezone=True))
    provider = db.Column(db.String(40))
    provider_message_id = db.Column(db.String(120))
    error = db.Column(db.String(255))
    dedupe_key = db.Column(db.String(190), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    plan = db.relationship("FollowUpPlan", back_populates="reminders")
