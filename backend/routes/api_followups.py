from __future__ import annotations

from flask import Blueprint, g, request
from sqlalchemy import or_

from ..extensions import db
from ..models import (
    Doctor,
    FollowUpPlan,
    FollowUpReminder,
    FollowUpStatus,
    Patient,
)
from ..permissions.rbac import permission_required
from ..permissions.tenant import current_clinic, get_scoped_or_404
from ..services.followup_service import (
    arrive_followup,
    cancel_followup,
    complete_followup,
    confirm_followup,
    create_followup,
    followup_dashboard,
    reschedule_followup,
    send_manual_reminder,
)
from ..utils.datetime_utils import clinic_today, iso, parse_date
from ..utils.errors import ForbiddenError, ValidationError
from ..utils.responses import ok, pagination_meta, parse_pagination
from ..utils.serializers import followup_dict, token_dict
from .helpers import date_range_args, json_body, scoped_or_404

followups_bp = Blueprint("followups", __name__)


def _scope_doctor(query):
    if g.user.doctor_profile and "tokens.manage_all" not in g.permissions:
        query = query.filter(FollowUpPlan.doctor_id == g.user.doctor_profile.id)
    return query


def _reminder_dict(reminder: FollowUpReminder) -> dict:
    return {
        "id": reminder.id,
        "channel": reminder.channel,
        "reminder_type": reminder.reminder_type,
        "scheduled_date": iso(reminder.scheduled_date),
        "status": reminder.status,
        "sent_at": iso(reminder.sent_at),
        "provider": reminder.provider,
        "error": reminder.error,
        "created_at": iso(reminder.created_at),
    }


@followups_bp.get("/api/followups")
@permission_required("followups.view")
def list_followups():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args)
    query = FollowUpPlan.query.filter(FollowUpPlan.clinic_id == clinic.id)
    query = _scope_doctor(query)

    status = request.args.get("status")
    if status and status != "all":
        if status == "due":
            query = query.filter(
                FollowUpPlan.due_date <= clinic_today(clinic),
                FollowUpPlan.status.in_(
                    [FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED, FollowUpStatus.ARRIVED]
                ),
            )
        elif status == "overdue":
            query = query.filter(
                FollowUpPlan.due_date < clinic_today(clinic),
                FollowUpPlan.status.in_([FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED]),
            )
        else:
            query = query.filter(FollowUpPlan.status == status)
    day = parse_date(request.args.get("date"), "Date", required=False)
    if day:
        query = query.filter(FollowUpPlan.due_date == day)
    start = parse_date(request.args.get("start"), "Start date", required=False)
    end = parse_date(request.args.get("end"), "End date", required=False)
    if start:
        query = query.filter(FollowUpPlan.due_date >= start)
    if end:
        query = query.filter(FollowUpPlan.due_date <= end)
    doctor_id = request.args.get("doctor_id")
    if doctor_id:
        query = query.filter(FollowUpPlan.doctor_id == doctor_id)
    patient_id = request.args.get("patient_id")
    if patient_id:
        query = query.filter(FollowUpPlan.patient_id == patient_id)
    term = (request.args.get("q") or "").strip()
    if term:
        query = query.join(Patient, FollowUpPlan.patient_id == Patient.id).filter(
            or_(
                Patient.first_name.ilike(f"%{term}%"),
                Patient.last_name.ilike(f"%{term}%"),
                Patient.patient_code.ilike(f"%{term}%"),
            )
        )
    query = query.order_by(FollowUpPlan.due_date.asc(), FollowUpPlan.created_at.desc())
    total = query.count()
    plans = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok([followup_dict(p) for p in plans], pagination_meta(total, page, per_page))


@followups_bp.get("/api/followups/dashboard")
@permission_required("followups.view")
def dashboard():
    clinic = current_clinic()
    data = followup_dashboard(clinic)
    if g.user.doctor_profile and "tokens.manage_all" not in g.permissions:
        doctor_id = g.user.doctor_profile.id
        base = FollowUpPlan.query.filter_by(clinic_id=clinic.id, doctor_id=doctor_id)
        today = clinic_today(clinic)
        data["counts"] = {
            "today": base.filter(
                FollowUpPlan.due_date == today,
                FollowUpPlan.status.in_([FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED, FollowUpStatus.ARRIVED]),
            ).count(),
            "upcoming": base.filter(
                FollowUpPlan.due_date > today,
                FollowUpPlan.status.in_([FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED]),
            ).count(),
            "overdue": base.filter(
                FollowUpPlan.due_date < today,
                FollowUpPlan.status.in_([FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED]),
            ).count(),
            "completed": base.filter(FollowUpPlan.status == FollowUpStatus.COMPLETED).count(),
            "cancelled": base.filter(FollowUpPlan.status == FollowUpStatus.CANCELLED).count(),
            "missed": base.filter(FollowUpPlan.status == FollowUpStatus.MISSED).count(),
            "arrived": base.filter(FollowUpPlan.status == FollowUpStatus.ARRIVED).count(),
        }
        data["by_doctor"] = [
            row for row in data["by_doctor"] if row[0] == doctor_id
        ]
    data["by_doctor"] = [
        {
            "doctor_id": row[0],
            "doctor": db.session.get(Doctor, row[0]).full_name if db.session.get(Doctor, row[0]) else "Unknown",
            "count": row[1],
        }
        for row in data["by_doctor"]
    ]
    return ok(data)


