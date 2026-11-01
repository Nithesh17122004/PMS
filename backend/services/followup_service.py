from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func

from ..auth.security import audit
from ..extensions import db
from ..models import (
    FollowUpPlan,
    FollowUpReminder,
    FollowUpStatus,
    NotificationChannel,
    ReminderStatus,
    TokenStatus,
)
from ..utils.datetime_utils import clinic_today, parse_date
from ..utils.errors import ConflictError, ValidationError
from .notification_service import deliver_notification, queue_patient_notification


def create_followup(
    clinic,
    actor,
    patient,
    doctor,
    consultation,
    due_date,
    instructions: str | None,
    priority: str = "normal",
) -> FollowUpPlan:
    due = parse_date(due_date, "Follow-up date")
    if due < clinic_today(clinic):
        raise ValidationError("A follow-up cannot be scheduled in the past.")
    plan = FollowUpPlan(
        clinic_id=clinic.id,
        patient_id=patient.id,
        doctor_id=doctor.id,
        consultation_id=consultation.id if consultation else None,
        due_date=due,
        original_due_date=due,
        instructions=(instructions or None),
        status=FollowUpStatus.UPCOMING,
        priority=priority if priority in ("normal", "high", "urgent") else "normal",
        created_by=actor.id,
    )
    db.session.add(plan)
    db.session.flush()
    audit(
        "followup.created",
        "followup",
        plan.id,
        {"doctor_id": doctor.id, "due_date": due.isoformat(), "consultation_id": consultation.id if consultation else None},
        clinic_id=clinic.id,
        user_id=actor.id,
    )
    return plan


def confirm_followup(plan: FollowUpPlan, actor, notes: str | None = None) -> FollowUpPlan:
    if plan.status not in (FollowUpStatus.UPCOMING, FollowUpStatus.MISSED):
        raise ConflictError("Only upcoming or missed follow-ups can be confirmed.")
    plan.status = FollowUpStatus.CONFIRMED
    plan.confirmed_at = datetime.now(timezone.utc)
    if notes:
        plan.contact_notes = notes[:2000]
    audit("followup.confirmed", "followup", plan.id, clinic_id=plan.clinic_id, user_id=actor.id)
    db.session.commit()
    return plan


