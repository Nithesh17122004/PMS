from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, g, request
from sqlalchemy import func

from ..auth.security import audit
from ..extensions import db
from ..models import (
    Appointment,
    DailyToken,
    Doctor,
    FollowUpPlan,
    Patient,
    TokenStatus,
    VisitType,
)
from ..permissions.rbac import permission_required
from ..permissions.tenant import current_clinic, get_scoped_or_404
from ..services.consultation_service import start_consultation_for_token
from ..services.pdf_service import token_receipt_pdf
from ..services.token_service import (
    call_next,
    cancel_token,
    complete_token,
    generate_token,
    mark_no_show,
    queue_snapshot,
    recall_token,
    skip_token,
    transfer_token,
)
from ..utils.datetime_utils import clinic_today, parse_date
from ..utils.errors import ConflictError, ForbiddenError, ValidationError
from ..utils.responses import ok, pagination_meta, parse_pagination
from ..utils.serializers import (
    consultation_dict,
    doctor_summary,
    patient_summary,
    token_dict,
)
from .helpers import json_body, pdf_response, scoped_or_404

tokens_bp = Blueprint("tokens", __name__)


def _scope_doctor(query, model=DailyToken):
    if g.user.doctor_profile and "tokens.manage_all" not in g.permissions:
        query = query.filter(model.doctor_id == g.user.doctor_profile.id)
    return query


@tokens_bp.get("/api/tokens")
@permission_required("tokens.view")
def list_tokens():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args, default_per_page=50)
    day = parse_date(request.args.get("date"), "Date", required=False) or clinic_today(clinic)
    query = DailyToken.query.filter(DailyToken.clinic_id == clinic.id, DailyToken.token_date == day)
    query = _scope_doctor(query)
    doctor_id = request.args.get("doctor_id")
    if doctor_id:
        query = query.filter(DailyToken.doctor_id == doctor_id)
    status = request.args.get("status")
    if status:
        query = query.filter(DailyToken.status == status)
    visit_type = request.args.get("visit_type")
    if visit_type:
        query = query.filter(DailyToken.visit_type == visit_type)
    query = query.order_by(DailyToken.priority.desc(), DailyToken.token_number.asc())
    total = query.count()
    tokens = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok([token_dict(t) for t in tokens], pagination_meta(total, page, per_page))


@tokens_bp.get("/api/tokens/queue")
@permission_required("tokens.view")
def queue_board():
    clinic = current_clinic()
    day = parse_date(request.args.get("date"), "Date", required=False) or clinic_today(clinic)
    doctor_id = request.args.get("doctor_id")
    if g.user.doctor_profile and "tokens.manage_all" not in g.permissions:
        doctor_id = g.user.doctor_profile.id
    if doctor_id:
        doctor = get_scoped_or_404(Doctor, doctor_id)
        snapshot = queue_snapshot(clinic, day, doctor.id)
        return ok(
            {
                "date": day.isoformat(),
                "mode": clinic.settings.token_mode if clinic.settings else "doctor",
                "doctor": doctor_summary(doctor),
                "counts": snapshot["counts"],
                "total": snapshot["total"],
                "average_wait_minutes": snapshot["average_wait_minutes"],
                "current": token_dict(snapshot["current"]) if snapshot["current"] else None,
                "next": token_dict(snapshot["next"]) if snapshot["next"] else None,
                "waiting": [token_dict(t) for t in snapshot["waiting"]],
                "tokens": [token_dict(t) for t in snapshot["tokens"]],
            }
        )
    all_snapshot = queue_snapshot(clinic, day)
    doctors = Doctor.query.filter_by(clinic_id=clinic.id, is_active=True).order_by(Doctor.full_name).all()
    queues = []
    for doctor in doctors:
        snapshot = queue_snapshot(clinic, day, doctor.id)
        has_tokens = snapshot["total"] > 0
        has_schedule = any(s.is_active and s.weekday == day.weekday() for s in doctor.schedules)
        if not (has_tokens or has_schedule or doctor.is_available):
            continue
        queues.append(
            {
                "doctor": doctor_summary(doctor),
                "counts": snapshot["counts"],
                "total": snapshot["total"],
                "average_wait_minutes": snapshot["average_wait_minutes"],
                "current": token_dict(snapshot["current"]) if snapshot["current"] else None,
                "next": token_dict(snapshot["next"]) if snapshot["next"] else None,
                "waiting": [token_dict(t) for t in snapshot["waiting"][:10]],
            }
        )
    return ok(
        {
            "date": day.isoformat(),
            "mode": clinic.settings.token_mode if clinic.settings else "doctor",
            "overall": {
                "counts": all_snapshot["counts"],
                "total": all_snapshot["total"],
                "average_wait_minutes": all_snapshot["average_wait_minutes"],
            },
            "queues": queues,
        }
    )


