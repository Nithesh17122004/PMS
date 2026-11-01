from __future__ import annotations

from datetime import date

from sqlalchemy import or_

from ..auth.security import audit
from ..extensions import db
from ..models import (
    Appointment,
    Consultation,
    DailyToken,
    FollowUpPlan,
    Invoice,
    LabOrder,
    MedicalDocument,
    Notification,
    Patient,
    Payment,
    Prescription,
)
from ..utils.crypto import blind_index, normalize_email, normalize_phone
from ..utils.datetime_utils import clinic_today
from ..utils.errors import ConflictError, ValidationError
from .sequence_service import format_document_number, next_document_number

GENDERS = {"male", "female", "other", "prefer_not_to_say"}


def _validate_patient_payload(payload: dict, existing: Patient | None = None) -> dict:
    first_name = (payload.get("first_name") or (existing.first_name if existing else "")).strip()
    last_name = (payload.get("last_name") or (existing.last_name if existing else "")).strip()
    if not first_name:
        raise ValidationError("First name is required.")
    if not last_name:
        raise ValidationError("Last name is required.")
    if len(first_name) > 80 or len(last_name) > 80:
        raise ValidationError("Patient name is too long.")

    gender = payload.get("gender", existing.gender if existing else "other")
    if gender not in GENDERS:
        raise ValidationError("Select a valid gender.")

    dob = None
    dob_raw = payload.get("date_of_birth", existing.date_of_birth if existing else None)
    if dob_raw:
        try:
            dob = date.fromisoformat(str(dob_raw)[:10]) if not isinstance(dob_raw, date) else dob_raw
        except ValueError:
            raise ValidationError("Date of birth must be a valid date.")
        if dob > date.today():
            raise ValidationError("Date of birth cannot be in the future.")

    age = payload.get("age_years", existing.age_years if existing else None)
    if age not in (None, ""):
        try:
            age = int(age)
        except (TypeError, ValueError):
            raise ValidationError("Age must be a whole number.")
        if age < 0 or age > 130:
            raise ValidationError("Age must be between 0 and 130.")
    if not dob and age is None:
        raise ValidationError("Provide a date of birth or an age.")

    phone = payload.get("phone", existing.phone if existing else None)
    digits = normalize_phone(phone)
    if not existing and not digits:
        raise ValidationError("A contact phone number is required.")
    if phone and len(digits) < 7:
        raise ValidationError("Enter a valid phone number.")

    email = normalize_email(payload.get("email", existing.email if existing else None))
    if email:
        import re

        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise ValidationError("Enter a valid email address.")
    return {
        "first_name": first_name,
        "last_name": last_name,
        "gender": gender,
        "date_of_birth": dob,
        "age_years": age,
        "phone": phone,
        "email": email or None,
    }


def find_duplicates(clinic, payload: dict, exclude_id: str | None = None) -> list[Patient]:
    conditions = []
    phone = normalize_phone(payload.get("phone"))
    if phone:
        conditions.append(Patient.phone_hash == blind_index(phone))
    first = (payload.get("first_name") or "").strip()
    last = (payload.get("last_name") or "").strip()
    dob_raw = payload.get("date_of_birth")
    if first and last and dob_raw:
        try:
            dob = date.fromisoformat(str(dob_raw)[:10])
            conditions.append(
                db.and_(
                    db.func.lower(Patient.first_name) == first.lower(),
                    db.func.lower(Patient.last_name) == last.lower(),
                    Patient.date_of_birth == dob,
                )
            )
        except ValueError:
            pass
    if not conditions:
        return []
    query = Patient.query.filter(
        Patient.clinic_id == clinic.id,
        Patient.is_active.is_(True),
        Patient.merged_into_id.is_(None),
        or_(*conditions),
    )
    if exclude_id:
        query = query.filter(Patient.id != exclude_id)
    return query.limit(10).all()


