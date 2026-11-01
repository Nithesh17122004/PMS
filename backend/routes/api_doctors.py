from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from flask import Blueprint, g, request
from sqlalchemy import func

from ..auth.security import audit, hash_password, validate_password_strength
from ..extensions import db
from ..models import (
    Consultation,
    ConsultationStatus,
    DailyToken,
    Doctor,
    DoctorLeave,
    DoctorSchedule,
    Invoice,
    Patient,
    Payment,
    Role,
    TokenStatus,
    User,
)
from ..permissions.rbac import permission_required
from ..permissions.tenant import current_clinic, get_scoped_or_404
from ..services.appointment_service import doctor_slots
from ..services.clinic_service import generate_temporary_password
from ..services.dashboard_service import available_doctors
from ..services.sequence_service import format_document_number, next_document_number
from ..services.token_service import queue_snapshot
from ..utils.crypto import normalize_email
from ..utils.datetime_utils import as_utc, clinic_today, parse_date, parse_time, utc_bounds_for_local_range
from ..utils.errors import ConflictError, ValidationError
from ..utils.responses import ok, pagination_meta, parse_pagination
from ..utils.serializers import (
    doctor_detail,
    doctor_summary,
    leave_dict,
    schedule_dict,
    token_dict,
)
from .helpers import date_range_args, json_body, scoped_or_404

doctors_bp = Blueprint("doctors", __name__)


def _today_counts(doctor):
    today = clinic_today(doctor.clinic)
    rows = (
        db.session.query(DailyToken.status, func.count(DailyToken.id))
        .filter(
            DailyToken.clinic_id == doctor.clinic_id,
            DailyToken.doctor_id == doctor.id,
            DailyToken.token_date == today,
        )
        .group_by(DailyToken.status)
        .all()
    )
    counts = {status: 0 for status in TokenStatus.ALL}
    for status, count in rows:
        counts[status] = count
    return counts


@doctors_bp.get("/api/doctors")
@permission_required("doctors.view")
def list_doctors():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args, default_per_page=50)
    query = Doctor.query.filter(Doctor.clinic_id == clinic.id)
    status = request.args.get("status", "active")
    if status == "active":
        query = query.filter(Doctor.is_active.is_(True))
    elif status == "inactive":
        query = query.filter(Doctor.is_active.is_(False))
    specialization = request.args.get("specialization")
    if specialization:
        query = query.filter(Doctor.specialization.ilike(f"%{specialization}%"))
    query = query.order_by(Doctor.full_name.asc())
    total = query.count()
    doctors = query.offset((page - 1) * per_page).limit(per_page).all()
    data = []
    today = clinic_today(clinic)
    for doctor in doctors:
        item = doctor_summary(doctor)
        item["today_counts"] = _today_counts(doctor)
        item["on_leave_today"] = any(
            lv.status == "approved" and lv.start_date <= today <= lv.end_date for lv in doctor.leaves
        )
        item["has_schedule_today"] = any(
            s.is_active and s.weekday == today.weekday() for s in doctor.schedules
        )
        data.append(item)
    return ok(data, pagination_meta(total, page, per_page))


@doctors_bp.get("/api/doctors/available")
@permission_required("doctors.view")
def list_available_doctors():
    clinic = current_clinic()
    day = parse_date(request.args.get("date"), "Date", required=False) or clinic_today(clinic)
    return ok([doctor_summary(d) for d in available_doctors(clinic, day)])


@doctors_bp.get("/api/doctors/<doctor_id>")
@permission_required("doctors.view")
def get_doctor(doctor_id):
    doctor = get_scoped_or_404(Doctor, doctor_id)
    data = doctor_detail(doctor)
    data["today_counts"] = _today_counts(doctor)
    month_start = clinic_today(doctor.clinic).replace(day=1)
    start_utc, end_utc = utc_bounds_for_local_range(
        doctor.clinic, month_start, clinic_today(doctor.clinic)
    )
    completed = Consultation.query.filter(
        Consultation.clinic_id == doctor.clinic_id,
        Consultation.doctor_id == doctor.id,
        Consultation.status == ConsultationStatus.COMPLETED,
        Consultation.completed_at >= start_utc,
        Consultation.completed_at < end_utc,
    ).count()
    data["month_consultations"] = completed
    data["total_patients"] = (
        db.session.query(func.count(func.distinct(DailyToken.patient_id)))
        .filter(DailyToken.clinic_id == doctor.clinic_id, DailyToken.doctor_id == doctor.id)
        .scalar()
        or 0
    )
    return ok({"doctor": data})


