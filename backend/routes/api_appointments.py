from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, g, request

from ..auth.security import audit
from ..extensions import db
from ..models import Appointment, AppointmentStatus, Doctor, NotificationChannel, Patient
from ..permissions.rbac import permission_required
from ..permissions.tenant import current_clinic, get_scoped_or_404
from ..services.appointment_service import (
    cancel_appointment,
    check_in_appointment,
    create_appointment,
    doctor_slots,
    reschedule_appointment,
)
from ..services.notification_service import deliver_notification, queue_patient_notification
from ..utils.datetime_utils import clinic_today, parse_date
from ..utils.errors import ForbiddenError, ValidationError
from ..utils.responses import ok, pagination_meta, parse_pagination
from ..utils.serializers import appointment_dict, token_dict
from .helpers import json_body, scoped_or_404

appointments_bp = Blueprint("appointments", __name__)


def _scope_doctor(query):
    if g.user.doctor_profile and "tokens.manage_all" not in g.permissions:
        query = query.filter(Appointment.doctor_id == g.user.doctor_profile.id)
    return query


@appointments_bp.get("/api/appointments")
@permission_required("appointments.view")
def list_appointments():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args)
    query = Appointment.query.filter(Appointment.clinic_id == clinic.id)
    query = _scope_doctor(query)
    day = parse_date(request.args.get("date"), "Date", required=False)
    if day:
        query = query.filter(Appointment.appointment_date == day)
    start = parse_date(request.args.get("start"), "Start date", required=False)
    end = parse_date(request.args.get("end"), "End date", required=False)
    if start:
        query = query.filter(Appointment.appointment_date >= start)
    if end:
        query = query.filter(Appointment.appointment_date <= end)
    doctor_id = request.args.get("doctor_id")
    if doctor_id:
        query = query.filter(Appointment.doctor_id == doctor_id)
    patient_id = request.args.get("patient_id")
    if patient_id:
        query = query.filter(Appointment.patient_id == patient_id)
    status = request.args.get("status")
    if status:
        query = query.filter(Appointment.status == status)
    visit_type = request.args.get("visit_type")
    if visit_type:
        query = query.filter(Appointment.visit_type == visit_type)
    query = query.order_by(Appointment.appointment_date.desc(), Appointment.start_time.desc())
    total = query.count()
    appointments = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok([appointment_dict(a) for a in appointments], pagination_meta(total, page, per_page))


@appointments_bp.get("/api/appointments/<appointment_id>")
@permission_required("appointments.view")
def get_appointment(appointment_id):
    appointment = get_scoped_or_404(Appointment, appointment_id)
    return ok({"appointment": appointment_dict(appointment)})


@appointments_bp.get("/api/appointments/slots")
@permission_required("appointments.view")
def appointment_slots():
    clinic = current_clinic()
    doctor = get_scoped_or_404(Doctor, request.args.get("doctor_id") or "")
    day = parse_date(request.args.get("date"), "Date")
    slots = doctor_slots(clinic, doctor, day)
    return ok(
        {
            "date": day.isoformat(),
            "doctor": {"id": doctor.id, "full_name": doctor.full_name},
            "slots": [
                {
                    "start_time": slot["start_time"].isoformat(),
                    "end_time": slot["end_time"].isoformat(),
                    "available": slot["available"],
                    "reason": slot.get("reason"),
                }
                for slot in slots
            ],
        }
    )


@appointments_bp.post("/api/appointments")
@permission_required("appointments.create")
def book_appointment():
    clinic = current_clinic()
    payload = json_body()
    can_override = "appointments.override" in g.permissions
    appointment = create_appointment(clinic, g.user, payload, can_override=can_override)
    _send_booking_confirmation(clinic, appointment)
    return ok({"appointment": appointment_dict(appointment)}, status=201)


def _send_booking_confirmation(clinic, appointment):
    try:
        settings = clinic.settings
        if not settings or not settings.appointment_reminders:
            return
        patient = appointment.patient
        channels = []
        if settings.reminder_email_enabled:
            channels.append(NotificationChannel.EMAIL)
        if settings.reminder_sms_enabled:
            channels.append(NotificationChannel.SMS)
        if settings.reminder_whatsapp_enabled:
            channels.append(NotificationChannel.WHATSAPP)
        if not channels:
            return
        body = (
            f"Your appointment with {appointment.doctor.full_name} at {clinic.name} is confirmed for "
            f"{appointment.appointment_date.strftime('%d %b %Y')} at "
            f"{appointment.start_time.strftime('%I:%M %p')}. "
            "Please arrive 10 minutes early. Do not reply to this message."
        )
        for channel in channels:
            notification = queue_patient_notification(
                clinic_id=clinic.id,
                patient=patient,
                notification_type="appointment_confirmation",
                channel=channel,
                subject="Appointment confirmed",
                body=body,
                dedupe_key=f"appt-confirm:{appointment.id}:{channel}",
                related_type="appointment",
                related_id=appointment.id,
            )
            if notification:
                deliver_notification(notification)
        db.session.commit()
    except Exception:
        db.session.rollback()


@appointments_bp.post("/api/appointments/<appointment_id>/reschedule")
@permission_required("appointments.edit")
def reschedule(appointment_id):
    appointment = get_scoped_or_404(Appointment, appointment_id)
    payload = json_body()
    can_override = "appointments.override" in g.permissions
    new_appointment = reschedule_appointment(
        current_clinic(), g.user, appointment, payload, can_override=can_override
    )
    return ok({"appointment": appointment_dict(new_appointment)})


@appointments_bp.post("/api/appointments/<appointment_id>/cancel")
@permission_required("appointments.cancel")
def cancel(appointment_id):
    appointment = get_scoped_or_404(Appointment, appointment_id)
    payload = json_body()
    reason = payload.get("reason") or payload.get("cancellation_reason") or ""
    updated = cancel_appointment(current_clinic(), g.user, appointment, reason)
    return ok({"appointment": appointment_dict(updated)})


@appointments_bp.post("/api/appointments/<appointment_id>/check-in")
@permission_required("tokens.create")
def check_in(appointment_id):
    appointment = get_scoped_or_404(Appointment, appointment_id)
    token = check_in_appointment(current_clinic(), g.user, appointment)
    return ok({"token": token_dict(token), "appointment": appointment_dict(appointment)})