@followups_bp.post("/api/followups")
@permission_required("followups.manage")
def create_manual_followup():
    clinic = current_clinic()
    payload = json_body()
    patient = get_scoped_or_404(Patient, payload.get("patient_id") or "")
    doctor = get_scoped_or_404(Doctor, payload.get("doctor_id") or "")
    if g.user.doctor_profile and g.user.doctor_profile.id != doctor.id:
        raise ForbiddenError("You can only schedule follow-ups for your own patients.")
    consultation = None
    if payload.get("consultation_id"):
        from ..models import Consultation

        consultation = get_scoped_or_404(Consultation, payload["consultation_id"])
        if consultation.patient_id != patient.id:
            raise ValidationError("The consultation does not belong to this patient.")
    plan = create_followup(
        clinic,
        g.user,
        patient,
        doctor,
        consultation,
        payload.get("due_date"),
        payload.get("instructions"),
        payload.get("priority") or "normal",
    )
    db.session.commit()
    return ok({"followup": followup_dict(plan)}, status=201)


@followups_bp.get("/api/followups/<plan_id>")
@permission_required("followups.view")
def get_followup(plan_id):
    plan = get_scoped_or_404(FollowUpPlan, plan_id)
    if g.user.doctor_profile and g.user.doctor_profile.id != plan.doctor_id and "tokens.manage_all" not in g.permissions:
        raise ForbiddenError("You can only view your own follow-ups.")
    data = followup_dict(plan)
    data["reminders"] = [
        _reminder_dict(r) for r in sorted(plan.reminders, key=lambda r: r.created_at, reverse=True)
    ]
    return ok({"followup": data})


@followups_bp.post("/api/followups/<plan_id>/confirm")
@permission_required("followups.manage")
def confirm(plan_id):
    plan = get_scoped_or_404(FollowUpPlan, plan_id)
    updated = confirm_followup(plan, g.user, json_body().get("notes"))
    return ok({"followup": followup_dict(updated)})


@followups_bp.post("/api/followups/<plan_id>/reschedule")
@permission_required("followups.manage")
def reschedule(plan_id):
    plan = get_scoped_or_404(FollowUpPlan, plan_id)
    payload = json_body()
    updated = reschedule_followup(plan, g.user, payload.get("due_date"), payload.get("reason"))
    return ok({"followup": followup_dict(updated)})


@followups_bp.post("/api/followups/<plan_id>/cancel")
@permission_required("followups.manage")
def cancel(plan_id):
    plan = get_scoped_or_404(FollowUpPlan, plan_id)
    updated = cancel_followup(plan, g.user, json_body().get("reason") or "")
    return ok({"followup": followup_dict(updated)})


@followups_bp.post("/api/followups/<plan_id>/arrive")
@permission_required("tokens.create")
def arrive(plan_id):
    plan = get_scoped_or_404(FollowUpPlan, plan_id)
    token = arrive_followup(plan, g.user, json_body().get("notes"))
    return ok({"token": token_dict(token), "followup": followup_dict(plan)}, status=201)


@followups_bp.post("/api/followups/<plan_id>/complete")
@permission_required("followups.complete")
def complete(plan_id):
    plan = get_scoped_or_404(FollowUpPlan, plan_id)
    updated = complete_followup(plan, g.user)
    return ok({"followup": followup_dict(updated)})


@followups_bp.post("/api/followups/<plan_id>/remind")
@permission_required("followups.manage")
def remind(plan_id):
    plan = get_scoped_or_404(FollowUpPlan, plan_id)
    payload = json_body()
    reminder = send_manual_reminder(
        plan, g.user, payload.get("channel") or "sms", payload.get("message")
    )
    return ok({"reminder": _reminder_dict(reminder), "followup": followup_dict(plan)})


@followups_bp.get("/api/followups/<plan_id>/reminders")
@permission_required("followups.view")
def reminders(plan_id):
    plan = get_scoped_or_404(FollowUpPlan, plan_id)
    items = sorted(plan.reminders, key=lambda r: r.created_at, reverse=True)
    return ok([_reminder_dict(r) for r in items])
