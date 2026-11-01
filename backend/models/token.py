from __future__ import annotations

from ..extensions import db
from .base import ClinicScopedMixin, TimestampMixin, UUIDMixin, utcnow


class TokenStatus:
    WAITING = "waiting"
    CALLED = "called"
    IN_CONSULTATION = "in_consultation"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    RECALLED = "recalled"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"

    ALL = [WAITING, CALLED, IN_CONSULTATION, COMPLETED, SKIPPED, RECALLED, CANCELLED, NO_SHOW]
    ACTIVE_QUEUE = [WAITING, CALLED, IN_CONSULTATION, RECALLED]
    CURRENT = [CALLED, IN_CONSULTATION, RECALLED]
    FINISHED = [COMPLETED, SKIPPED, CANCELLED, NO_SHOW]


class VisitType:
    WALK_IN = "walk_in"
    APPOINTMENT = "appointment"
    FOLLOW_UP = "follow_up"
    PRIORITY = "priority"
    EMERGENCY = "emergency"

    ALL = [WALK_IN, APPOINTMENT, FOLLOW_UP, PRIORITY, EMERGENCY]


class DailyToken(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "daily_tokens"
    __table_args__ = (
        db.UniqueConstraint(
            "clinic_id", "token_date", "queue_key", "token_number",
            name="uq_token_clinic_date_queue_number",
        ),
        db.UniqueConstraint("appointment_id", name="uq_token_appointment"),
        db.UniqueConstraint("consultation_id", name="uq_token_consultation"),
        db.Index("ix_token_clinic_date_doctor", "clinic_id", "token_date", "doctor_id"),
        db.Index("ix_token_clinic_date_status", "clinic_id", "token_date", "status"),
        db.Index("ix_token_clinic_date_queue", "clinic_id", "token_date", "queue_key"),
        db.Index("ix_token_created", "clinic_id", "created_at"),
    )

    doctor_id = db.Column(
        db.String(36), db.ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    patient_id = db.Column(
        db.String(36), db.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    appointment_id = db.Column(
        db.String(36), db.ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    follow_up_plan_id = db.Column(
        db.String(36), db.ForeignKey("follow_up_plans.id", ondelete="SET NULL"), nullable=True
    )
    consultation_id = db.Column(
        db.String(36), db.ForeignKey("consultations.id", ondelete="SET NULL"), nullable=True
    )
    token_date = db.Column(db.Date, nullable=False, index=True)
    queue_key = db.Column(db.String(40), nullable=False)
    token_number = db.Column(db.Integer, nullable=False)
    display_number = db.Column(db.String(12), nullable=False)
    visit_type = db.Column(db.String(30), nullable=False, default=VisitType.WALK_IN)
    status = db.Column(db.String(20), nullable=False, default=TokenStatus.WAITING)
    priority = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text)
    skip_reason = db.Column(db.String(255))
    called_at = db.Column(db.DateTime(timezone=True))
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    recall_count = db.Column(db.Integer, nullable=False, default=0)
    transferred_from_id = db.Column(
        db.String(36), db.ForeignKey("daily_tokens.id", ondelete="SET NULL")
    )
    created_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))

    patient = db.relationship("Patient", foreign_keys=[patient_id])
    doctor = db.relationship("Doctor", foreign_keys=[doctor_id])
    appointment = db.relationship("Appointment", back_populates="token", foreign_keys=[appointment_id])
    follow_up_plan = db.relationship("FollowUpPlan", back_populates="tokens", foreign_keys=[follow_up_plan_id])
    consultation = db.relationship("Consultation", foreign_keys=[consultation_id], uselist=False)
    creator = db.relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<Token {self.token_date} {self.display_number}>"


class TokenSequence(UUIDMixin, db.Model):
    __tablename__ = "token_sequences"
    __table_args__ = (
        db.UniqueConstraint(
            "clinic_id", "token_date", "queue_key", name="uq_token_seq_clinic_date_queue"
        ),
    )

    clinic_id = db.Column(
        db.String(36), db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False
    )
    token_date = db.Column(db.Date, nullable=False)
    queue_key = db.Column(db.String(40), nullable=False)
    last_number = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
