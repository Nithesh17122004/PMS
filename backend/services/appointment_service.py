from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.exc import IntegrityError, OperationalError

from ..auth.security import audit
from ..extensions import db
from ..models import (
    Appointment,
    AppointmentStatus,
    Doctor,
    DoctorLeave,
    FollowUpPlan,
    FollowUpStatus,
    Patient,
    TokenStatus,
)
from ..utils.datetime_utils import clinic_now, clinic_today, parse_date, parse_time
from ..utils.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from .sequence_service import format_document_number, next_document_number

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _working_day(clinic, day: date) -> bool:
    working_days = clinic.settings.working_days if clinic.settings else WEEKDAYS[:6]
    return WEEKDAYS[day.weekday()] in working_days


def doctor_on_leave(doctor, day: date) -> bool:
    return (
        DoctorLeave.query.filter(
            DoctorLeave.doctor_id == doctor.id,
            DoctorLeave.status == "approved",
            DoctorLeave.start_date <= day,
            DoctorLeave.end_date >= day,
        ).first()
        is not None
    )


def doctor_slots(clinic, doctor, day: date, exclude_appointment_id: str | None = None) -> list[dict]:
    if not doctor.is_active or not doctor.is_available:
        return []
    if not _working_day(clinic, day):
        return []
    if doctor_on_leave(doctor, day):
        return []
    schedules = [
        s for s in doctor.schedules if s.is_active and s.weekday == day.weekday()
    ]
    if not schedules:
        return []
    existing = Appointment.query.filter(
        Appointment.clinic_id == clinic.id,
        Appointment.doctor_id == doctor.id,
        Appointment.appointment_date == day,
        Appointment.status.in_(AppointmentStatus.ACTIVE),
    )
    if exclude_appointment_id:
        existing = existing.filter(Appointment.id != exclude_appointment_id)
    booked = [(a.start_time, a.end_time) for a in existing.all()]
    now = clinic_now(clinic)
    slots = []
    seen = set()
    for schedule in schedules:
        slot_minutes = schedule.slot_minutes or (clinic.settings.slot_minutes if clinic.settings else 15)
        cursor = datetime.combine(day, schedule.start_time)
        end_dt = datetime.combine(day, schedule.end_time)
        while cursor < end_dt:
            slot_end = cursor + timedelta(minutes=slot_minutes)
            if slot_end > end_dt:
                break
            start_t = cursor.time()
            end_t = slot_end.time()
            in_break = False
            if schedule.break_start and schedule.break_end:
                in_break = start_t < schedule.break_end and end_t > schedule.break_start
            overlaps = any(start_t < b_end and end_t > b_start for b_start, b_end in booked)
            past = day == now.date() and cursor.time() <= now.time()
            reason = None
            if past:
                reason = "past"
            elif in_break:
                reason = "break"
            elif overlaps:
                reason = "booked"
            key = (start_t, end_t)
            if key in seen:
                cursor = slot_end
                continue
            seen.add(key)
            slots.append(
                {
                    "start_time": start_t,
                    "end_time": end_t,
                    "available": reason is None,
                    "reason": reason,
                }
            )
            cursor = slot_end
    slots.sort(key=lambda s: s["start_time"])
    return slots


def _validate_booking(clinic, patient_id, doctor_id, day, start_time, can_override=False, override_reason=None, exclude_id=None):
    patient = Patient.query.filter_by(id=patient_id, clinic_id=clinic.id).first()
    if patient is None or not patient.is_active or patient.merged_into_id:
        raise NotFoundError("Patient not found or inactive.")
    doctor = Doctor.query.filter_by(id=doctor_id, clinic_id=clinic.id).first()
    if doctor is None or not doctor.is_active:
        raise NotFoundError("Doctor not found or inactive.")
    if day < clinic_today(clinic):
        raise ValidationError("Appointments cannot be booked in the past.")
    if not _working_day(clinic, day):
        raise ValidationError("The clinic is closed on this day.")
    if doctor_on_leave(doctor, day):
        raise ConflictError("The doctor is on leave on this date.")
    slots = doctor_slots(clinic, doctor, day, exclude_appointment_id=exclude_id)
    slot = next((s for s in slots if s["start_time"] == start_time), None)
    if slot is None:
        raise ValidationError("The selected time is not part of the doctor's schedule.")
    if not slot["available"]:
        if slot.get("reason") != "booked":
            raise ConflictError("This slot is outside the doctor's available hours. Choose another time.")
        if not can_override:
            raise ConflictError("This slot is already booked. Choose another time.")
        if not override_reason or len(override_reason.strip()) < 5:
            raise ValidationError("An override reason is required to double-book this slot.")
    return patient, doctor, slot


