from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, abort, send_file
from flask_limiter.util import get_remote_address

from ..extensions import limiter
from ..models import Clinic, DailyToken, Doctor, TokenStatus
from ..services.token_service import queue_snapshot
from ..utils.datetime_utils import clinic_today
from ..utils.responses import ok
from ..utils.uploads import absolute_upload_path

public_bp = Blueprint("public", __name__)


@public_bp.get("/api/public/clinics/<slug>/logo")
@limiter.limit("120 per minute", key_func=get_remote_address)
def clinic_logo(slug):
    clinic = Clinic.query.filter_by(slug=slug, is_active=True).first()
    if clinic is None or not clinic.logo_path:
        abort(404)
    path = absolute_upload_path(clinic.logo_path)
    if path is None:
        abort(404)
    return send_file(path, mimetype="image/png", max_age=3600, conditional=True)


@public_bp.get("/api/public/display/<display_key>")
@limiter.limit("180 per minute", key_func=get_remote_address)
def display_data(display_key):
    clinic = Clinic.query.filter_by(display_key=display_key, is_active=True).first()
    if clinic is None or not clinic.settings or not clinic.settings.public_display_enabled:
        abort(404)
    today = clinic_today(clinic)
    doctors = Doctor.query.filter_by(clinic_id=clinic.id, is_active=True).order_by(Doctor.full_name).all()
    queues = []
    now_serving = []
    for doctor in doctors:
        snapshot = queue_snapshot(clinic, today, doctor.id)
        if snapshot["total"] == 0 and not doctor.is_available:
            continue
        current = snapshot["current"]
        current_data = None
        if current is not None:
            current_data = {
                "display_number": current.display_number,
                "status": current.status,
                "room_number": doctor.room_number,
            }
            now_serving.append(
                {
                    "display_number": current.display_number,
                    "doctor": doctor.full_name,
                    "room_number": doctor.room_number,
                    "status": current.status,
                }
            )
        queues.append(
            {
                "doctor_id": doctor.id,
                "doctor": doctor.full_name,
                "specialization": doctor.specialization,
                "room_number": doctor.room_number,
                "current": current_data,
                "next": snapshot["next"].display_number if snapshot["next"] else None,
                "waiting": [
                    token.display_number for token in snapshot["waiting"][:6]
                ],
                "counts": snapshot["counts"],
                "total": snapshot["total"],
                "average_wait_minutes": snapshot["average_wait_minutes"],
            }
        )
    all_snapshot = queue_snapshot(clinic, today)
    return ok(
        {
            "clinic": {
                "name": clinic.name,
                "city": clinic.city,
                "logo_url": f"/api/public/clinics/{clinic.slug}/logo" if clinic.logo_path else None,
                "is_demo": clinic.is_demo,
                "timezone": clinic.settings.timezone,
                "currency": clinic.settings.currency,
            },
            "date": today.isoformat(),
            "display_message": clinic.settings.display_message,
            "token_mode": clinic.settings.token_mode,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "now_serving": now_serving,
            "queues": queues,
            "overall": {
                "waiting": all_snapshot["counts"].get(TokenStatus.WAITING, 0),
                "in_consultation": all_snapshot["counts"].get(TokenStatus.IN_CONSULTATION, 0),
                "completed": all_snapshot["counts"].get(TokenStatus.COMPLETED, 0),
                "total": all_snapshot["total"],
                "average_wait_minutes": all_snapshot["average_wait_minutes"],
            },
        }
    )
