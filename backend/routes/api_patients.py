from __future__ import annotations

import os

from flask import Blueprint, g, request, send_file
from sqlalchemy import or_

from ..auth.security import audit
from ..extensions import db
from ..models import (
    Appointment,
    Consultation,
    DailyToken,
    FollowUpPlan,
    Invoice,
    LabOrder,
    MedicalDocument,
    Patient,
    Payment,
    Prescription,
    TokenStatus,
)
from ..permissions.rbac import permission_required
from ..permissions.tenant import current_clinic, get_scoped_or_404
from ..services.patient_service import (
    create_patient,
    merge_patients,
    patient_context,
    search_patients,
    update_patient,
)
from ..utils.datetime_utils import as_utc
from ..utils.errors import NotFoundError, ValidationError
from ..utils.responses import ok, pagination_meta, parse_pagination
from ..utils.serializers import (
    appointment_dict,
    consultation_dict,
    followup_dict,
    invoice_dict,
    lab_order_dict,
    patient_detail,
    patient_summary,
    prescription_dict,
    token_dict,
)
from ..utils.uploads import absolute_upload_path, save_document
from .helpers import json_body, scoped_or_404

patients_bp = Blueprint("patients", __name__)


@patients_bp.get("/api/patients")
@permission_required("patients.view")
def list_patients():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args)
    query = Patient.query.filter(Patient.clinic_id == clinic.id)
    status = request.args.get("status", "active")
    if status == "active":
        query = query.filter(Patient.is_active.is_(True), Patient.merged_into_id.is_(None))
    elif status == "inactive":
        query = query.filter(Patient.is_active.is_(False), Patient.merged_into_id.is_(None))
    elif status == "merged":
        query = query.filter(Patient.merged_into_id.isnot(None))
    gender = request.args.get("gender")
    if gender:
        query = query.filter(Patient.gender == gender)
    sort = request.args.get("sort", "recent")
    if sort == "name":
        query = query.order_by(Patient.first_name.asc(), Patient.last_name.asc())
    elif sort == "code":
        query = query.order_by(Patient.patient_code.asc())
    else:
        query = query.order_by(Patient.created_at.desc())
    total = query.count()
    patients = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok(
        [patient_summary(p) for p in patients],
        pagination_meta(total, page, per_page),
    )


@patients_bp.post("/api/patients/search")
@permission_required("patients.view")
def search_patient_records():
    payload = json_body()
    term = (payload.get("query") or "").strip()
    if len(term) > 100:
        raise ValidationError("Search term is too long.")
    patients = search_patients(current_clinic(), term, limit=int(payload.get("limit") or 20))
    return ok({"patients": [patient_summary(p) for p in patients], "count": len(patients)})


@patients_bp.post("/api/patients")
@permission_required("patients.create")
def register_patient():
    payload = json_body()
    patient = create_patient(
        current_clinic(),
        g.user,
        payload,
        override_duplicate=bool(payload.get("override_duplicate")),
        duplicate_reason=payload.get("duplicate_reason"),
    )
    return ok({"patient": patient_detail(patient)}, status=201)


