from __future__ import annotations

from datetime import date

from ..extensions import db
from ..utils.crypto import EncryptedString, blind_index, normalize_phone
from .base import ClinicScopedMixin, TimestampMixin, UUIDMixin


class Patient(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "patients"
    __table_args__ = (
        db.UniqueConstraint("clinic_id", "patient_code", name="uq_patient_clinic_code"),
        db.Index("ix_patient_clinic_phone_hash", "clinic_id", "phone_hash"),
        db.Index("ix_patient_clinic_name", "clinic_id", "last_name", "first_name"),
        db.Index("ix_patient_clinic_created", "clinic_id", "created_at"),
        db.Index("ix_patient_clinic_active", "clinic_id", "is_active"),
    )

    patient_code = db.Column(db.String(30), nullable=False, index=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    date_of_birth = db.Column(db.Date)
    age_years = db.Column(db.Integer)
    gender = db.Column(db.String(20), nullable=False, default="other")
    blood_group = db.Column(db.String(8))

    phone = db.Column(EncryptedString)
    phone_hash = db.Column(db.String(64), index=True)
    phone_last4 = db.Column(db.String(4))
    email = db.Column(EncryptedString)
    alternate_phone = db.Column(EncryptedString)
    emergency_contact_name = db.Column(db.String(120))
    emergency_contact_relation = db.Column(db.String(60))
    emergency_contact_phone = db.Column(EncryptedString)

    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    country = db.Column(db.String(80), default="India")

    allergies = db.Column(db.Text)
    medical_history = db.Column(db.Text)
    notes = db.Column(db.Text)

    consent_email = db.Column(db.Boolean, nullable=False, default=False)
    consent_sms = db.Column(db.Boolean, nullable=False, default=False)
    consent_whatsapp = db.Column(db.Boolean, nullable=False, default=False)
    preferred_contact = db.Column(db.String(20), nullable=False, default="phone")

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    merged_into_id = db.Column(
        db.String(36), db.ForeignKey("patients.id", ondelete="SET NULL"), nullable=True
    )
    created_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))

    merged_into = db.relationship("Patient", remote_side="Patient.id", foreign_keys=[merged_into_id])
    documents = db.relationship(
        "MedicalDocument", back_populates="patient", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def age(self) -> int | None:
        if self.date_of_birth:
            today = date.today()
            return (
                today.year
                - self.date_of_birth.year
                - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
            )
        return self.age_years

    def set_phone(self, value: str | None) -> None:
        normalized = normalize_phone(value)
        self.phone = value
        self.phone_hash = blind_index(normalized) if normalized else None
        self.phone_last4 = normalized[-4:] if len(normalized) >= 4 else None

    def __repr__(self) -> str:
        return f"<Patient {self.patient_code}>"


class MedicalDocument(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "medical_documents"
    __table_args__ = (
        db.Index("ix_documents_patient", "clinic_id", "patient_id", "created_at"),
    )

    patient_id = db.Column(
        db.String(36), db.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    mime_type = db.Column(db.String(120))
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    category = db.Column(db.String(60), nullable=False, default="general")
    description = db.Column(db.String(255))

    patient = db.relationship("Patient", back_populates="documents")
    uploader = db.relationship("User", foreign_keys=[uploaded_by])
