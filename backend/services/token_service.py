from __future__ import annotations

import logging
from datetime import datetime, timezone
from statistics import mean

from flask import g
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, OperationalError

from ..auth.security import audit
from ..extensions import db
from ..models import (
    Appointment,
    AppointmentStatus,
    DailyToken,
    Doctor,
    FollowUpPlan,
    FollowUpStatus,
    NotificationChannel,
    Patient,
    TokenStatus,
    VisitType,
)
from ..permissions.tenant import current_clinic, current_doctor, current_user
from ..utils.datetime_utils import clinic_now, clinic_today, minutes_between
from ..utils.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from .notification_service import (
    deliver_notification,
    notify_staff,
    queue_patient_notification,
)
from .sequence_service import allocate_token_number, format_token_number

logger = logging.getLogger(__name__)


def queue_key_for(clinic, doctor_id: str) -> str:
    return "COMMON" if clinic.settings and clinic.settings.token_mode == "clinic" else doctor_id


def ensure_queue_access(token: DailyToken) -> None:
    user = current_user()
    if "tokens.manage_all" in getattr(g, "permissions", set()):
        return
    doctor = user.doctor_profile
    if doctor is None or token.doctor_id != doctor.id:
        raise ForbiddenError("Doctors may only manage their own queue.")


def resolve_doctor_id(requested: str | None) -> str:
    user = current_user()
    if "tokens.manage_all" in getattr(g, "permissions", set()):
        if not requested:
            raise ValidationError("Select a doctor for this queue action.")
        return requested
    doctor = user.doctor_profile
    if doctor is None:
        raise ForbiddenError("This action is limited to assigned clinical staff.")
    if requested and requested != doctor.id:
        raise ForbiddenError("Doctors may only manage their own queue.")
    return doctor.id


def _validate_patient_and_doctor(clinic, patient: Patient, doctor: Doctor) -> None:
    if patient.clinic_id != clinic.id:
        raise NotFoundError("Patient not found in this clinic.")
    if patient.merged_into_id:
        raise ValidationError("This patient record was merged into another record. Use the merged patient.")
    if not patient.is_active:
        raise ValidationError("This patient record is inactive.")
    if doctor.clinic_id != clinic.id or not doctor.is_active:
        raise ValidationError("The selected doctor is not available in this clinic.")


def _post_commit_notifications(token: DailyToken) -> None:
    """Best-effort confirmation messages. Never fail a generated token for this."""
    try:
        clinic = token.doctor.clinic
        settings = clinic.settings
        doctor = token.doctor
        patient = token.patient
        if doctor.user_id:
            notify_staff(
                clinic_id=clinic.id,
                user_id=doctor.user_id,
                notification_type="token_created",
                subject="New patient in your queue",
                body=f"Token {token.display_number} is waiting for you.",
                dedupe_key=f"token-doctor:{token.id}",
                related_type="token",
                related_id=token.id,
            )
        channels = []
        if settings.reminder_email_enabled:
            channels.append(NotificationChannel.EMAIL)
        if settings.reminder_sms_enabled:
            channels.append(NotificationChannel.SMS)
        if settings.reminder_whatsapp_enabled:
            channels.append(NotificationChannel.WHATSAPP)
        body = (
            f"Your token for {doctor.full_name} at {clinic.name} is {token.display_number}. "
            "Please wait in the waiting area. Do not reply to this message."
        )
        for channel in channels:
            notification = queue_patient_notification(
                clinic_id=clinic.id,
                patient=patient,
                notification_type="token_confirmation",
                channel=channel,
                subject="Your clinic token",
                body=body,
                dedupe_key=f"token-{channel}:{token.id}",
                related_type="token",
                related_id=token.id,
            )
            if notification:
                deliver_notification(notification)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Token confirmation notification failed for token %s", token.id)