def create_patient(clinic, actor, payload: dict, override_duplicate=False, duplicate_reason=None) -> Patient:
    data = _validate_patient_payload(payload)
    duplicates = find_duplicates(clinic, data)
    if duplicates and not override_duplicate:
        raise ConflictError(
            "A patient with the same phone number or name and date of birth already exists.",
            details={
                "duplicates": [
                    {
                        "id": p.id,
                        "patient_code": p.patient_code,
                        "full_name": p.full_name,
                        "age": p.age,
                        "phone_masked": ("*" * max(0, len(normalize_phone(p.phone)) - 4)) + normalize_phone(p.phone)[-4:],
                    }
                    for p in duplicates
                ]
            },
        )
    if duplicates and override_duplicate and not (duplicate_reason and len(duplicate_reason.strip()) >= 5):
        raise ValidationError("A reason is required when registering a possible duplicate patient.")

    prefix = ((clinic.settings.patient_prefix if clinic.settings else "P") or "P").strip().rstrip("-")
    number = next_document_number(clinic.id, "patient")
    patient = Patient(
        clinic_id=clinic.id,
        patient_code=format_document_number(f"{prefix}-", number, width=6),
        first_name=data["first_name"],
        last_name=data["last_name"],
        date_of_birth=data["date_of_birth"],
        age_years=data["age_years"],
        gender=data["gender"],
        blood_group=(payload.get("blood_group") or None),
        email=data["email"],
        alternate_phone=(payload.get("alternate_phone") or None),
        emergency_contact_name=(payload.get("emergency_contact_name") or None),
        emergency_contact_relation=(payload.get("emergency_contact_relation") or None),
        emergency_contact_phone=(payload.get("emergency_contact_phone") or None),
        address_line1=(payload.get("address_line1") or None),
        address_line2=(payload.get("address_line2") or None),
        city=(payload.get("city") or None),
        state=(payload.get("state") or None),
        postal_code=(payload.get("postal_code") or None),
        country=(payload.get("country") or "India"),
        allergies=(payload.get("allergies") or None),
        medical_history=(payload.get("medical_history") or None),
        notes=(payload.get("notes") or None),
        consent_email=bool(payload.get("consent_email", False)),
        consent_sms=bool(payload.get("consent_sms", False)),
        consent_whatsapp=bool(payload.get("consent_whatsapp", False)),
        preferred_contact=(payload.get("preferred_contact") or "phone"),
        created_by=actor.id,
    )
    patient.set_phone(data["phone"])
    db.session.add(patient)
    db.session.flush()
    audit(
        "patient.created",
        "patient",
        patient.id,
        {
            "patient_code": patient.patient_code,
            "duplicate_override": bool(duplicates),
            "duplicate_reason": duplicate_reason if duplicates else None,
        },
        clinic_id=clinic.id,
        user_id=actor.id,
    )
    db.session.commit()
    return patient


def update_patient(patient: Patient, actor, payload: dict) -> Patient:
    data = _validate_patient_payload(payload, patient)
    patient.first_name = data["first_name"]
    patient.last_name = data["last_name"]
    patient.gender = data["gender"]
    patient.date_of_birth = data["date_of_birth"]
    patient.age_years = data["age_years"]
    patient.set_phone(data["phone"])
    patient.email = data["email"]
    for field in (
        "blood_group", "alternate_phone", "emergency_contact_name", "emergency_contact_relation",
        "emergency_contact_phone", "address_line1", "address_line2", "city", "state",
        "postal_code", "country", "allergies", "medical_history", "notes", "preferred_contact",
    ):
        if field in payload:
            value = payload.get(field)
            setattr(patient, field, value if value not in ("", None) else None)
    for field in ("consent_email", "consent_sms", "consent_whatsapp"):
        if field in payload:
            setattr(patient, field, bool(payload.get(field)))
    audit("patient.updated", "patient", patient.id, clinic_id=patient.clinic_id, user_id=actor.id)
    db.session.commit()
    return patient


def search_patients(clinic, term: str, limit: int = 20) -> list[Patient]:
    term = (term or "").strip()
    if not term:
        return (
            Patient.query.filter_by(clinic_id=clinic.id, is_active=True)
            .order_by(Patient.created_at.desc())
            .limit(limit)
            .all()
        )
    digits = normalize_phone(term)
    conditions = [
        Patient.patient_code.ilike(f"%{term}%"),
        Patient.first_name.ilike(f"%{term}%"),
        Patient.last_name.ilike(f"%{term}%"),
        (Patient.first_name + " " + Patient.last_name).ilike(f"%{term}%"),
    ]
    if len(digits) >= 4:
        conditions.append(Patient.phone_hash == blind_index(digits))
        conditions.append(Patient.phone_last4 == digits[-4:])
    return (
        Patient.query.filter(
            Patient.clinic_id == clinic.id,
            Patient.is_active.is_(True),
            Patient.merged_into_id.is_(None),
            or_(*conditions),
        )
        .order_by(Patient.created_at.desc())
        .limit(limit)
        .all()
    )


