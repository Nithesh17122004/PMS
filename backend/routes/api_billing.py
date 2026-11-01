from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from flask import Blueprint, g, request
from sqlalchemy import func, or_

from ..extensions import db
from ..models import Invoice, InvoiceStatus, Patient, Payment, Refund
from ..permissions.rbac import permission_required
from ..permissions.tenant import current_clinic, get_scoped_or_404
from ..services.billing_service import (
    collection_summary,
    create_invoice,
    record_payment,
    refund_payment,
    void_invoice,
)
from ..services.pdf_service import invoice_pdf
from ..utils.datetime_utils import clinic_today, parse_date, utc_bounds_for_local_range
from ..utils.errors import ValidationError
from ..utils.responses import ok, pagination_meta, parse_pagination
from ..utils.serializers import (
    invoice_dict,
    payment_dict,
    refund_dict,
)
from .helpers import date_range_args, json_body, pdf_response

billing_bp = Blueprint("billing", __name__)


@billing_bp.get("/api/invoices")
@permission_required("billing.view")
def list_invoices():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args)
    query = Invoice.query.filter(Invoice.clinic_id == clinic.id)
    status = request.args.get("status")
    if status and status != "all":
        query = query.filter(Invoice.status == status)
    patient_id = request.args.get("patient_id")
    if patient_id:
        query = query.filter(Invoice.patient_id == patient_id)
    consultation_id = request.args.get("consultation_id")
    if consultation_id:
        query = query.filter(Invoice.consultation_id == consultation_id)
    term = (request.args.get("q") or "").strip()
    if term:
        query = query.join(Patient, Invoice.patient_id == Patient.id).filter(
            or_(
                Invoice.invoice_number.ilike(f"%{term}%"),
                Patient.patient_code.ilike(f"%{term}%"),
                Patient.first_name.ilike(f"%{term}%"),
                Patient.last_name.ilike(f"%{term}%"),
            )
        )
    start = parse_date(request.args.get("start"), "Start date", required=False)
    end = parse_date(request.args.get("end"), "End date", required=False)
    if start or end:
        end = end or clinic_today(clinic)
        start = start or end - timedelta(days=30)
        if start > end:
            raise ValidationError("Start date cannot be after end date.")
        start_utc, end_utc = utc_bounds_for_local_range(clinic, start, end)
        query = query.filter(Invoice.issued_at >= start_utc, Invoice.issued_at < end_utc)
    query = query.order_by(Invoice.created_at.desc())
    total = query.count()
    invoices = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok(
        [invoice_dict(inv, include_payments=False) for inv in invoices],
        pagination_meta(total, page, per_page),
    )


@billing_bp.post("/api/invoices")
@permission_required("billing.create")
def create():
    payload = json_body()
    invoice = create_invoice(
        current_clinic(),
        g.user,
        patient_id=payload.get("patient_id"),
        items=payload.get("items") or [],
        discount_amount=payload.get("discount_amount") or 0,
        tax_rate=payload.get("tax_rate"),
        notes=payload.get("notes"),
        consultation_id=payload.get("consultation_id"),
        token_id=payload.get("token_id"),
        due_date=payload.get("due_date"),
        issue_now=payload.get("issue_now", True),
    )
    return ok({"invoice": invoice_dict(invoice)}, status=201)


@billing_bp.get("/api/invoices/<invoice_id>")
@permission_required("billing.view")
def get_invoice(invoice_id):
    invoice = get_scoped_or_404(Invoice, invoice_id)
    return ok({"invoice": invoice_dict(invoice)})


@billing_bp.get("/api/invoices/<invoice_id>/pdf")
@permission_required("billing.view")
def download_invoice(invoice_id):
    invoice = get_scoped_or_404(Invoice, invoice_id)
    buffer = invoice_pdf(invoice)
    return pdf_response(buffer, f"invoice-{invoice.invoice_number}.pdf")