@patients_bp.get("/api/patients/<patient_id>")
@permission_required("patients.view")
def patient_profile(patient_id):
    clinic = current_clinic()
    patient = get_scoped_or_404(Patient, patient_id)
    context = patient_context(clinic, patient)
    permissions = g.permissions
    outstanding = sum(
        (float(inv.balance) for inv in context["invoices"] if inv.status not in ("cancelled", "paid")),
        0,
    )
    data = patient_detail(patient)
    data["stats"] = {
        "appointments": len(context["appointments"]),
        "visits": len(context["tokens"]),
        "consultations": len(context["consultations"]),
        "prescriptions": len(context["prescriptions"]),
        "followups": len(context["followups"]),
        "invoices": len(context["invoices"]),
        "lab_orders": len(context["lab_orders"]),
        "documents": len(context["documents"]),
        "outstanding": round(outstanding, 2),
    }
    data["appointments"] = [appointment_dict(a) for a in context["appointments"][:20]]
    data["visits"] = [token_dict(t) for t in context["tokens"][:20]]
    data["consultations"] = [
        consultation_dict(c, include_clinical="consultations.view" in permissions)
        for c in context["consultations"][:20]
    ]
    data["prescriptions"] = (
        [prescription_dict(p) for p in context["prescriptions"][:20]]
        if "prescriptions.view" in permissions
        else []
    )
    data["followups"] = [followup_dict(f) for f in context["followups"][:20]]
    data["invoices"] = (
        [invoice_dict(i, include_payments=False) for i in context["invoices"][:20]]
        if "billing.view" in permissions
        else []
    )
    data["lab_orders"] = (
        [lab_order_dict(o) for o in context["lab_orders"][:20]]
        if "lab.view" in permissions
        else []
    )
    data["documents"] = [
        {
            "id": doc.id,
            "original_name": doc.original_name,
            "mime_type": doc.mime_type,
            "size_bytes": doc.size_bytes,
            "category": doc.category,
            "description": doc.description,
            "uploaded_by": doc.uploader.full_name if doc.uploader else None,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }
        for doc in context["documents"]
    ]
    return ok({"patient": data})


@patients_bp.put("/api/patients/<patient_id>")
@permission_required("patients.edit")
def edit_patient(patient_id):
    patient = get_scoped_or_404(Patient, patient_id)
    updated = update_patient(patient, g.user, json_body())
    return ok({"patient": patient_detail(updated)})


@patients_bp.post("/api/patients/<patient_id>/merge")
@permission_required("patients.merge")
def merge_patient(patient_id):
    source = get_scoped_or_404(Patient, patient_id)
    payload = json_body()
    target = get_scoped_or_404(Patient, payload.get("target_id") or "")
    result = merge_patients(current_clinic(), g.user, source, target, payload.get("reason") or "")
    return ok(
        {
            "message": f"Patient records merged into {result['target'].patient_code}.",
            "source_id": source.id,
            "target": patient_summary(result["target"]),
            "moved": result["moved"],
        }
    )