def generate_token(
    *,
    patient: Patient,
    doctor: Doctor,
    visit_type: str = VisitType.WALK_IN,
    actor=None,
    appointment: Appointment | None = None,
    follow_up_plan: FollowUpPlan | None = None,
    priority: int | None = None,
    notes: str | None = None,
    token_date=None,
) -> DailyToken:
    clinic = current_clinic()
    actor = actor or current_user()
    today = clinic_today(clinic)
    token_date = token_date or today
    if token_date > today:
        raise ValidationError("Tokens can only be generated for today.")
    if visit_type not in VisitType.ALL:
        raise ValidationError("Invalid visit type.")
    if visit_type == VisitType.EMERGENCY and not (notes and len(notes.strip()) >= 5):
        raise ValidationError("Emergency tokens require an authorisation reason.")
    if appointment and appointment.token:
        raise ConflictError("This appointment already has a token.")
    if appointment:
        if appointment.clinic_id != clinic.id or appointment.patient_id != patient.id:
            raise ValidationError("Appointment does not belong to this patient.")
        if appointment.doctor_id != doctor.id:
            raise ValidationError("Appointment belongs to a different doctor.")
        if appointment.appointment_date != token_date:
            raise ValidationError("This appointment is not scheduled for today.")
        if appointment.status not in AppointmentStatus.ACTIVE:
            raise ConflictError("This appointment is no longer active.")
    if follow_up_plan:
        if follow_up_plan.patient_id != patient.id or follow_up_plan.clinic_id != clinic.id:
            raise ValidationError("Follow-up does not belong to this patient.")
        if follow_up_plan.status in (FollowUpStatus.COMPLETED, FollowUpStatus.CANCELLED):
            raise ConflictError("This follow-up is already closed.")
        if follow_up_plan.doctor_id != doctor.id:
            raise ValidationError("This follow-up belongs to a different doctor.")

    if priority is None:
        priority = {VisitType.PRIORITY: 5, VisitType.EMERGENCY: 10}.get(visit_type, 0)

    last_error = None
    for attempt in range(6):
        try:
            _validate_patient_and_doctor(clinic, patient, doctor)
            queue_key = queue_key_for(clinic, doctor.id)
            number = allocate_token_number(clinic.id, token_date, queue_key)
            display_number = format_token_number(
                clinic.settings.token_prefix if clinic.settings else "", number
            )
            token = DailyToken(
                clinic_id=clinic.id,
                doctor_id=doctor.id,
                patient_id=patient.id,
                appointment_id=appointment.id if appointment else None,
                follow_up_plan_id=follow_up_plan.id if follow_up_plan else None,
                token_date=token_date,
                queue_key=queue_key,
                token_number=number,
                display_number=display_number,
                visit_type=visit_type,
                status=TokenStatus.WAITING,
                priority=priority,
                notes=notes,
                created_by=actor.id,
            )
            db.session.add(token)
            db.session.flush()
            if appointment:
                appointment.status = AppointmentStatus.CHECKED_IN
            if follow_up_plan:
                follow_up_plan.status = FollowUpStatus.ARRIVED
                follow_up_plan.arrived_at = datetime.now(timezone.utc)
            audit(
                "token.created",
                "token",
                token.id,
                {
                    "doctor_id": doctor.id,
                    "visit_type": visit_type,
                    "token_number": number,
                    "appointment_id": appointment.id if appointment else None,
                    "follow_up_plan_id": follow_up_plan.id if follow_up_plan else None,
                },
                clinic_id=clinic.id,
                user_id=actor.id,
            )
            db.session.commit()
            _post_commit_notifications(token)
            return token
        except (IntegrityError, OperationalError) as exc:
            last_error = exc
            db.session.rollback()
            continue
        except Exception:
            db.session.rollback()
            raise
    raise ConflictError(
        "The token could not be generated because another registration is in progress. Please try again.",
        details={"retryable": True},
    )


def queue_snapshot(clinic, token_date=None, doctor_id: str | None = None) -> dict:
    token_date = token_date or clinic_today(clinic)
    query = DailyToken.query.filter_by(clinic_id=clinic.id, token_date=token_date)
    if doctor_id:
        query = query.filter_by(doctor_id=doctor_id)
    tokens = query.order_by(DailyToken.priority.desc(), DailyToken.token_number.asc()).all()

    current = [
        t for t in tokens if t.status in (TokenStatus.CALLED, TokenStatus.RECALLED, TokenStatus.IN_CONSULTATION)
    ]
    current.sort(key=lambda t: t.called_at or t.created_at, reverse=True)
    waiting = [t for t in tokens if t.status == TokenStatus.WAITING]
    next_token = waiting[0] if waiting else None
    counts = {status: 0 for status in TokenStatus.ALL}
    for token in tokens:
        counts[token.status] = counts.get(token.status, 0) + 1
    waits = [
        minutes_between(t.created_at, t.called_at)
        for t in tokens
        if t.called_at and t.created_at
    ]
    avg_wait = round(mean(waits), 1) if waits else 0
    return {
        "token_date": token_date,
        "doctor_id": doctor_id,
        "tokens": tokens,
        "current": current[0] if current else None,
        "current_all": current,
        "next": next_token,
        "waiting": waiting,
        "counts": counts,
        "total": len(tokens),
        "average_wait_minutes": avg_wait,
    }