@doctors_bp.post("/api/doctors")
@permission_required("doctors.manage")
def create_doctor():
    clinic = current_clinic()
    payload = json_body()
    full_name = (payload.get("full_name") or "").strip()
    specialization = (payload.get("specialization") or "").strip()
    if not full_name or not specialization:
        raise ValidationError("Doctor name and specialization are required.")
    email_value = payload.get("email")
    if email_value not in (None, "") and not isinstance(email_value, str):
        raise ValidationError("Doctor login email must be a valid email address.")
    email = normalize_email(email_value)
    if email and (len(email) > 190 or "@" not in email or any(ch.isspace() for ch in email)):
        raise ValidationError("Doctor login email must be a valid email address.")
    temp_password = None
    user = None
    if email:
        user = User.query.filter_by(email=email).first()
        if user and user.clinic_id != clinic.id:
            raise ConflictError("That email belongs to another clinic.")
        if user is None:
            role = Role.query.filter_by(clinic_id=clinic.id, slug="doctor").first()
            if role is None:
                raise ValidationError("Doctor role is not configured for this clinic.")
            password = payload.get("password")
            if password:
                validate_password_strength(password)
            else:
                password = generate_temporary_password()
                temp_password = password
            user = User(
                clinic_id=clinic.id,
                role_id=role.id,
                email=email,
                full_name=full_name[:140],
                phone=(payload.get("phone") or None),
                designation="Doctor",
                password_hash=hash_password(password),
                must_change_password=temp_password is not None,
                avatar_color="#0f9d8f",
            )
            db.session.add(user)
            db.session.flush()
        else:
            if user.role is None or user.role.slug != "doctor":
                raise ValidationError("That email belongs to a non-doctor account. Use a new email to create a doctor login.")
            if user.doctor_profile:
                raise ConflictError("This user already has a doctor profile.")
    number = next_document_number(clinic.id, "doctor")
    doctor = Doctor(
        clinic_id=clinic.id,
        user_id=user.id if user else None,
        doctor_code=format_document_number("DR-", number, width=4),
        full_name=full_name[:140],
        specialization=specialization[:120],
        qualifications=(payload.get("qualifications") or None),
        registration_number=(payload.get("registration_number") or None),
        experience_years=int(payload.get("experience_years") or 0),
        consultation_fee=payload.get("consultation_fee") or (clinic.settings.consultation_fee_default if clinic.settings else 500),
        follow_up_fee=payload.get("follow_up_fee") or (clinic.settings.follow_up_fee_default if clinic.settings else 0),
        bio=(payload.get("bio") or None),
        room_number=(payload.get("room_number") or None),
        avg_consult_minutes=int(payload.get("avg_consult_minutes") or 12),
        is_available=bool(payload.get("is_available", True)),
    )
    db.session.add(doctor)
    db.session.flush()
    audit(
        "doctor.created",
        "doctor",
        doctor.id,
        {"doctor_code": doctor.doctor_code, "user_id": doctor.user_id},
        clinic_id=clinic.id,
        user_id=g.user.id,
    )
    db.session.commit()
    result = doctor_detail(doctor)
    if temp_password:
        result["temporary_password"] = temp_password
    return ok({"doctor": result}, status=201)


@doctors_bp.put("/api/doctors/<doctor_id>")
@permission_required("doctors.manage")
def update_doctor(doctor_id):
    doctor = get_scoped_or_404(Doctor, doctor_id)
    payload = json_body()
    if "full_name" in payload:
        name = (payload.get("full_name") or "").strip()
        if not name:
            raise ValidationError("Doctor name is required.")
        doctor.full_name = name[:140]
    for field in ("specialization", "qualifications", "registration_number", "bio", "room_number"):
        if field in payload:
            setattr(doctor, field, (payload.get(field) or None))
    for field in ("consultation_fee", "follow_up_fee"):
        if field in payload:
            try:
                value = float(payload.get(field) or 0)
            except (TypeError, ValueError):
                raise ValidationError("Fees must be numbers.")
            if value < 0:
                raise ValidationError("Fees cannot be negative.")
            setattr(doctor, field, value)
    for field in ("experience_years", "avg_consult_minutes"):
        if field in payload:
            setattr(doctor, field, max(0, int(payload.get(field) or 0)))
    for field in ("is_available", "is_active"):
        if field in payload:
            setattr(doctor, field, bool(payload.get(field)))
    audit("doctor.updated", "doctor", doctor.id, clinic_id=doctor.clinic_id, user_id=g.user.id)
    db.session.commit()
    return ok({"doctor": doctor_detail(doctor)})


