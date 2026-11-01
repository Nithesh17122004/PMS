from __future__ import annotations

import logging

from flask import Blueprint, g, request

from ..extensions import db
from ..models import (
    Consultation,
    ConsultationStatus,
    DailyToken,
    Doctor,
    Patient,
    Prescription,
    PrescriptionStatus,
)
from ..permissions.rbac import permission_required
from ..permissions.tenant import current_clinic, get_scoped_or_404
from ..services.billing_service import create_consultation_invoice
from ..services.consultation_service import (
    cancel_prescription,
    complete_consultation,
    create_standalone_draft,
    issue_prescription,
    save_consultation,
    start_consultation_for_token,
)
from ..services.pdf_service import prescription_pdf
from ..utils.datetime_utils import parse_date
from ..utils.errors import ForbiddenError
from ..utils.responses import ok, pagination_meta, parse_pagination
from ..utils.serializers import (
    consultation_dict,
    invoice_dict,
    patient_detail,
    prescription_dict,
    token_dict,
)
from .helpers import date_range_args, json_body, pdf_response, scoped_or_404

logger = logging.getLogger(__name__)
consultations_bp = Blueprint("consultations", __name__)


def _scope_doctor(query, model):
    if g.user.doctor_profile and "tokens.manage_all" not in g.permissions:
        return query.filter(model.doctor_id == g.user.doctor_profile.id)
    return query


@consultations_bp.get("/api/consultations")
@permission_required("consultations.view")
def list_consultations():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args)
    query = Consultation.query.filter(Consultation.clinic_id == clinic.id)
    query = _scope_doctor(query, Consultation)
    patient_id = request.args.get("patient_id")
    if patient_id:
        query = query.filter(Consultation.patient_id == patient_id)
    doctor_id = request.args.get("doctor_id")
    if doctor_id:
        query = query.filter(Consultation.doctor_id == doctor_id)
    status = request.args.get("status")
    if status:
        query = query.filter(Consultation.status == status)
    start = parse_date(request.args.get("start"), "Start date", required=False)
    end = parse_date(request.args.get("end"), "End date", required=False)
    if start:
        query = query.filter(Consultation.created_at >= __import__("datetime").datetime.combine(start, __import__("datetime").time.min))
    if end:
        query = query.filter(Consultation.created_at <= __import__("datetime").datetime.combine(end, __import__("datetime").time.max))
    query = query.order_by(Consultation.created_at.desc())
    total = query.count()
    consultations = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok(
        [consultation_dict(c, include_clinical=True) for c in consultations],
        pagination_meta(total, page, per_page),
    )


@consultations_bp.get("/api/consultations/<consultation_id>")
@permission_required("consultations.view")
def get_consultation(consultation_id):
    consultation = get_scoped_or_404(Consultation, consultation_id)
    if (
        g.user.doctor_profile
        and g.user.doctor_profile.id != consultation.doctor_id
        and "tokens.manage_all" not in g.permissions
        and g.user.role
        and g.user.role.slug == "doctor"
    ):
        raise ForbiddenError("You can only view your own consultations.")
    data = consultation_dict(consultation, include_clinical=True)
    previous = (
        Consultation.query.filter(
            Consultation.clinic_id == consultation.clinic_id,
            Consultation.patient_id == consultation.patient_id,
            Consultation.id != consultation.id,
            Consultation.status == ConsultationStatus.COMPLETED,
        )
        .order_by(Consultation.completed_at.desc())
        .limit(10)
        .all()
    )
    data["previous_consultations"] = [
        consultation_dict(c, include_clinical=True) for c in previous
    ]
    data["patient"] = patient_detail(consultation.patient)
    data["allergies"] = consultation.patient.allergies
    data["medical_history"] = consultation.patient.medical_history
    return ok({"consultation": data})


@consultations_bp.post("/api/consultations/start")
@permission_required("consultations.create")
def start_consultation():
    payload = json_body()
    token = get_scoped_or_404(DailyToken, payload.get("token_id") or "")
    consultation = start_consultation_for_token(token, g.user)
    return ok({"consultation": consultation_dict(consultation), "token": token_dict(token)})