@billing_bp.post("/api/invoices/<invoice_id>/payments")
@permission_required("billing.payment")
def add_payment(invoice_id):
    invoice = get_scoped_or_404(Invoice, invoice_id)
    payload = json_body()
    payment = record_payment(
        invoice,
        g.user,
        payload.get("amount"),
        payload.get("method") or "cash",
        reference_number=payload.get("reference_number"),
        notes=payload.get("notes"),
    )
    db.session.refresh(invoice)
    return ok({"payment": payment_dict(payment), "invoice": invoice_dict(invoice)}, status=201)


@billing_bp.post("/api/invoices/<invoice_id>/refund")
@permission_required("billing.refund")
def refund(invoice_id):
    invoice = get_scoped_or_404(Invoice, invoice_id)
    payload = json_body()
    payment = Payment.query.filter_by(
        id=payload.get("payment_id"), invoice_id=invoice.id, clinic_id=invoice.clinic_id
    ).first()
    if payment is None:
        raise ValidationError("Select a payment that belongs to this invoice.")
    refund_record = refund_payment(
        invoice,
        payment,
        g.user,
        payload.get("amount"),
        payload.get("reason") or "",
    )
    db.session.refresh(invoice)
    return ok(
        {"refund": refund_dict(refund_record), "invoice": invoice_dict(invoice)},
        status=201,
    )


@billing_bp.post("/api/invoices/<invoice_id>/void")
@permission_required("billing.refund")
def void(invoice_id):
    invoice = get_scoped_or_404(Invoice, invoice_id)
    updated = void_invoice(invoice, g.user, json_body().get("reason") or "")
    return ok({"invoice": invoice_dict(updated)})


@billing_bp.get("/api/payments")
@permission_required("billing.view")
def list_payments():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args)
    query = Payment.query.filter(Payment.clinic_id == clinic.id)
    start = parse_date(request.args.get("start"), "Start date", required=False)
    end = parse_date(request.args.get("end"), "End date", required=False)
    if start or end:
        end = end or clinic_today(clinic)
        start = start or end - timedelta(days=30)
        start_utc, end_utc = utc_bounds_for_local_range(clinic, start, end)
        query = query.filter(Payment.paid_at >= start_utc, Payment.paid_at < end_utc)
    method = request.args.get("method")
    if method:
        query = query.filter(Payment.method == method)
    term = (request.args.get("q") or "").strip()
    if term:
        query = query.join(Invoice, Payment.invoice_id == Invoice.id).join(
            Patient, Payment.patient_id == Patient.id
        ).filter(
            or_(
                Payment.payment_code.ilike(f"%{term}%"),
                Invoice.invoice_number.ilike(f"%{term}%"),
                Patient.patient_code.ilike(f"%{term}%"),
                Patient.first_name.ilike(f"%{term}%"),
                Patient.last_name.ilike(f"%{term}%"),
            )
        )
    query = query.order_by(Payment.paid_at.desc())
    total = query.count()
    payments = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok([payment_dict(p) for p in payments], pagination_meta(total, page, per_page))


@billing_bp.get("/api/billing/summary")
@permission_required("billing.view")
def summary():
    clinic = current_clinic()
    start, end = date_range_args(default_days=30)
    data = collection_summary(clinic, start, end)
    outstanding = (
        db.session.query(func.coalesce(func.sum(Invoice.balance), 0))
        .filter(
            Invoice.clinic_id == clinic.id,
            Invoice.status.in_([InvoiceStatus.UNPAID, InvoiceStatus.PARTIAL]),
            Invoice.balance > 0,
        )
        .scalar()
        or 0
    )
    invoice_counts = {
        status: Invoice.query.filter_by(clinic_id=clinic.id, status=status).count()
        for status in InvoiceStatus.ALL
    }
    return ok(
        {
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "gross": data["gross"],
            "refunded": data["refunded"],
            "net": data["net"],
            "by_method": data["by_method"],
            "payment_count": data["count"],
            "outstanding": float(Decimal(str(outstanding))),
            "invoice_counts": invoice_counts,
            "payments": [payment_dict(p) for p in data["payments"][:100]],
            "refunds": [refund_dict(r) for r in data["refunds"][:100]],
        }
    )