@doctors_bp.post("/api/doctors/<doctor_id>/schedules")
@permission_required("doctors.manage")
def add_schedule(doctor_id):
    doctor = get_scoped_or_404(Doctor, doctor_id)
    payload = json_body()
    schedule = _schedule_from_payload(doctor, payload)
    db.session.add(schedule)
    db.session.flush()
    _ensure_no_schedule_overlap(doctor, schedule, exclude_id=schedule.id)
    audit("doctor.schedule_added", "doctor", doctor.id, {"weekday": schedule.weekday}, clinic_id=doctor.clinic_id, user_id=g.user.id)
    db.session.commit()
    return ok({"schedule": schedule_dict(schedule)}, status=201)


@doctors_bp.put("/api/doctors/<doctor_id>/schedules/<schedule_id>")
@permission_required("doctors.manage")
def update_schedule(doctor_id, schedule_id):
    doctor = get_scoped_or_404(Doctor, doctor_id)
    schedule = DoctorSchedule.query.filter_by(id=schedule_id, doctor_id=doctor.id).first()
    if schedule is None:
        raise ConflictError("Schedule not found.")
    payload = json_body()
    updated = _schedule_from_payload(doctor, payload)
    schedule.weekday = updated.weekday
    schedule.start_time = updated.start_time
    schedule.end_time = updated.end_time
    schedule.break_start = updated.break_start
    schedule.break_end = updated.break_end
    schedule.slot_minutes = updated.slot_minutes
    schedule.max_tokens = updated.max_tokens
    schedule.is_active = updated.is_active
    _ensure_no_schedule_overlap(doctor, schedule, exclude_id=schedule.id)
    audit("doctor.schedule_updated", "doctor", doctor.id, {"schedule_id": schedule.id}, clinic_id=doctor.clinic_id, user_id=g.user.id)
    db.session.commit()
    return ok({"schedule": schedule_dict(schedule)})


@doctors_bp.delete("/api/doctors/<doctor_id>/schedules/<schedule_id>")
@permission_required("doctors.manage")
def delete_schedule(doctor_id, schedule_id):
    doctor = get_scoped_or_404(Doctor, doctor_id)
    schedule = DoctorSchedule.query.filter_by(id=schedule_id, doctor_id=doctor.id).first()
    if schedule is None:
        raise ConflictError("Schedule not found.")
    db.session.delete(schedule)
    audit("doctor.schedule_deleted", "doctor", doctor.id, {"schedule_id": schedule_id}, clinic_id=doctor.clinic_id, user_id=g.user.id)
    db.session.commit()
    return ok({"message": "Schedule removed."})