@consultations_bp.post("/api/consultations")
@permission_required("consultations.create")
def create_consultation():
    payload = json_body()
    patient = get_scoped_or_404(Patient, payload.get("patient_id") or "")
    doctor = get_scoped_or_404(Doctor, payload.get("doctor_id") or "")
    consultation = create_standalone_draft(current_clinic(), g.user, patient, doctor)
    return ok({"consultation": consultation_dict(consultation)}, status=201)


@consultations_bp.put("/api/consultations/<consultation_id>")
@permission_required("consultations.create")
def update_consultation(consultation_id):
    consultation = get_scoped_or_404(Consultation, consultation_id)
    consultation = save_consultation(consultation, g.user, json_body())
    return ok({"consultation": consultation_dict(consultation)})


@consultations_bp.post("/api/consultations/<consultation_id>/complete")
@permission_required("consultations.complete")
def finish_consultation(consultation_id):
    consultation = get_scoped_or_404(Consultation, consultation_id)
    consultation = complete_consultation(consultation, g.user, json_body())
    invoice = None
    clinic = current_clinic()
    if clinic.settings and clinic.settings.auto_invoice_on_completion:
        try:
            invoice = create_consultation_invoice(consultation, g.user)
        except Exception:
            logger.exception("Auto invoice failed for consultation %s", consultation.id)
            db.session.rollback()
    return ok(
        {
            "consultation": consultation_dict(consultation),
            "invoice": invoice_dict(invoice, include_payments=False) if invoice else None,
        }
    )


@consultations_bp.post("/api/consultations/<consultation_id>/invoice")
@permission_required("billing.create")
def consultation_invoice(consultation_id):
    consultation = get_scoped_or_404(Consultation, consultation_id)
    invoice = create_consultation_invoice(consultation, g.user)
    return ok({"invoice": invoice_dict(invoice)}, status=201)


@consultations_bp.post("/api/consultations/<consultation_id>/prescriptions")
@permission_required("prescriptions.create")
def create_prescription(consultation_id):
    consultation = get_scoped_or_404(Consultation, consultation_id)
    prescription = issue_prescription(consultation, g.user, json_body())
    return ok({"prescription": prescription_dict(prescription)}, status=201)


@consultations_bp.get("/api/prescriptions")
@permission_required("prescriptions.view")
def list_prescriptions():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args)
    query = Prescription.query.filter(Prescription.clinic_id == clinic.id)
    query = _scope_doctor(query, Prescription)
    patient_id = request.args.get("patient_id")
    if patient_id:
        query = query.filter(Prescription.patient_id == patient_id)
    doctor_id = request.args.get("doctor_id")
    if doctor_id:
        query = query.filter(Prescription.doctor_id == doctor_id)
    query = query.order_by(Prescription.issued_at.desc())
    total = query.count()
    prescriptions = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok([prescription_dict(p) for p in prescriptions], pagination_meta(total, page, per_page))


@consultations_bp.get("/api/prescriptions/<prescription_id>")
@permission_required("prescriptions.view")
def get_prescription(prescription_id):
    prescription = get_scoped_or_404(Prescription, prescription_id)
    return ok({"prescription": prescription_dict(prescription)})


@consultations_bp.post("/api/prescriptions/<prescription_id>/cancel")
@permission_required("prescriptions.create")
def cancel_prescription_route(prescription_id):
    prescription = get_scoped_or_404(Prescription, prescription_id)
    payload = json_body()
    updated = cancel_prescription(prescription, g.user, payload.get("reason") or "")
    return ok({"prescription": prescription_dict(updated)})


@consultations_bp.get("/api/prescriptions/<prescription_id>/pdf")
@permission_required("prescriptions.view")
def prescription_pdf_route(prescription_id):
    prescription = get_scoped_or_404(Prescription, prescription_id)
    if (
        g.user.doctor_profile
        and g.user.doctor_profile.id != prescription.doctor_id
        and "tokens.manage_all" not in g.permissions
        and g.user.role
        and g.user.role.slug == "doctor"
    ):
        raise ForbiddenError("You can only print your own prescriptions.")
    buffer = prescription_pdf(prescription)
    return pdf_response(buffer, f"prescription-{prescription.prescription_code}.pdf")