def reschedule_followup(plan: FollowUpPlan, actor, new_date, reason: str | None = None) -> FollowUpPlan:
    if plan.status in (FollowUpStatus.COMPLETED, FollowUpStatus.CANCELLED):
        raise ConflictError("This follow-up is already closed.")
    if plan.appointment_id:
        raise ConflictError("Reschedule the linked appointment instead, then update the follow-up.")
    due = parse_date(new_date, "New follow-up date")
    if due < clinic_today(plan.doctor.clinic):
        raise ValidationError("The new follow-up date cannot be in the past.")
    plan.due_date = due
    plan.status = FollowUpStatus.UPCOMING
    plan.rescheduled_count = (plan.rescheduled_count or 0) + 1
    if reason:
        plan.contact_notes = reason[:2000]
    audit(
        "followup.rescheduled",
        "followup",
        plan.id,
        {"new_date": due.isoformat(), "reason": (reason or "")[:150]},
        clinic_id=plan.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return plan


def cancel_followup(plan: FollowUpPlan, actor, reason: str) -> FollowUpPlan:
    if plan.status == FollowUpStatus.COMPLETED:
        raise ConflictError("A completed follow-up cannot be cancelled.")
    if not reason or len(reason.strip()) < 3:
        raise ValidationError("A cancellation reason is required.")
    plan.status = FollowUpStatus.CANCELLED
    plan.cancelled_at = datetime.now(timezone.utc)
    plan.cancellation_reason = reason[:255]
    audit(
        "followup.cancelled",
        "followup",
        plan.id,
        {"reason": reason[:150]},
        clinic_id=plan.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return plan


def arrive_followup(plan: FollowUpPlan, actor, notes: str | None = None):
    """Generate a token only when the patient actually arrives."""
    from .token_service import generate_token

    if plan.status in (FollowUpStatus.COMPLETED, FollowUpStatus.CANCELLED):
        raise ConflictError("This follow-up is already closed.")
    if plan.status == FollowUpStatus.ARRIVED:
        existing = next(
            (t for t in plan.tokens if t.status not in (TokenStatus.CANCELLED, TokenStatus.COMPLETED)),
            None,
        )
        if existing:
            raise ConflictError(f"A token ({existing.display_number}) already exists for this follow-up.")
    token = generate_token(
        patient=plan.patient,
        doctor=plan.doctor,
        visit_type="follow_up",
        actor=actor,
        follow_up_plan=plan,
        notes=notes,
    )
    audit(
        "followup.arrived",
        "followup",
        plan.id,
        {"token_id": token.id},
        clinic_id=plan.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return token


def complete_followup(plan: FollowUpPlan, actor) -> FollowUpPlan:
    if plan.status == FollowUpStatus.CANCELLED:
        raise ConflictError("A cancelled follow-up cannot be completed.")
    plan.status = FollowUpStatus.COMPLETED
    plan.completed_at = datetime.now(timezone.utc)
    audit("followup.completed", "followup", plan.id, clinic_id=plan.clinic_id, user_id=actor.id)
    db.session.commit()
    return plan


def send_manual_reminder(plan: FollowUpPlan, actor, channel: str, message: str | None = None):
    if plan.status in (FollowUpStatus.COMPLETED, FollowUpStatus.CANCELLED):
        raise ConflictError("This follow-up is closed.")
    if channel not in (NotificationChannel.EMAIL, NotificationChannel.SMS, NotificationChannel.WHATSAPP):
        raise ValidationError("Select email, SMS or WhatsApp.")
    patient = plan.patient
    if channel == NotificationChannel.EMAIL and (not patient.consent_email or not patient.email):
        raise ValidationError("This patient has not consented to email reminders or has no email address.")
    if channel in (NotificationChannel.SMS, NotificationChannel.WHATSAPP) and not patient.phone:
        raise ValidationError("This patient has no phone number on file.")
    if channel == NotificationChannel.SMS and not patient.consent_sms:
        raise ValidationError("This patient has not consented to SMS reminders.")
    if channel == NotificationChannel.WHATSAPP and not patient.consent_whatsapp:
        raise ValidationError("This patient has not consented to WhatsApp reminders.")
    today = clinic_today(plan.doctor.clinic)
    dedupe = f"followup-manual:{plan.id}:{channel}:{today.isoformat()}"
    existing = FollowUpReminder.query.filter_by(dedupe_key=dedupe).first()
    if existing:
        raise ConflictError("A reminder was already sent to this patient today on this channel.")
    body = message or (
        f"Reminder: your follow-up with {plan.doctor.full_name} at "
        f"{plan.doctor.clinic.name} is due on {plan.due_date.strftime('%d %b %Y')}. "
        "Please contact the clinic to confirm. Do not reply to this message."
    )
    reminder = FollowUpReminder(
        clinic_id=plan.clinic_id,
        follow_up_plan_id=plan.id,
        channel=channel,
        reminder_type="manual",
        scheduled_date=today,
        status=ReminderStatus.QUEUED,
        dedupe_key=dedupe,
    )
    db.session.add(reminder)
    db.session.flush()
    notification = queue_patient_notification(
        clinic_id=plan.clinic_id,
        patient=patient,
        notification_type="followup_reminder",
        channel=channel,
        subject="Follow-up reminder",
        body=body,
        dedupe_key=dedupe,
        related_type="followup",
        related_id=plan.id,
    )
    if notification is None:
        reminder.status = ReminderStatus.SKIPPED
        reminder.error = "Patient consent or contact details missing"
    else:
        deliver_notification(notification)
        reminder.status = (
            ReminderStatus.SENT if notification.status == "sent" else ReminderStatus.FAILED
        )
        reminder.sent_at = notification.sent_at
        reminder.provider = notification.provider
        reminder.provider_message_id = notification.provider_message_id
        reminder.error = notification.error
    plan.reminder_count = (plan.reminder_count or 0) + 1
    plan.last_reminder_at = datetime.now(timezone.utc)
    audit(
        "followup.reminder_sent",
        "followup",
        plan.id,
        {"channel": channel, "status": reminder.status},
        clinic_id=plan.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return reminder


def followup_dashboard(clinic) -> dict:
    today = clinic_today(clinic)
    base = FollowUpPlan.query.filter_by(clinic_id=clinic.id)
    counts = {
        "today": base.filter(FollowUpPlan.due_date == today, FollowUpPlan.status.in_([FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED, FollowUpStatus.ARRIVED])).count(),
        "upcoming": base.filter(FollowUpPlan.due_date > today, FollowUpPlan.status.in_([FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED])).count(),
        "overdue": base.filter(FollowUpPlan.due_date < today, FollowUpPlan.status.in_([FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED])).count(),
        "completed": base.filter(FollowUpPlan.status == FollowUpStatus.COMPLETED).count(),
        "cancelled": base.filter(FollowUpPlan.status == FollowUpStatus.CANCELLED).count(),
        "missed": base.filter(FollowUpPlan.status == FollowUpStatus.MISSED).count(),
        "arrived": base.filter(FollowUpPlan.status == FollowUpStatus.ARRIVED).count(),
    }
    by_doctor = (
        db.session.query(FollowUpPlan.doctor_id, func.count(FollowUpPlan.id))
        .filter(
            FollowUpPlan.clinic_id == clinic.id,
            FollowUpPlan.due_date <= today,
            FollowUpPlan.status.in_([FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED, FollowUpStatus.ARRIVED]),
        )
        .group_by(FollowUpPlan.doctor_id)
        .all()
    )
    return {"counts": counts, "by_doctor": by_doctor}