def _schedule_from_payload(doctor, payload):
    raw_weekday = payload.get("weekday")
    if raw_weekday in (None, "") or isinstance(raw_weekday, bool):
        raise ValidationError("Weekday is required.")
    if isinstance(raw_weekday, float) and not raw_weekday.is_integer():
        raise ValidationError("Weekday must be a whole number from Monday (0) to Sunday (6).")
    try:
        weekday = int(raw_weekday)
    except (TypeError, ValueError):
        raise ValidationError("Weekday must be a whole number from Monday (0) to Sunday (6).")
    if weekday < 0 or weekday > 6:
        raise ValidationError("Weekday must be between Monday and Sunday.")
    start = parse_time(payload.get("start_time"), "Start time")
    end = parse_time(payload.get("end_time"), "End time")
    if start >= end:
        raise ValidationError("End time must be after start time.")
    break_start = parse_time(payload.get("break_start"), "Break start", required=False)
    break_end = parse_time(payload.get("break_end"), "Break end", required=False)
    if bool(break_start) != bool(break_end):
        raise ValidationError("Provide both break start and break end.")
    if break_start and break_end:
        if break_start >= break_end:
            raise ValidationError("Break end must be after break start.")
        if break_start < start or break_end > end:
            raise ValidationError("Break must be within working hours.")
    raw_slot_minutes = payload.get("slot_minutes")
    if raw_slot_minutes in (None, ""):
        raw_slot_minutes = 15
    if isinstance(raw_slot_minutes, bool) or (isinstance(raw_slot_minutes, float) and not raw_slot_minutes.is_integer()):
        raise ValidationError("Slot duration must be a whole number.")
    try:
        slot_minutes = int(raw_slot_minutes)
    except (TypeError, ValueError):
        raise ValidationError("Slot duration must be a whole number.")
    if slot_minutes < 5 or slot_minutes > 240:
        raise ValidationError("Slot duration must be between 5 and 240 minutes.")
    max_tokens = payload.get("max_tokens")
    if max_tokens in ("", None):
        max_tokens = None
    else:
        try:
            max_tokens = int(max_tokens)
        except (TypeError, ValueError):
            raise ValidationError("Maximum tokens must be a number.")
        if max_tokens < 1:
            max_tokens = None
    return DoctorSchedule(
        clinic_id=doctor.clinic_id,
        doctor_id=doctor.id,
        weekday=weekday,
        start_time=start,
        end_time=end,
        break_start=break_start,
        break_end=break_end,
        slot_minutes=slot_minutes,
        max_tokens=max_tokens,
        is_active=bool(payload.get("is_active", True)),
    )


def _ensure_no_schedule_overlap(doctor, schedule, exclude_id=None):
    if not schedule.is_active:
        return
    query = DoctorSchedule.query.filter(
        DoctorSchedule.doctor_id == doctor.id,
        DoctorSchedule.weekday == schedule.weekday,
        DoctorSchedule.is_active.is_(True),
        DoctorSchedule.start_time < schedule.end_time,
        DoctorSchedule.end_time > schedule.start_time,
    )
    if exclude_id:
        query = query.filter(DoctorSchedule.id != exclude_id)
    if query.first():
        raise ConflictError("This schedule overlaps another active shift for the doctor.")


@doctors_bp.get("/api/doctors/<doctor_id>/leaves")
@permission_required("doctors.view")
def list_leaves(doctor_id):
    doctor = get_scoped_or_404(Doctor, doctor_id)
    leaves = (
        DoctorLeave.query.filter_by(doctor_id=doctor.id)
        .order_by(DoctorLeave.start_date.desc())
        .limit(100)
        .all()
    )
    return ok([leave_dict(l) for l in leaves])


@doctors_bp.post("/api/doctors/<doctor_id>/leaves")
@permission_required("doctors.manage")
def add_leave(doctor_id):
    doctor = get_scoped_or_404(Doctor, doctor_id)
    payload = json_body()
    start = parse_date(payload.get("start_date"), "Start date")
    end = parse_date(payload.get("end_date"), "End date")
    if end < start:
        raise ValidationError("Leave end date must be on or after the start date.")
    overlapping = DoctorLeave.query.filter(
        DoctorLeave.doctor_id == doctor.id,
        DoctorLeave.status == "approved",
        DoctorLeave.start_date <= end,
        DoctorLeave.end_date >= start,
    ).first()
    if overlapping:
        raise ConflictError("This leave overlaps an existing approved leave.")
    leave = DoctorLeave(
        clinic_id=doctor.clinic_id,
        doctor_id=doctor.id,
        start_date=start,
        end_date=end,
        leave_type=(payload.get("leave_type") or "planned")[:40],
        reason=(payload.get("reason") or None),
        status="approved",
        created_by=g.user.id,
    )
    db.session.add(leave)
    audit("doctor.leave_added", "doctor", doctor.id, {"start": start.isoformat(), "end": end.isoformat()}, clinic_id=doctor.clinic_id, user_id=g.user.id)
    db.session.commit()
    return ok({"leave": leave_dict(leave)}, status=201)


@doctors_bp.delete("/api/doctors/<doctor_id>/leaves/<leave_id>")
@permission_required("doctors.manage")
def cancel_leave(doctor_id, leave_id):
    doctor = get_scoped_or_404(Doctor, doctor_id)
    leave = DoctorLeave.query.filter_by(id=leave_id, doctor_id=doctor.id).first()
    if leave is None:
        raise ConflictError("Leave not found.")
    leave.status = "cancelled"
    audit("doctor.leave_cancelled", "doctor", doctor.id, {"leave_id": leave.id}, clinic_id=doctor.clinic_id, user_id=g.user.id)
    db.session.commit()
    return ok({"message": "Leave cancelled."})


