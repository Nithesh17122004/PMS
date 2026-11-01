from __future__ import annotations

from ..extensions import db
from .base import ClinicScopedMixin, TimestampMixin, UUIDMixin


class ConsultationStatus:
    DRAFT = "draft"
    COMPLETED = "completed"
    AMENDED = "amended"
    CANCELLED = "cancelled"


class Consultation(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "consultations"
    __table_args__ = (
        db.UniqueConstraint("clinic_id", "consultation_code", name="uq_consultation_clinic_code"),
        db.Index("ix_consult_clinic_doctor_date", "clinic_id", "doctor_id", "created_at"),
        db.Index("ix_consult_clinic_patient", "clinic_id", "patient_id", "created_at"),
    )

    consultation_code = db.Column(db.String(30), nullable=False, index=True)
    patient_id = db.Column(
        db.String(36), db.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doctor_id = db.Column(
        db.String(36), db.ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    appointment_id = db.Column(
        db.String(36), db.ForeignKey("appointments.id", ondelete="SET NULL")
    )
    version = db.Column(db.Integer, nullable=False, default=1)
    previous_consultation_id = db.Column(
        db.String(36), db.ForeignKey("consultations.id", ondelete="SET NULL")
    )
    status = db.Column(db.String(20), nullable=False, default=ConsultationStatus.DRAFT)

    symptoms = db.Column(db.Text)
    observations = db.Column(db.Text)
    vitals = db.Column(db.JSON, nullable=False, default=dict)
    diagnosis_summary = db.Column(db.Text)
    treatment_plan = db.Column(db.Text)
    doctor_notes = db.Column(db.Text)
    follow_up_required = db.Column(db.Boolean, nullable=False, default=False)
    follow_up_notes = db.Column(db.Text)
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    created_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    completed_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))

    patient = db.relationship("Patient", foreign_keys=[patient_id])
    doctor = db.relationship("Doctor", foreign_keys=[doctor_id])
    appointment = db.relationship("Appointment", foreign_keys=[appointment_id])
    diagnoses = db.relationship(
        "Diagnosis", back_populates="consultation", cascade="all, delete-orphan"
    )
    prescriptions = db.relationship(
        "Prescription", back_populates="consultation", cascade="all, delete-orphan"
    )
    token = db.relationship(
        "DailyToken",
        back_populates="consultation",
        foreign_keys="DailyToken.consultation_id",
        uselist=False,
    )
    follow_ups = db.relationship(
        "FollowUpPlan", back_populates="consultation", foreign_keys="FollowUpPlan.consultation_id"
    )

    def __repr__(self) -> str:
        return f"<Consultation {self.consultation_code}>"


class Diagnosis(UUIDMixin, db.Model):
    __tablename__ = "diagnoses"
    __table_args__ = (db.Index("ix_diagnosis_consultation", "consultation_id"),)

    consultation_id = db.Column(
        db.String(36), db.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False
    )
    clinic_id = db.Column(
        db.String(36), db.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )
    icd_code = db.Column(db.String(20))
    description = db.Column(db.String(300), nullable=False)
    diagnosis_type = db.Column(db.String(20), nullable=False, default="primary")
    notes = db.Column(db.String(255))
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=__import__("datetime").datetime.utcnow
    )

    consultation = db.relationship("Consultation", back_populates="diagnoses")


class PrescriptionStatus:
    ISSUED = "issued"
    CANCELLED = "cancelled"


class Prescription(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "prescriptions"
    __table_args__ = (
        db.UniqueConstraint("clinic_id", "prescription_code", name="uq_prescription_clinic_code"),
        db.Index("ix_prescription_clinic_patient", "clinic_id", "patient_id", "created_at"),
    )

    consultation_id = db.Column(
        db.String(36), db.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id = db.Column(
        db.String(36), db.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    doctor_id = db.Column(
        db.String(36), db.ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False
    )
    prescription_code = db.Column(db.String(30), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default=PrescriptionStatus.ISSUED)
    issued_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=__import__("datetime").datetime.utcnow
    )
    notes = db.Column(db.Text)
    created_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))

    consultation = db.relationship("Consultation", back_populates="prescriptions")
    patient = db.relationship("Patient", foreign_keys=[patient_id])
    doctor = db.relationship("Doctor", foreign_keys=[doctor_id])
    items = db.relationship(
        "PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan",
        order_by="PrescriptionItem.sort_order",
    )

    def __repr__(self) -> str:
        return f"<Prescription {self.prescription_code}>"


class PrescriptionItem(UUIDMixin, db.Model):
    __tablename__ = "prescription_items"

    prescription_id = db.Column(
        db.String(36), db.ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clinic_id = db.Column(
        db.String(36), db.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )
    medication_id = db.Column(
        db.String(36), db.ForeignKey("medications.id", ondelete="SET NULL"), nullable=True
    )
    medicine_name = db.Column(db.String(160), nullable=False)
    strength = db.Column(db.String(60))
    form = db.Column(db.String(40))
    dosage = db.Column(db.String(80), nullable=False)
    frequency = db.Column(db.String(80), nullable=False)
    duration_days = db.Column(db.Integer)
    quantity = db.Column(db.String(40))
    instructions = db.Column(db.String(255))
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    prescription = db.relationship("Prescription", back_populates="items")
    medication = db.relationship("Medication", foreign_keys=[medication_id])
