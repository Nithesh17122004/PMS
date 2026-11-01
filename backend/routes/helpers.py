from __future__ import annotations

from datetime import date, datetime, timezone

from flask import g, request, send_file

from ..extensions import db
from ..models import Doctor
from ..permissions.tenant import current_clinic, get_scoped_or_404
from ..utils.datetime_utils import parse_date
from ..utils.errors import ValidationError


def json_body() -> dict:
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict()
    if not isinstance(payload, dict):
        raise ValidationError("A JSON object is required.")
    return payload


def scoped_or_404(model, record_id, active_only=False):
    return get_scoped_or_404(model, record_id, active_only=active_only)


def doctor_or_404(doctor_id):
    return scoped_or_404(Doctor, doctor_id)


def require_doctor_clinic(doctor_id):
    clinic = current_clinic()
    doctor = Doctor.query.filter_by(id=doctor_id, clinic_id=clinic.id).first()
    if doctor is None:
        from ..utils.errors import NotFoundError

        raise NotFoundError("Doctor not found.")
    return doctor


def date_arg(name="date", required=False, default_today=False):
    value = request.args.get(name)
    if not value and default_today:
        from ..utils.datetime_utils import clinic_today

        return clinic_today(current_clinic())
    return parse_date(value, name.replace("_", " ").title(), required=required)


def date_range_args(default_days=30):
    clinic = current_clinic()
    from ..utils.datetime_utils import clinic_today

    end = date_arg("end") or clinic_today(clinic)
    start = date_arg("start") or end - __import__("datetime").timedelta(days=default_days)
    if start > end:
        raise ValidationError("Start date cannot be after end date.")
    return start, end


def csv_response(content: str, filename: str):
    from flask import Response

    return Response(
        "\ufeff" + content,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def pdf_response(buffer, filename: str):
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=filename,
        max_age=0,
    )


def scope_doctor_id():
    """Doctors without manage-all are forced to their own doctor profile."""
    user = g.get("user")
    if user is None:
        return None
    if "tokens.manage_all" in getattr(g, "permissions", set()):
        return request.args.get("doctor_id") or None
    doctor = user.doctor_profile
    return doctor.id if doctor else None


def can_manage_all() -> bool:
    return "tokens.manage_all" in getattr(g, "permissions", set())


def utc_now():
    return datetime.now(timezone.utc)