@doctors_bp.get("/api/doctors/<doctor_id>/slots")
@permission_required("appointments.view")
def doctor_available_slots(doctor_id):
    doctor = get_scoped_or_404(Doctor, doctor_id)
    day = parse_date(request.args.get("date"), "Date")
    slots = doctor_slots(current_clinic(), doctor, day)
    return ok(
        {
            "date": day.isoformat(),
            "doctor_id": doctor.id,
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


@doctors_bp.get("/api/doctors/<doctor_id>/queue")
@permission_required("tokens.view")
def doctor_queue(doctor_id):
    doctor = get_scoped_or_404(Doctor, doctor_id)
    if (
        g.user.doctor_profile
        and g.user.doctor_profile.id != doctor.id
        and "tokens.manage_all" not in g.permissions
    ):
        from ..utils.errors import ForbiddenError

        raise ForbiddenError("You can only view your own queue.")
    day = parse_date(request.args.get("date"), "Date", required=False) or clinic_today(current_clinic())
    snapshot = queue_snapshot(current_clinic(), day, doctor.id)
    return ok(
        {
            "date": day.isoformat(),
            "doctor": doctor_summary(doctor),
            "counts": snapshot["counts"],
            "total": snapshot["total"],
            "average_wait_minutes": snapshot["average_wait_minutes"],
            "current": token_dict(snapshot["current"]) if snapshot["current"] else None,
            "next": token_dict(snapshot["next"]) if snapshot["next"] else None,
            "waiting": [token_dict(t) for t in snapshot["waiting"]],
        }
    )


@doctors_bp.get("/api/doctors/<doctor_id>/performance")
@permission_required("doctors.view")
def doctor_performance(doctor_id):
    doctor = get_scoped_or_404(Doctor, doctor_id)
    start, end = date_range_args(default_days=30)
    start_utc, end_utc = utc_bounds_for_local_range(doctor.clinic, start, end)
    tokens = DailyToken.query.filter(
        DailyToken.clinic_id == doctor.clinic_id,
        DailyToken.doctor_id == doctor.id,
        DailyToken.token_date >= start,
        DailyToken.token_date <= end,
    ).all()
    completed = [t for t in tokens if t.status == TokenStatus.COMPLETED]
    waits = [
        max(0, (as_utc(t.called_at) - as_utc(t.created_at)).total_seconds() / 60)
        for t in tokens
        if t.called_at and t.created_at
    ]
    consultations = Consultation.query.filter(
        Consultation.clinic_id == doctor.clinic_id,
        Consultation.doctor_id == doctor.id,
        Consultation.status == ConsultationStatus.COMPLETED,
        Consultation.completed_at >= start_utc,
        Consultation.completed_at < end_utc,
    ).all()
    durations = [
        max(0, (as_utc(c.completed_at) - as_utc(c.started_at)).total_seconds() / 60)
        for c in consultations
        if c.completed_at and c.started_at
    ]
    revenue = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .join(Consultation, Invoice.consultation_id == Consultation.id)
        .filter(
            Payment.clinic_id == doctor.clinic_id,
            Consultation.doctor_id == doctor.id,
            Payment.paid_at >= start_utc,
            Payment.paid_at < end_utc,
        )
        .scalar()
        or 0
    )
    daily = (
        db.session.query(DailyToken.token_date, func.count(DailyToken.id))
        .filter(
            DailyToken.clinic_id == doctor.clinic_id,
            DailyToken.doctor_id == doctor.id,
            DailyToken.token_date >= start,
            DailyToken.token_date <= end,
        )
        .group_by(DailyToken.token_date)
        .order_by(DailyToken.token_date.asc())
        .all()
    )
    return ok(
        {
            "doctor": doctor_summary(doctor),
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "totals": {
                "tokens": len(tokens),
                "completed": len(completed),
                "patients": len({t.patient_id for t in tokens}),
                "consultations": len(consultations),
                "revenue": float(revenue),
                "average_wait_minutes": round(sum(waits) / len(waits), 1) if waits else 0,
                "average_consult_minutes": round(sum(durations) / len(durations), 1) if durations else 0,
            },
            "daily": [{"date": d.isoformat(), "count": c} for d, c in daily],
        }
    )