def merge_patients(clinic, actor, source: Patient, target: Patient, reason: str) -> dict:
    if source.id == target.id:
        raise ValidationError("Select two different patients.")
    if source.clinic_id != clinic.id or target.clinic_id != clinic.id:
        raise ValidationError("Both patients must belong to this clinic.")
    if source.merged_into_id or not source.is_active:
        raise ValidationError("The source patient is already inactive or merged.")
    if target.merged_into_id or not target.is_active:
        raise ValidationError("The target patient must be an active patient record.")
    if not reason or len(reason.strip()) < 10:
        raise ValidationError("Provide a clear reason for merging these records.")

    counts = {}
    for model, field in (
        (Appointment, "patient_id"),
        (DailyToken, "patient_id"),
        (Consultation, "patient_id"),
        (Prescription, "patient_id"),
        (FollowUpPlan, "patient_id"),
        (Invoice, "patient_id"),
        (Payment, "patient_id"),
        (LabOrder, "patient_id"),
        (MedicalDocument, "patient_id"),
        (Notification, "patient_id"),
    ):
        count = model.query.filter(getattr(model, field) == source.id).update(
            {getattr(model, field): target.id}, synchronize_session=False
        )
        counts[model.__tablename__] = count
    source.merged_into_id = target.id
    source.is_active = False
    source.notes = ((source.notes or "") + f"\nMerged into {target.patient_code}: {reason.strip()}").strip()
    audit(
        "patient.merged",
        "patient",
        source.id,
        {"target_patient_id": target.id, "reason": reason[:200], "moved": counts},
        clinic_id=clinic.id,
        user_id=actor.id,
    )
    db.session.commit()
    return {"source": source, "target": target, "moved": counts}


def patient_context(clinic, patient: Patient) -> dict:
    """Aggregate profile tab data with strict tenant scoping."""
    appointments = (
        Appointment.query.filter_by(clinic_id=clinic.id, patient_id=patient.id)
        .order_by(Appointment.appointment_date.desc(), Appointment.start_time.desc())
        .limit(50)
        .all()
    )
    tokens = (
        DailyToken.query.filter_by(clinic_id=clinic.id, patient_id=patient.id)
        .order_by(DailyToken.token_date.desc(), DailyToken.token_number.desc())
        .limit(50)
        .all()
    )
    consultations = (
        Consultation.query.filter_by(clinic_id=clinic.id, patient_id=patient.id)
        .order_by(Consultation.created_at.desc())
        .limit(50)
        .all()
    )
    prescriptions = (
        Prescription.query.filter_by(clinic_id=clinic.id, patient_id=patient.id)
        .order_by(Prescription.created_at.desc())
        .limit(50)
        .all()
    )
    followups = (
        FollowUpPlan.query.filter_by(clinic_id=clinic.id, patient_id=patient.id)
        .order_by(FollowUpPlan.due_date.desc())
        .limit(50)
        .all()
    )
    invoices = (
        Invoice.query.filter_by(clinic_id=clinic.id, patient_id=patient.id)
        .order_by(Invoice.created_at.desc())
        .limit(50)
        .all()
    )
    lab_orders = (
        LabOrder.query.filter_by(clinic_id=clinic.id, patient_id=patient.id)
        .order_by(LabOrder.created_at.desc())
        .limit(50)
        .all()
    )
    documents = (
        MedicalDocument.query.filter_by(clinic_id=clinic.id, patient_id=patient.id)
        .order_by(MedicalDocument.created_at.desc())
        .all()
    )
    return {
        "appointments": appointments,
        "tokens": tokens,
        "consultations": consultations,
        "prescriptions": prescriptions,
        "followups": followups,
        "invoices": invoices,
        "lab_orders": lab_orders,
        "documents": documents,
    }