def create_appointment(
    clinic,
    actor,
    payload,
    can_override=False,
) -> Appointment:
    patient_id = payload.get("patient_id")
    doctor_id = payload.get("doctor_id")
    day = parse_date(payload.get("appointment_date"), "Appointment date")
    start_time = parse_time(payload.get("start_time"), "Start time")
    if not patient_id or not doctor_id:
        raise ValidationError("Patient and doctor are required.")
    override_reason = payload.get("override_reason")
    last_error = None
    for attempt in range(4):
        try:
            # Row lock serialises overlapping bookings for the same doctor in PostgreSQL.
            Doctor.query.filter_by(id=doctor_id, clinic_id=clinic.id).with_for_update().first()
            patient, doctor, slot = _validate_booking(
                clinic,
                patient_id,
                doctor_id,
                day,
                start_time,
                can_override=can_override,
                override_reason=override_reason,
            )
            end_time = slot["end_time"]
            visit_type = payload.get("visit_type") or "consultation"
            follow_up_plan = None
            follow_up_id = payload.get("follow_up_plan_id")
            if follow_up_id:
                follow_up_plan = FollowUpPlan.query.filter_by(
                    id=follow_up_id, clinic_id=clinic.id, patient_id=patient.id
                ).first()
                if follow_up_plan is None:
                    raise ValidationError("Follow-up record not found for this patient.")
                if follow_up_plan.status in (FollowUpStatus.COMPLETED, FollowUpStatus.CANCELLED):
                    raise ConflictError("This follow-up is already closed.")
                visit_type = "follow_up"
            number = next_document_number(clinic.id, "appointment")
            appointment = Appointment(
                clinic_id=clinic.id,
                appointment_code=format_document_number("APT-", number, width=6),
                patient_id=patient.id,
                doctor_id=doctor.id,
                appointment_date=day,
                start_time=start_time,
                end_time=end_time,
                status=payload.get("status") if payload.get("status") in (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED) else AppointmentStatus.CONFIRMED,
                visit_type=visit_type,
                reason=(payload.get("reason") or None),
                notes=(payload.get("notes") or None),
                source=(payload.get("source") or "reception"),
                created_by=actor.id,
                override_reason=override_reason if can_override else None,
                override_by=actor.id if can_override and override_reason else None,
            )
            db.session.add(appointment)
            db.session.flush()
            if follow_up_plan:
                follow_up_plan.appointment_id = appointment.id
            audit(
                "appointment.created",
                "appointment",
                appointment.id,
                {
                    "doctor_id": doctor.id,
                    "appointment_date": day.isoformat(),
                    "start_time": start_time.isoformat(),
                    "override": bool(can_override and override_reason),
                },
                clinic_id=clinic.id,
                user_id=actor.id,
            )
            db.session.commit()
            return appointment
        except (IntegrityError, OperationalError) as exc:
            last_error = exc
            db.session.rollback()
            continue
        except Exception:
            db.session.rollback()
            raise
    raise ConflictError("The appointment could not be booked due to a concurrent update. Try again.")


def reschedule_appointment(clinic, actor, appointment: Appointment, payload: dict, can_override=False) -> Appointment:
    if appointment.status not in (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED):
        raise ConflictError("Only scheduled or confirmed appointments can be rescheduled.")
    if appointment.token:
        raise ConflictError("This appointment is already checked in. Manage the token instead.")
    new_payload = {
        "patient_id": appointment.patient_id,
        "doctor_id": payload.get("doctor_id") or appointment.doctor_id,
        "appointment_date": payload.get("appointment_date"),
        "start_time": payload.get("start_time"),
        "visit_type": appointment.visit_type,
        "reason": payload.get("reason") or appointment.reason,
        "notes": payload.get("notes") or appointment.notes,
        "source": appointment.source,
        "override_reason": payload.get("override_reason"),
    }
    new_appointment = create_appointment(clinic, actor, new_payload, can_override=can_override)
    appointment.status = AppointmentStatus.RESCHEDULED
    new_appointment.rescheduled_from_id = appointment.id
    audit(
        "appointment.rescheduled",
        "appointment",
        appointment.id,
        {"new_appointment_id": new_appointment.id},
        clinic_id=clinic.id,
        user_id=actor.id,
    )
    db.session.commit()
    return new_appointment


def cancel_appointment(clinic, actor, appointment: Appointment, reason: str) -> Appointment:
    if appointment.status in (AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED):
        raise ConflictError("This appointment is already closed.")
    if appointment.token and appointment.token.status not in (
        TokenStatus.WAITING,
        TokenStatus.CALLED,
        TokenStatus.RECALLED,
        TokenStatus.SKIPPED,
        TokenStatus.NO_SHOW,
    ):
        raise ConflictError("The linked token is already in consultation or completed.")
    if not reason or len(reason.strip()) < 3:
        raise ValidationError("A cancellation reason is required.")
    if appointment.token and appointment.token.status in (
        TokenStatus.WAITING,
        TokenStatus.CALLED,
        TokenStatus.RECALLED,
    ):
        appointment.token.status = TokenStatus.CANCELLED
        appointment.token.skip_reason = "Appointment cancelled"
    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancellation_reason = reason[:255]
    appointment.cancelled_at = datetime.now(timezone.utc)
    appointment.cancelled_by = actor.id
    audit(
        "appointment.cancelled",
        "appointment",
        appointment.id,
        {"reason": reason[:200]},
        clinic_id=clinic.id,
        user_id=actor.id,
    )
    db.session.commit()
    return appointment


def check_in_appointment(clinic, actor, appointment: Appointment):
    from .token_service import generate_token

    if appointment.status not in (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED):
        raise ConflictError("Only scheduled or confirmed appointments can be checked in.")
    if appointment.appointment_date != clinic_today(clinic):
        raise ValidationError("Appointments can only be checked in on their scheduled day.")
    token = generate_token(
        patient=appointment.patient,
        doctor=appointment.doctor,
        visit_type="appointment",
        actor=actor,
        appointment=appointment,
    )
    audit(
        "appointment.checked_in",
        "appointment",
        appointment.id,
        {"token_id": token.id},
        clinic_id=clinic.id,
        user_id=actor.id,
    )
    db.session.commit()
    return token