@tokens_bp.post("/api/tokens")
@permission_required("tokens.create")
def create_token():
    clinic = current_clinic()
    payload = json_body()
    patient = get_scoped_or_404(Patient, payload.get("patient_id") or "")
    doctor = get_scoped_or_404(Doctor, payload.get("doctor_id") or "")
    if (
        g.user.doctor_profile
        and g.user.doctor_profile.id != doctor.id
        and "tokens.manage_all" not in g.permissions
    ):
        raise ForbiddenError("Doctors can only generate tokens for their own queue.")
    visit_type = payload.get("visit_type") or VisitType.WALK_IN
    if visit_type == VisitType.EMERGENCY and g.user.role and g.user.role.slug not in (
        "clinic_admin",
        "doctor",
        "nurse",
    ):
        raise ForbiddenError("Emergency tokens require clinical authorisation.")
    appointment = None
    if payload.get("appointment_id"):
        appointment = get_scoped_or_404(Appointment, payload.get("appointment_id"))
    follow_up_plan = None
    if payload.get("follow_up_plan_id"):
        follow_up_plan = get_scoped_or_404(FollowUpPlan, payload.get("follow_up_plan_id"))
    token = generate_token(
        patient=patient,
        doctor=doctor,
        visit_type=visit_type,
        actor=g.user,
        appointment=appointment,
        follow_up_plan=follow_up_plan,
        priority=payload.get("priority"),
        notes=payload.get("notes"),
    )
    return ok({"token": token_dict(token)}, status=201)


@tokens_bp.get("/api/tokens/<token_id>")
@permission_required("tokens.view")
def get_token(token_id):
    token = get_scoped_or_404(DailyToken, token_id)
    if (
        g.user.doctor_profile
        and g.user.doctor_profile.id != token.doctor_id
        and "tokens.manage_all" not in g.permissions
    ):
        raise ForbiddenError("You can only view your own queue.")
    return ok({"token": token_dict(token)})


@tokens_bp.get("/api/tokens/<token_id>/receipt.pdf")
@permission_required("tokens.view")
def token_receipt(token_id):
    token = get_scoped_or_404(DailyToken, token_id)
    if (
        g.user.doctor_profile
        and g.user.doctor_profile.id != token.doctor_id
        and "tokens.manage_all" not in g.permissions
    ):
        raise ForbiddenError("You can only print your own queue tokens.")
    buffer = token_receipt_pdf(token)
    return pdf_response(buffer, f"token-{token.display_number}.pdf")


@tokens_bp.post("/api/tokens/<token_id>/call")
@permission_required("tokens.call")
def call_token(token_id):
    token = get_scoped_or_404(DailyToken, token_id)
    updated = call_next(
        current_clinic(), token.doctor_id, actor=g.user, force=bool(json_body().get("force"))
    )
    return ok({"token": token_dict(updated)})


@tokens_bp.post("/api/tokens/<token_id>/recall")
@permission_required("tokens.recall")
def recall(token_id):
    token = get_scoped_or_404(DailyToken, token_id)
    updated = recall_token(token, actor=g.user)
    return ok({"token": token_dict(updated)})


@tokens_bp.post("/api/tokens/<token_id>/skip")
@permission_required("tokens.skip")
def skip(token_id):
    token = get_scoped_or_404(DailyToken, token_id)
    payload = json_body()
    updated = skip_token(token, payload.get("reason"), actor=g.user)
    return ok({"token": token_dict(updated)})


@tokens_bp.post("/api/tokens/<token_id>/cancel")
@permission_required("tokens.cancel")
def cancel(token_id):
    token = get_scoped_or_404(DailyToken, token_id)
    payload = json_body()
    updated = cancel_token(token, payload.get("reason"), actor=g.user)
    return ok({"token": token_dict(updated)})


@tokens_bp.post("/api/tokens/<token_id>/no-show")
@permission_required("tokens.skip")
def no_show(token_id):
    token = get_scoped_or_404(DailyToken, token_id)
    updated = mark_no_show(token, actor=g.user)
    return ok({"token": token_dict(updated)})


@tokens_bp.post("/api/tokens/<token_id>/transfer")
@permission_required("tokens.transfer")
def transfer(token_id):
    token = get_scoped_or_404(DailyToken, token_id)
    payload = json_body()
    target = get_scoped_or_404(Doctor, payload.get("target_doctor_id") or "")
    new_token = transfer_token(token, target, payload.get("reason") or "", actor=g.user)
    return ok({"token": token_dict(new_token), "message": "Token transferred."})


@tokens_bp.post("/api/tokens/<token_id>/start")
@permission_required("consultations.create")
def start(token_id):
    token = get_scoped_or_404(DailyToken, token_id)
    consultation = start_consultation_for_token(token, g.user)
    return ok({"consultation": consultation_dict(consultation), "token": token_dict(token)})


@tokens_bp.post("/api/tokens/<token_id>/complete")
@permission_required("consultations.complete")
def complete(token_id):
    token = get_scoped_or_404(DailyToken, token_id)
    if token.consultation is None or token.consultation.status != "completed":
        raise ConflictError("Complete the consultation record before closing this token.")
    updated = complete_token(token, actor=g.user)
    return ok({"token": token_dict(updated)})