def call_next(clinic, doctor_id: str, actor=None, force: bool = False) -> DailyToken:
    doctor_id = resolve_doctor_id(doctor_id)
    actor = actor or current_user()
    today = clinic_today(clinic)
    current = (
        DailyToken.query.filter(
            DailyToken.clinic_id == clinic.id,
            DailyToken.token_date == today,
            DailyToken.doctor_id == doctor_id,
            DailyToken.status.in_([TokenStatus.CALLED, TokenStatus.RECALLED]),
        )
        .order_by(DailyToken.called_at.desc())
        .first()
    )
    in_consult = DailyToken.query.filter_by(
        clinic_id=clinic.id,
        token_date=today,
        doctor_id=doctor_id,
        status=TokenStatus.IN_CONSULTATION,
    ).first()
    if in_consult:
        raise ConflictError("A consultation is already in progress for this doctor.")
    if current and not force:
        raise ConflictError(
            f"Token {current.display_number} is already called. Recall, skip or complete it first.",
            details={"token_id": current.id, "display_number": current.display_number},
        )
    if current and force:
        current.status = TokenStatus.SKIPPED
        current.skip_reason = "Skipped when the next token was called"
    token = (
        DailyToken.query.filter_by(
            clinic_id=clinic.id,
            token_date=today,
            doctor_id=doctor_id,
            status=TokenStatus.WAITING,
        )
        .order_by(DailyToken.priority.desc(), DailyToken.token_number.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if token is None:
        raise NotFoundError("No patients are waiting in this queue.")
    token.status = TokenStatus.CALLED
    token.called_at = datetime.now(timezone.utc)
    audit(
        "token.called",
        "token",
        token.id,
        {"display_number": token.display_number, "doctor_id": doctor_id},
        clinic_id=clinic.id,
        user_id=actor.id,
    )
    db.session.commit()
    return token


def recall_token(token: DailyToken, actor=None) -> DailyToken:
    ensure_queue_access(token)
    actor = actor or current_user()
    if token.status not in (TokenStatus.CALLED, TokenStatus.RECALLED, TokenStatus.SKIPPED):
        raise ConflictError("Only called or skipped tokens can be recalled.")
    token.status = TokenStatus.RECALLED
    token.called_at = datetime.now(timezone.utc)
    token.recall_count = (token.recall_count or 0) + 1
    audit(
        "token.recalled",
        "token",
        token.id,
        {"display_number": token.display_number, "recall_count": token.recall_count},
        clinic_id=token.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return token


def skip_token(token: DailyToken, reason: str | None = None, actor=None) -> DailyToken:
    ensure_queue_access(token)
    actor = actor or current_user()
    if token.status not in (TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.RECALLED):
        raise ConflictError("This token can no longer be skipped.")
    token.status = TokenStatus.SKIPPED
    token.skip_reason = (reason or "")[:255] or "Skipped by staff"
    audit(
        "token.skipped",
        "token",
        token.id,
        {"display_number": token.display_number},
        clinic_id=token.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return token


def cancel_token(token: DailyToken, reason: str | None = None, actor=None) -> DailyToken:
    ensure_queue_access(token)
    actor = actor or current_user()
    if token.status in (TokenStatus.COMPLETED, TokenStatus.CANCELLED, TokenStatus.IN_CONSULTATION):
        raise ConflictError("This token can no longer be cancelled.")
    token.status = TokenStatus.CANCELLED
    token.skip_reason = (reason or "Cancelled by staff")[:255]
    if token.appointment and token.appointment.status in AppointmentStatus.ACTIVE:
        token.appointment.status = AppointmentStatus.CANCELLED
        token.appointment.cancellation_reason = "Linked token cancelled"
        token.appointment.cancelled_at = datetime.now(timezone.utc)
        token.appointment.cancelled_by = actor.id
    audit(
        "token.cancelled",
        "token",
        token.id,
        {"display_number": token.display_number, "reason": token.skip_reason},
        clinic_id=token.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return token


def mark_no_show(token: DailyToken, actor=None) -> DailyToken:
    ensure_queue_access(token)
    actor = actor or current_user()
    if token.status not in (TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.RECALLED):
        raise ConflictError("This token cannot be marked as a no-show.")
    token.status = TokenStatus.NO_SHOW
    token.skip_reason = "Patient unavailable"
    if token.appointment and token.appointment.status in AppointmentStatus.ACTIVE:
        token.appointment.status = AppointmentStatus.NO_SHOW
    audit(
        "token.no_show",
        "token",
        token.id,
        {"display_number": token.display_number},
        clinic_id=token.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return token


def start_token(token: DailyToken, actor=None) -> DailyToken:
    ensure_queue_access(token)
    actor = actor or current_user()
    if token.status not in (TokenStatus.CALLED, TokenStatus.RECALLED):
        raise ConflictError("Call the patient before starting the consultation.")
    token.status = TokenStatus.IN_CONSULTATION
    token.started_at = datetime.now(timezone.utc)
    audit(
        "token.consultation_started",
        "token",
        token.id,
        {"display_number": token.display_number},
        clinic_id=token.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return token


def complete_token(token: DailyToken, actor=None) -> DailyToken:
    actor = actor or current_user()
    token.status = TokenStatus.COMPLETED
    token.completed_at = datetime.now(timezone.utc)
    if token.appointment and token.appointment.status in AppointmentStatus.ACTIVE:
        token.appointment.status = AppointmentStatus.COMPLETED
    if token.follow_up_plan and token.follow_up_plan.status not in (
        FollowUpStatus.COMPLETED,
        FollowUpStatus.CANCELLED,
    ):
        token.follow_up_plan.status = FollowUpStatus.COMPLETED
        token.follow_up_plan.completed_at = datetime.now(timezone.utc)
    audit(
        "token.completed",
        "token",
        token.id,
        {"display_number": token.display_number},
        clinic_id=token.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return token


def transfer_token(token: DailyToken, target_doctor: Doctor, reason: str, actor=None) -> DailyToken:
    ensure_queue_access(token)
    clinic = current_clinic()
    actor = actor or current_user()
    if target_doctor.clinic_id != clinic.id or not target_doctor.is_active:
        raise ValidationError("Select an active doctor in this clinic.")
    if target_doctor.id == token.doctor_id:
        raise ValidationError("The token already belongs to this doctor.")
    if token.status not in (TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.RECALLED):
        raise ConflictError("This token can no longer be transferred.")
    if not reason or len(reason.strip()) < 5:
        raise ValidationError("A transfer reason is required.")
    token_date = token.token_date
    queue_key = queue_key_for(clinic, target_doctor.id)
    last_error = None
    for attempt in range(6):
        try:
            number = allocate_token_number(clinic.id, token_date, queue_key)
            new_token = DailyToken(
                clinic_id=clinic.id,
                doctor_id=target_doctor.id,
                patient_id=token.patient_id,
                appointment_id=None,
                follow_up_plan_id=token.follow_up_plan_id,
                token_date=token_date,
                queue_key=queue_key,
                token_number=number,
                display_number=format_token_number(
                    clinic.settings.token_prefix if clinic.settings else "", number
                ),
                visit_type=token.visit_type,
                status=TokenStatus.WAITING,
                priority=token.priority,
                notes=token.notes,
                transferred_from_id=token.id,
                created_by=actor.id,
            )
            db.session.add(new_token)
            db.session.flush()
            if token.follow_up_plan:
                token.follow_up_plan.doctor_id = target_doctor.id
                token.follow_up_plan_id = None
            if token.appointment and token.appointment.status in AppointmentStatus.ACTIVE:
                token.appointment.status = AppointmentStatus.CANCELLED
                token.appointment.cancellation_reason = f"Token transferred: {reason[:200]}"
                token.appointment.cancelled_at = datetime.now(timezone.utc)
                token.appointment.cancelled_by = actor.id
            token.status = TokenStatus.CANCELLED
            token.skip_reason = f"Transferred to {target_doctor.full_name}: {reason[:200]}"
            audit(
                "token.transferred",
                "token",
                new_token.id,
                {
                    "from_token_id": token.id,
                    "from_doctor_id": token.doctor_id,
                    "to_doctor_id": target_doctor.id,
                    "reason": reason[:200],
                },
                clinic_id=clinic.id,
                user_id=actor.id,
            )
            db.session.commit()
            if target_doctor.user_id:
                try:
                    notify_staff(
                        clinic_id=clinic.id,
                        user_id=target_doctor.user_id,
                        notification_type="token_transferred",
                        subject="Token transferred to you",
                        body=f"Token {new_token.display_number} was transferred to your queue.",
                        dedupe_key=f"token-transfer:{new_token.id}",
                        related_type="token",
                        related_id=new_token.id,
                    )
                    db.session.commit()
                except Exception:
                    db.session.rollback()
            return new_token
        except (IntegrityError, OperationalError) as exc:
            last_error = exc
            db.session.rollback()
            continue
        except Exception:
            db.session.rollback()
            raise
    raise ConflictError("The transfer could not be completed. Please try again.")


def doctor_queue_today(clinic, doctor_id: str) -> dict:
    return queue_snapshot(clinic, clinic_today(clinic), doctor_id)
