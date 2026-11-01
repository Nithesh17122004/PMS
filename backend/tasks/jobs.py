"""Background jobs for reminders, missed follow-ups and operational alerts.

Every job is idempotent: notification and reminder rows use unique dedupe keys,
so running the scheduler more than once cannot spam patients.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import or_

from ..extensions import db
from ..models import (
    Appointment,
    AppointmentStatus,
    Clinic,
    DailyToken,
    Doctor,
    FollowUpPlan,
    FollowUpReminder,
    FollowUpStatus,
    Medication,
    NotificationChannel,
    ReminderStatus,
    Role,
    TokenStatus,
    User,
)
from ..services.notification_service import (
    deliver_notification,
    notify_staff,
    queue_patient_notification,
    retry_pending_notifications,
)
from ..utils.datetime_utils import clinic_now, clinic_today
from ..utils.serializers import iso

logger = logging.getLogger(__name__)


def _enabled_channels(clinic) -> list[str]:
    settings = clinic.settings
    if settings is None:
        return []
    channels = []
    if settings.reminder_email_enabled:
        channels.append(NotificationChannel.EMAIL)
    if settings.reminder_sms_enabled:
        channels.append(NotificationChannel.SMS)
    if settings.reminder_whatsapp_enabled:
        channels.append(NotificationChannel.WHATSAPP)
    return channels


def mark_missed_followups() -> dict:
    total = 0
    for clinic in Clinic.query.filter_by(is_active=True).all():
        today = clinic_today(clinic)
        plans = FollowUpPlan.query.filter(
            FollowUpPlan.clinic_id == clinic.id,
            FollowUpPlan.due_date < today,
            FollowUpPlan.status.in_([FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED]),
        ).all()
        for plan in plans:
            plan.status = FollowUpStatus.MISSED
            total += 1
        db.session.commit()
    return {"missed_followups": total}


def send_followup_reminders() -> dict:
    queued = sent = skipped = 0
    for clinic in Clinic.query.filter_by(is_active=True).all():
        settings = clinic.settings
        if settings is None:
            continue
        channels = _enabled_channels(clinic)
        if not channels:
            continue
        today = clinic_today(clinic)
        due_dates = []
        if settings.reminder_day_before:
            due_dates.append(today + timedelta(days=1))
        if settings.reminder_on_day:
            due_dates.append(today)
        if not due_dates:
            continue
        plans = FollowUpPlan.query.filter(
            FollowUpPlan.clinic_id == clinic.id,
            FollowUpPlan.due_date.in_(due_dates),
            FollowUpPlan.status.in_([FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED]),
        ).all()
        for plan in plans:
            patient = plan.patient
            for channel in channels:
                reminder_type = "day_before" if plan.due_date == today + timedelta(days=1) else "on_day"
                dedupe = f"followup-auto:{plan.id}:{channel}:{plan.due_date.isoformat()}:{reminder_type}"
                if FollowUpReminder.query.filter_by(dedupe_key=dedupe).first():
                    continue
                reminder = FollowUpReminder(
                    clinic_id=clinic.id,
                    follow_up_plan_id=plan.id,
                    channel=channel,
                    reminder_type=reminder_type,
                    scheduled_date=plan.due_date,
                    status=ReminderStatus.QUEUED,
                    dedupe_key=dedupe,
                )
                db.session.add(reminder)
                db.session.flush()
                body = (
                    f"Reminder: your follow-up with {plan.doctor.full_name} at {clinic.name} "
                    f"is due on {plan.due_date.strftime('%d %b %Y')}. "
                    "Please contact the clinic to confirm. Do not reply to this message."
                )
                notification = queue_patient_notification(
                    clinic_id=clinic.id,
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
                    skipped += 1
                else:
                    deliver_notification(notification)
                    reminder.status = (
                        ReminderStatus.SENT
                        if notification.status == "sent"
                        else ReminderStatus.FAILED
                    )
                    reminder.sent_at = notification.sent_at
                    reminder.provider = notification.provider
                    reminder.error = notification.error
                    if notification.status == "sent":
                        sent += 1
                    else:
                        queued += 1
                plan.reminder_count = (plan.reminder_count or 0) + 1
                plan.last_reminder_at = datetime.now(timezone.utc)
        db.session.commit()
    return {"followup_reminders_sent": sent, "followup_reminders_failed": queued, "followup_reminders_skipped": skipped}


def send_appointment_reminders() -> dict:
    sent = 0
    skipped = 0
    for clinic in Clinic.query.filter_by(is_active=True).all():
        settings = clinic.settings
        if settings is None or not settings.appointment_reminders:
            continue
        channels = _enabled_channels(clinic)
        if not channels:
            continue
        today = clinic_today(clinic)
        days = [today]
        if settings.reminder_day_before:
            days.append(today + timedelta(days=1))
        appointments = Appointment.query.filter(
            Appointment.clinic_id == clinic.id,
            Appointment.appointment_date.in_(days),
            Appointment.status.in_([AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED]),
            Appointment.reminder_sent.is_(False),
        ).all()
        for appointment in appointments:
            delivered_any = False
            for channel in channels:
                kind = "on_day" if appointment.appointment_date == today else "day_before"
                dedupe = f"appt-reminder:{appointment.id}:{channel}:{kind}:{appointment.appointment_date.isoformat()}"
                body = (
                    f"Reminder: your appointment with {appointment.doctor.full_name} at {clinic.name} "
                    f"is on {appointment.appointment_date.strftime('%d %b %Y')} at "
                    f"{appointment.start_time.strftime('%I:%M %p')}. "
                    "Please arrive 10 minutes early. Do not reply to this message."
                )
                notification = queue_patient_notification(
                    clinic_id=clinic.id,
                    patient=appointment.patient,
                    notification_type="appointment_reminder",
                    channel=channel,
                    subject="Appointment reminder",
                    body=body,
                    dedupe_key=dedupe,
                    related_type="appointment",
                    related_id=appointment.id,
                )
                if notification is None:
                    skipped += 1
                    continue
                deliver_notification(notification)
                if notification.status == "sent":
                    delivered_any = True
                    sent += 1
            if delivered_any:
                appointment.reminder_sent = True
        db.session.commit()
    return {"appointment_reminders_sent": sent, "appointment_reminders_skipped": skipped}


def send_overdue_followup_alerts() -> dict:
    created = 0
    for clinic in Clinic.query.filter_by(is_active=True).all():
        settings = clinic.settings
        if settings is None or not settings.overdue_followup_alert:
            continue
        today = clinic_today(clinic)
        overdue = FollowUpPlan.query.filter(
            FollowUpPlan.clinic_id == clinic.id,
            FollowUpPlan.due_date < today,
            FollowUpPlan.status.in_([FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED, FollowUpStatus.MISSED]),
        ).count()
        if overdue == 0:
            continue
        admins = (
            User.query.join(Role, User.role_id == Role.id)
            .filter(
                User.clinic_id == clinic.id,
                User.is_active.is_(True),
                Role.slug.in_(["clinic_admin", "receptionist"]),
            )
            .all()
        )
        for user in admins:
            notification = notify_staff(
                clinic_id=clinic.id,
                user_id=user.id,
                notification_type="overdue_followups",
                subject="Overdue follow-ups need attention",
                body=f"{overdue} follow-up(s) are overdue. Review the follow-up worklist.",
                dedupe_key=f"overdue-followups:{clinic.id}:{user.id}:{today.isoformat()}",
                related_type="clinic",
                related_id=clinic.id,
            )
            if notification:
                created += 1
        db.session.commit()
    return {"overdue_alerts": created}


def send_low_stock_alerts() -> dict:
    created = 0
    for clinic in Clinic.query.filter_by(is_active=True).all():
        settings = clinic.settings
        if settings is None or not settings.low_stock_alerts:
            continue
        today = clinic_today(clinic)
        medications = Medication.query.filter_by(clinic_id=clinic.id, is_active=True).all()
        low = [m for m in medications if sum(b.quantity for b in m.batches) <= m.reorder_level]
        if not low:
            continue
        admins = (
            User.query.join(Role, User.role_id == Role.id)
            .filter(
                User.clinic_id == clinic.id,
                User.is_active.is_(True),
                Role.slug.in_(["clinic_admin", "pharmacist"]),
            )
            .all()
        )
        for user in admins:
            names = ", ".join(m.name for m in low[:4])
            notification = notify_staff(
                clinic_id=clinic.id,
                user_id=user.id,
                notification_type="low_stock",
                subject="Pharmacy stock needs replenishment",
                body=f"{len(low)} medicine(s) are at or below reorder level: {names}.",
                dedupe_key=f"low-stock:{clinic.id}:{user.id}:{today.isoformat()}",
                related_type="clinic",
                related_id=clinic.id,
            )
            if notification:
                created += 1
        db.session.commit()
    return {"low_stock_alerts": created}


def purge_stale_data() -> dict:
    from ..models import PasswordResetToken

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    deleted = PasswordResetToken.query.filter(
        PasswordResetToken.expires_at < cutoff
    ).delete(synchronize_session=False)
    db.session.commit()
    return {"expired_reset_tokens_deleted": deleted}


def run_all_jobs() -> dict:
    results: dict = {}
    jobs = [
        ("missed_followups", mark_missed_followups),
        ("followup_reminders", send_followup_reminders),
        ("appointment_reminders", send_appointment_reminders),
        ("overdue_alerts", send_overdue_followup_alerts),
        ("low_stock_alerts", send_low_stock_alerts),
        ("notification_retry", retry_pending_notifications),
        ("purge", purge_stale_data),
    ]
    for name, job in jobs:
        try:
            results[name] = job()
        except Exception:
            logger.exception("Background job failed: %s", name)
            db.session.rollback()
            results[name] = {"error": "job_failed"}
    logger.info("Background job cycle complete: %s", results)
    return results