@patients_bp.get("/api/patients/<patient_id>/documents")
@permission_required("patients.view")
def list_documents(patient_id):
    patient = get_scoped_or_404(Patient, patient_id)
    documents = (
        MedicalDocument.query.filter_by(clinic_id=patient.clinic_id, patient_id=patient.id)
        .order_by(MedicalDocument.created_at.desc())
        .all()
    )
    return ok(
        [
            {
                "id": doc.id,
                "original_name": doc.original_name,
                "mime_type": doc.mime_type,
                "size_bytes": doc.size_bytes,
                "category": doc.category,
                "description": doc.description,
                "uploaded_by": doc.uploader.full_name if doc.uploader else None,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in documents
        ]
    )


@patients_bp.post("/api/patients/<patient_id>/documents")
@permission_required("patients.edit")
def upload_document(patient_id):
    patient = get_scoped_or_404(Patient, patient_id)
    file = request.files.get("file")
    relative_path, stored_name, size = save_document(file, patient.clinic_id)
    document = MedicalDocument(
        clinic_id=patient.clinic_id,
        patient_id=patient.id,
        uploaded_by=g.user.id,
        original_name=(file.filename or stored_name)[:255],
        stored_name=relative_path,
        mime_type=file.mimetype,
        size_bytes=size,
        category=(request.form.get("category") or "general")[:60],
        description=(request.form.get("description") or "")[:255] or None,
    )
    db.session.add(document)
    audit(
        "patient.document_uploaded",
        "document",
        document.id,
        {"patient_id": patient.id, "category": document.category, "size": size},
        clinic_id=patient.clinic_id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok(
        {
            "id": document.id,
            "original_name": document.original_name,
            "mime_type": document.mime_type,
            "size_bytes": document.size_bytes,
            "category": document.category,
        },
        status=201,
    )


@patients_bp.get("/api/documents/<document_id>/download")
@permission_required("patients.view")
def download_document(document_id):
    document = get_scoped_or_404(MedicalDocument, document_id)
    path = absolute_upload_path(document.stored_name)
    if path is None:
        raise NotFoundError("The stored file is no longer available.")
    audit(
        "patient.document_downloaded",
        "document",
        document.id,
        {"patient_id": document.patient_id},
        clinic_id=document.clinic_id,
        user_id=g.user.id,
    )
    db.session.commit()
    return send_file(
        path,
        mimetype=document.mime_type or "application/octet-stream",
        as_attachment=True,
        download_name=document.original_name,
        max_age=0,
    )


@patients_bp.delete("/api/documents/<document_id>")
@permission_required("patients.edit")
def delete_document(document_id):
    document = get_scoped_or_404(MedicalDocument, document_id)
    path = absolute_upload_path(document.stored_name)
    audit(
        "patient.document_deleted",
        "document",
        document.id,
        {"patient_id": document.patient_id},
        clinic_id=document.clinic_id,
        user_id=g.user.id,
    )
    db.session.delete(document)
    db.session.commit()
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    return ok({"message": "Document deleted."})


@patients_bp.get("/api/patients/<patient_id>/timeline")
@permission_required("patients.view")
def patient_timeline(patient_id):
    clinic = current_clinic()
    patient = get_scoped_or_404(Patient, patient_id)
    context = patient_context(clinic, patient)
    permissions = g.permissions
    events = [
        {
            "type": "registration",
            "title": "Patient registered",
            "detail": f"Patient ID {patient.patient_code}",
            "at": patient.created_at,
        }
    ]
    for appointment in context["appointments"]:
        events.append(
            {
                "type": "appointment",
                "title": f"Appointment {appointment.status.replace('_', ' ')}",
                "detail": f"{appointment.doctor.full_name} · {appointment.appointment_date.strftime('%d %b %Y')}",
                "at": appointment.created_at,
            }
        )
    for token in context["tokens"]:
        events.append(
            {
                "type": "token",
                "title": f"Token {token.display_number} · {token.status.replace('_', ' ')}",
                "detail": f"{token.doctor.full_name} · {token.token_date.strftime('%d %b %Y')}",
                "at": token.created_at,
            }
        )
    if "consultations.view" in permissions:
        for consultation in context["consultations"]:
            events.append(
                {
                    "type": "consultation",
                    "title": f"Consultation {consultation.consultation_code}",
                    "detail": consultation.diagnosis_summary or consultation.doctor.full_name,
                    "at": consultation.created_at,
                }
            )
    if "prescriptions.view" in permissions:
        for prescription in context["prescriptions"]:
            events.append(
                {
                    "type": "prescription",
                    "title": f"Prescription {prescription.prescription_code}",
                    "detail": f"{len(prescription.items)} medicine(s)",
                    "at": prescription.issued_at,
                }
            )
    for plan in context["followups"]:
        events.append(
            {
                "type": "followup",
                "title": f"Follow-up {plan.status}",
                "detail": f"Due {plan.due_date.strftime('%d %b %Y')} · {plan.doctor.full_name}",
                "at": plan.created_at,
            }
        )
    if "billing.view" in permissions:
        for invoice in context["invoices"]:
            events.append(
                {
                    "type": "invoice",
                    "title": f"Invoice {invoice.invoice_number} · {invoice.status}",
                    "detail": f"Total {invoice.total} · Balance {invoice.balance}",
                    "at": invoice.created_at,
                }
            )
            for payment in invoice.payments:
                events.append(
                    {
                        "type": "payment",
                        "title": f"Payment received · {payment.method.replace('_', ' ')}",
                        "detail": f"{payment.amount} · {payment.payment_code}",
                        "at": payment.paid_at,
                    }
                )
    if "lab.view" in permissions:
        for order in context["lab_orders"]:
            events.append(
                {
                    "type": "lab",
                    "title": f"Lab order {order.order_number} · {order.status.replace('_', ' ')}",
                    "detail": f"{len(order.items)} test(s)",
                    "at": order.created_at,
                }
            )
    events.sort(key=lambda e: as_utc(e["at"]) or patient.created_at, reverse=True)
    for event in events:
        event["at"] = as_utc(event["at"]).isoformat() if event["at"] else None
    return ok(events)
