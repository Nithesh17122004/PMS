from __future__ import annotations

from datetime import datetime, timezone

from ..auth.security import audit
from ..extensions import db
from ..models import (
    AppointmentStatus,
    Consultation,
    ConsultationStatus,
    DailyToken,
    Diagnosis,
    Doctor,
    FollowUpStatus,
    Medication,
    Patient,
    Prescription,
    PrescriptionItem,
    PrescriptionStatus,
    TokenStatus,
)
from ..utils.datetime_utils import clinic_today, parse_date
from ..utils.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from .followup_service import create_followup
from .sequence_service import format_document_number, next_document_number

VITAL_FIELDS = {"blood_pressure", "pulse", "temperature", "weight_kg", "height_cm", "spo2", "respiratory_rate"}


def _doctor_for_actor(actor) -> Doctor:
    doctor = getattr(actor, "doctor_profile", None)
    if doctor is None:
        raise ForbiddenError("Clinical records can only be created by a doctor.")
    return doctor


def ensure_consultation_author(consultation: Consultation, actor) -> None:
    doctor = _doctor_for_actor(actor)
    if consultation.doctor_id != doctor.id:
        raise ForbiddenError("You can only author your own consultations.")


def start_consultation_for_token(token: DailyToken, actor) -> Consultation:
    doctor = _doctor_for_actor(actor)
    if token.doctor_id != doctor.id:
        raise ForbiddenError("You can only start consultations in your own queue.")
    if token.status not in (TokenStatus.CALLED, TokenStatus.RECALLED):
        raise ConflictError("Call the patient before starting the consultation.")
    if token.consultation_id:
        consultation = db.session.get(Consultation, token.consultation_id)
        if consultation:
            return consultation
    number = next_document_number(token.clinic_id, "consultation")
    consultation = Consultation(
        clinic_id=token.clinic_id,
        consultation_code=format_document_number("CONS-", number, width=6),
        patient_id=token.patient_id,
        doctor_id=token.doctor_id,
        appointment_id=token.appointment_id,
        status=ConsultationStatus.DRAFT,
        started_at=datetime.now(timezone.utc),
        created_by=actor.id,
    )
    db.session.add(consultation)
    db.session.flush()
    token.consultation_id = consultation.id
    token.status = TokenStatus.IN_CONSULTATION
    token.started_at = datetime.now(timezone.utc)
    audit(
        "consultation.started",
        "consultation",
        consultation.id,
        {"token_id": token.id, "doctor_id": doctor.id},
        clinic_id=token.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return consultation


def save_consultation(consultation: Consultation, actor, payload: dict) -> Consultation:
    ensure_consultation_author(consultation, actor)
    if consultation.status != ConsultationStatus.DRAFT:
        raise ConflictError("Completed consultations are immutable. Create an addendum instead.")
    if "symptoms" in payload:
        consultation.symptoms = (payload.get("symptoms") or "")[:10000] or None
    if "observations" in payload:
        consultation.observations = (payload.get("observations") or "")[:10000] or None
    if "vitals" in payload:
        vitals = payload.get("vitals") or {}
        if not isinstance(vitals, dict):
            raise ValidationError("Vitals must be an object.")
        consultation.vitals = {
            key: str(value)[:40]
            for key, value in vitals.items()
            if key in VITAL_FIELDS and value not in (None, "")
        }
    if "diagnosis_summary" in payload:
        consultation.diagnosis_summary = (payload.get("diagnosis_summary") or "")[:10000] or None
    if "treatment_plan" in payload:
        consultation.treatment_plan = (payload.get("treatment_plan") or "")[:10000] or None
    if "doctor_notes" in payload:
        consultation.doctor_notes = (payload.get("doctor_notes") or "")[:10000] or None
    if "follow_up_required" in payload:
        consultation.follow_up_required = bool(payload.get("follow_up_required"))
    if "follow_up_notes" in payload:
        consultation.follow_up_notes = (payload.get("follow_up_notes") or "")[:2000] or None
    if "diagnoses" in payload:
        diagnoses = payload.get("diagnoses") or []
        if not isinstance(diagnoses, list):
            raise ValidationError("Diagnoses must be a list.")
        Diagnosis.query.filter_by(consultation_id=consultation.id).delete()
        for index, item in enumerate(diagnoses[:20]):
            description = (item.get("description") or "").strip()
            if not description:
                continue
            db.session.add(
                Diagnosis(
                    consultation_id=consultation.id,
                    clinic_id=consultation.clinic_id,
                    icd_code=(item.get("icd_code") or "")[:20] or None,
                    description=description[:300],
                    diagnosis_type=(item.get("diagnosis_type") or ("primary" if index == 0 else "secondary"))[:20],
                    notes=(item.get("notes") or "")[:255] or None,
                )
            )
    audit(
        "consultation.draft_saved",
        "consultation",
        consultation.id,
        {"doctor_id": consultation.doctor_id},
        clinic_id=consultation.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return consultation


def complete_consultation(consultation: Consultation, actor, payload: dict | None = None) -> Consultation:
    ensure_consultation_author(consultation, actor)
    if consultation.status != ConsultationStatus.DRAFT:
        raise ConflictError("This consultation has already been completed.")
    payload = payload or {}
    if payload:
        save_consultation(consultation, actor, payload)
    diagnoses = Diagnosis.query.filter_by(consultation_id=consultation.id).all()
    if not (consultation.diagnosis_summary or "").strip() and not diagnoses:
        raise ValidationError("Add a diagnosis before completing the consultation.")
    if not (consultation.treatment_plan or "").strip():
        raise ValidationError("Add a treatment plan before completing the consultation.")

    follow_up_plan = None
    if consultation.follow_up_required:
        due_date = payload.get("follow_up_date")
        if not due_date:
            raise ValidationError("Select a follow-up date.")
        follow_up_plan = create_followup(
            clinic=consultation.doctor.clinic,
            actor=actor,
            patient=consultation.patient,
            doctor=consultation.doctor,
            consultation=consultation,
            due_date=due_date,
            instructions=payload.get("follow_up_instructions") or consultation.follow_up_notes,
            priority=payload.get("follow_up_priority") or "normal",
        )

    now = datetime.now(timezone.utc)
    consultation.status = ConsultationStatus.COMPLETED
    consultation.completed_at = now
    consultation.completed_by = actor.id
    token = consultation.token
    if token:
        token.status = TokenStatus.COMPLETED
        token.completed_at = now
        if token.appointment and token.appointment.status in AppointmentStatus.ACTIVE:
            token.appointment.status = AppointmentStatus.COMPLETED
        if token.follow_up_plan and token.follow_up_plan.status not in (
            FollowUpStatus.COMPLETED,
            FollowUpStatus.CANCELLED,
        ):
            token.follow_up_plan.status = FollowUpStatus.COMPLETED
            token.follow_up_plan.completed_at = now
    audit(
        "consultation.completed",
        "consultation",
        consultation.id,
        {"doctor_id": consultation.doctor_id, "follow_up_plan_id": follow_up_plan.id if follow_up_plan else None},
        clinic_id=consultation.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return consultation


def issue_prescription(consultation: Consultation, actor, payload: dict) -> Prescription:
    ensure_consultation_author(consultation, actor)
    if consultation.status == ConsultationStatus.CANCELLED:
        raise ConflictError("Cannot issue a prescription for a cancelled consultation.")
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        raise ValidationError("Add at least one medicine.")
    if len(items) > 50:
        raise ValidationError("A prescription cannot contain more than 50 items.")
    number = next_document_number(consultation.clinic_id, "prescription")
    prescription = Prescription(
        clinic_id=consultation.clinic_id,
        consultation_id=consultation.id,
        patient_id=consultation.patient_id,
        doctor_id=consultation.doctor_id,
        prescription_code=format_document_number("RX-", number, width=6),
        status=PrescriptionStatus.ISSUED,
        notes=(payload.get("notes") or "")[:2000] or None,
        created_by=actor.id,
    )
    db.session.add(prescription)
    db.session.flush()
    for index, item in enumerate(items):
        medicine_name = (item.get("medicine_name") or "").strip()
        dosage = (item.get("dosage") or "").strip()
        frequency = (item.get("frequency") or "").strip()
        if not medicine_name or not dosage or not frequency:
            raise ValidationError("Each medicine needs a name, dosage and frequency.")
        medication_id = item.get("medication_id")
        if medication_id:
            medication = Medication.query.filter_by(
                id=medication_id, clinic_id=consultation.clinic_id
            ).first()
            if medication is None:
                medication_id = None
        db.session.add(
            PrescriptionItem(
                prescription_id=prescription.id,
                clinic_id=consultation.clinic_id,
                medication_id=medication_id or None,
                medicine_name=medicine_name[:160],
                strength=(item.get("strength") or "")[:60] or None,
                form=(item.get("form") or "")[:40] or None,
                dosage=dosage[:80],
                frequency=frequency[:80],
                duration_days=int(item.get("duration_days") or 0) or None,
                quantity=(str(item.get("quantity")) if item.get("quantity") not in (None, "") else None),
                instructions=(item.get("instructions") or "")[:255] or None,
                sort_order=index,
            )
        )
    audit(
        "prescription.issued",
        "prescription",
        prescription.id,
        {"consultation_id": consultation.id, "item_count": len(items)},
        clinic_id=consultation.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return prescription


def cancel_prescription(prescription: Prescription, actor, reason: str) -> Prescription:
    doctor = getattr(actor, "doctor_profile", None)
    if prescription.doctor_id != (doctor.id if doctor else None):
        raise ForbiddenError("Only the issuing doctor can cancel this prescription.")
    if prescription.status == PrescriptionStatus.CANCELLED:
        raise ConflictError("This prescription is already cancelled.")
    if not reason or len(reason.strip()) < 3:
        raise ValidationError("A cancellation reason is required.")
    prescription.status = PrescriptionStatus.CANCELLED
    prescription.notes = ((prescription.notes or "") + f"\nCancelled: {reason[:300]}").strip()
    audit(
        "prescription.cancelled",
        "prescription",
        prescription.id,
        {"reason": reason[:150]},
        clinic_id=prescription.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return prescription


def create_standalone_draft(clinic, actor, patient: Patient, doctor: Doctor) -> Consultation:
    actor_doctor = _doctor_for_actor(actor)
    if actor_doctor.id != doctor.id:
        raise ForbiddenError("You can only create your own consultations.")
    number = next_document_number(clinic.id, "consultation")
    consultation = Consultation(
        clinic_id=clinic.id,
        consultation_code=format_document_number("CONS-", number, width=6),
        patient_id=patient.id,
        doctor_id=doctor.id,
        status=ConsultationStatus.DRAFT,
        started_at=datetime.now(timezone.utc),
        created_by=actor.id,
    )
    db.session.add(consultation)
    db.session.flush()
    audit(
        "consultation.started",
        "consultation",
        consultation.id,
        {"doctor_id": doctor.id, "standalone": True},
        clinic_id=clinic.id,
        user_id=actor.id,
    )
    db.session.commit()
    return consultation
