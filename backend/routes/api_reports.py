from __future__ import annotations

from flask import Blueprint, g, request

from ..permissions.rbac import permission_required
from ..permissions.tenant import current_clinic
from ..services.pdf_service import report_pdf
from ..services.report_service import REPORT_TITLES, build_report, report_to_csv
from ..utils.errors import ValidationError
from ..utils.responses import ok
from .helpers import csv_response, date_range_args, pdf_response

reports_bp = Blueprint("reports", __name__)

REPORT_GROUPS = {
    "Patients": ["patients"],
    "Queue": ["tokens", "doctor_queue", "waiting_time", "cancelled_tokens", "skipped_tokens"],
    "Clinical": ["consultations", "consultation_time", "followup_completion", "missed_followups"],
    "Appointments": ["appointments"],
    "Finance": ["revenue", "daily_collection"],
    "Operations": ["inventory", "lab"],
}


def _build(report_type: str):
    clinic = current_clinic()
    start, end = date_range_args(default_days=30)
    doctor_id = request.args.get("doctor_id") or None
    if doctor_id and g.user.doctor_profile and "tokens.manage_all" not in g.permissions:
        doctor_id = g.user.doctor_profile.id
    elif g.user.doctor_profile and "tokens.manage_all" not in g.permissions:
        doctor_id = g.user.doctor_profile.id
    try:
        return clinic, build_report(clinic, report_type, start, end, doctor_id)
    except ValueError as exc:
        raise ValidationError(str(exc))


@reports_bp.get("/api/reports/types")
@permission_required("reports.view")
def report_types():
    return ok(
        {
            "types": [
                {"key": key, "title": title, "group": group}
                for group, keys in REPORT_GROUPS.items()
                for key in keys
                for title in [REPORT_TITLES[key]]
            ],
            "groups": REPORT_GROUPS,
        }
    )


@reports_bp.get("/api/reports/<report_type>")
@permission_required("reports.view")
def report_data(report_type):
    clinic, report = _build(report_type)
    return ok(
        {
            "report": report,
            "clinic": {"name": clinic.name, "currency": clinic.settings.currency if clinic.settings else "INR"},
        }
    )


@reports_bp.get("/api/reports/<report_type>/export.csv")
@permission_required("reports.export")
def export_csv(report_type):
    _, report = _build(report_type)
    filename = f"{report_type}-{report['date_label'].replace(' ', '').replace('–', '-')}.csv"
    return csv_response(report_to_csv(report), filename)


@reports_bp.get("/api/reports/<report_type>/export.pdf")
@permission_required("reports.export")
def export_pdf(report_type):
    clinic, report = _build(report_type)
    buffer = report_pdf(
        report["title"],
        clinic,
        report["columns"],
        report["rows"],
        report["summary"],
        report["date_label"],
    )
    return pdf_response(buffer, f"{report_type}-report.pdf")
