from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func

from ..auth.security import audit
from ..extensions import db
from ..models import (
    Consultation,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    Patient,
    Payment,
    PaymentMethod,
    Refund,
    TokenStatus,
    VisitType,
)
from ..utils.datetime_utils import clinic_today, parse_date, utc_bounds_for_local_range
from ..utils.errors import ConflictError, NotFoundError, ValidationError
from .sequence_service import format_document_number, next_document_number

MONEY = Decimal("0.01")
ITEM_TYPES = {"consultation", "medicine", "service", "lab", "procedure", "other"}


def _money(value) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except Exception:
        raise ValidationError("Enter a valid amount.")


def _invoice_prefix(clinic) -> str:
    prefix = ((clinic.settings.invoice_prefix if clinic.settings else "INV") or "INV").strip().rstrip("-")
    return f"{prefix}-"


def create_invoice(
    clinic,
    actor,
    *,
    patient_id: str,
    items: list,
    discount_amount=0,
    tax_rate=None,
    notes=None,
    consultation_id=None,
    token_id=None,
    due_date=None,
    issue_now=True,
) -> Invoice:
    patient = Patient.query.filter_by(id=patient_id, clinic_id=clinic.id).first()
    if patient is None or not patient.is_active or patient.merged_into_id:
        raise NotFoundError("Patient not found or inactive.")
    if not isinstance(items, list) or not items:
        raise ValidationError("Add at least one invoice item.")
    if len(items) > 100:
        raise ValidationError("An invoice cannot contain more than 100 items.")
    if consultation_id:
        consultation = Consultation.query.filter_by(id=consultation_id, clinic_id=clinic.id).first()
        if consultation is None or consultation.patient_id != patient.id:
            raise ValidationError("Consultation does not belong to this patient.")
        existing = Invoice.query.filter_by(
            clinic_id=clinic.id, consultation_id=consultation_id, status=InvoiceStatus.PAID
        ).first()
        if existing:
            raise ConflictError("This consultation already has a paid invoice.")
    rate = _money(tax_rate if tax_rate is not None else (clinic.settings.tax_rate if clinic.settings else 0))
    if rate < 0 or rate > 100:
        raise ValidationError("Tax rate must be between 0 and 100.")

    prepared = []
    subtotal = Decimal("0")
    for raw in items:
        item_type = raw.get("item_type") or "service"
        if item_type not in ITEM_TYPES:
            raise ValidationError("Invalid invoice item type.")
        description = (raw.get("description") or "").strip()
        if not description:
            raise ValidationError("Every invoice item needs a description.")
        try:
            quantity = int(raw.get("quantity") or 1)
        except (TypeError, ValueError):
            raise ValidationError("Item quantity must be a whole number.")
        if quantity <= 0 or quantity > 10000:
            raise ValidationError("Item quantity must be greater than zero.")
        unit_price = _money(raw.get("unit_price"))
        if unit_price < 0:
            raise ValidationError("Item price cannot be negative.")
        amount = (unit_price * quantity).quantize(MONEY, rounding=ROUND_HALF_UP)
        subtotal += amount
        prepared.append((item_type, description[:255], quantity, unit_price, amount, raw.get("reference_id")))

    discount = _money(discount_amount)
    if discount < 0 or discount > subtotal:
        raise ValidationError("Discount cannot exceed the subtotal.")
    taxable = subtotal - discount
    tax_amount = (taxable * rate / Decimal("100")).quantize(MONEY, rounding=ROUND_HALF_UP)
    total = (taxable + tax_amount).quantize(MONEY, rounding=ROUND_HALF_UP)

    period = clinic_today(clinic).strftime("%Y%m")
    number = next_document_number(clinic.id, "invoice", period=period)
    invoice = Invoice(
        clinic_id=clinic.id,
        invoice_number=format_document_number(_invoice_prefix(clinic), number, width=5, period=period),
        patient_id=patient.id,
        consultation_id=consultation_id,
        token_id=token_id,
        status=(InvoiceStatus.UNPAID if total > 0 else InvoiceStatus.PAID)
        if issue_now
        else InvoiceStatus.DRAFT,
        subtotal=subtotal,
        discount_amount=discount,
        tax_rate=rate,
        tax_amount=tax_amount,
        total=total,
        amount_paid=Decimal("0"),
        balance=total,
        notes=(notes or None),
        due_date=parse_date(due_date, "Due date", required=False),
        issued_at=datetime.now(timezone.utc) if issue_now else None,
        created_by=actor.id,
    )
    db.session.add(invoice)
    db.session.flush()
    for item_type, description, quantity, unit_price, amount, reference_id in prepared:
        db.session.add(
            InvoiceItem(
                invoice_id=invoice.id,
                clinic_id=clinic.id,
                item_type=item_type,
                description=description,
                quantity=quantity,
                unit_price=unit_price,
                amount=amount,
                reference_id=reference_id,
            )
        )
    audit(
        "invoice.created",
        "invoice",
        invoice.id,
        {"total": str(total), "patient_id": patient.id, "item_count": len(prepared)},
        clinic_id=clinic.id,
        user_id=actor.id,
    )
    db.session.commit()
    return invoice


def create_consultation_invoice(consultation: Consultation, actor, include_followup_fee=False) -> Invoice:
    existing = Invoice.query.filter_by(
        clinic_id=consultation.clinic_id, consultation_id=consultation.id
    ).first()
    if existing:
        return existing
    token = consultation.token
    is_followup = token and token.visit_type == VisitType.FOLLOW_UP
    fee = consultation.doctor.follow_up_fee if is_followup else consultation.doctor.consultation_fee
    if include_followup_fee and is_followup and consultation.doctor.follow_up_fee == 0:
        fee = consultation.doctor.consultation_fee
    return create_invoice(
        consultation.doctor.clinic,
        actor,
        patient_id=consultation.patient_id,
        items=[
            {
                "item_type": "consultation",
                "description": (
                    f"Follow-up consultation — {consultation.doctor.full_name}"
                    if is_followup
                    else f"Consultation — {consultation.doctor.full_name}"
                ),
                "quantity": 1,
                "unit_price": fee,
                "reference_id": consultation.id,
            }
        ],
        consultation_id=consultation.id,
        token_id=token.id if token else None,
    )


def recalculate_invoice(invoice: Invoice) -> Invoice:
    net_paid = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.invoice_id == invoice.id, Payment.status != "voided"
    ).scalar()
    refunded = db.session.query(func.coalesce(func.sum(Refund.amount), 0)).filter(
        Refund.invoice_id == invoice.id, Refund.status == "completed"
    ).scalar()
    net_paid = Decimal(str(net_paid or 0))
    refunded = Decimal(str(refunded or 0))
    invoice.amount_paid = (net_paid - refunded).quantize(MONEY, rounding=ROUND_HALF_UP)
    invoice.balance = (invoice.total - invoice.amount_paid).quantize(MONEY, rounding=ROUND_HALF_UP)
    if invoice.status == InvoiceStatus.CANCELLED:
        return invoice
    if invoice.balance <= 0 and invoice.amount_paid > 0:
        invoice.status = InvoiceStatus.PAID
    elif refunded > 0 and invoice.amount_paid <= 0:
        invoice.status = InvoiceStatus.REFUNDED
    elif invoice.amount_paid > 0:
        invoice.status = InvoiceStatus.PARTIAL
    else:
        invoice.status = InvoiceStatus.UNPAID
    return invoice


def record_payment(invoice: Invoice, actor, amount, method: str, reference_number=None, notes=None) -> Payment:
    invoice = (
        Invoice.query.filter_by(id=invoice.id)
        .with_for_update()
        .first()
    )
    if invoice.status == InvoiceStatus.CANCELLED:
        raise ConflictError("Cannot record a payment against a cancelled invoice.")
    if invoice.balance <= 0:
        raise ConflictError("This invoice is already fully paid.")
    paid = _money(amount)
    if paid <= 0:
        raise ValidationError("Payment amount must be greater than zero.")
    if paid > invoice.balance:
        raise ValidationError(f"Payment cannot exceed the outstanding balance of {invoice.balance}.")
    if method not in PaymentMethod.ALL:
        raise ValidationError("Select a valid payment method.")
    number = next_document_number(invoice.clinic_id, "payment")
    payment = Payment(
        invoice_id=invoice.id,
        clinic_id=invoice.clinic_id,
        patient_id=invoice.patient_id,
        payment_code=format_document_number("PAY-", number, width=6),
        amount=paid,
        method=method,
        reference_number=(reference_number or None),
        notes=(notes or None),
        received_by=actor.id,
        paid_at=datetime.now(timezone.utc),
    )
    db.session.add(payment)
    db.session.flush()
    invoice.amount_paid = (invoice.amount_paid + paid).quantize(MONEY, rounding=ROUND_HALF_UP)
    invoice.balance = (invoice.total - invoice.amount_paid).quantize(MONEY, rounding=ROUND_HALF_UP)
    invoice.status = InvoiceStatus.PAID if invoice.balance <= 0 else InvoiceStatus.PARTIAL
    audit(
        "payment.recorded",
        "payment",
        payment.id,
        {"invoice_id": invoice.id, "amount": str(paid), "method": method},
        clinic_id=invoice.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return payment


def refund_payment(invoice: Invoice, payment: Payment, actor, amount, reason: str) -> Refund:
    if payment.invoice_id != invoice.id:
        raise ValidationError("Payment does not belong to this invoice.")
    already = db.session.query(func.coalesce(func.sum(Refund.amount), 0)).filter(
        Refund.payment_id == payment.id, Refund.status == "completed"
    ).scalar()
    already = Decimal(str(already or 0))
    refundable = payment.amount - already
    refund_amount = _money(amount)
    if refund_amount <= 0:
        raise ValidationError("Refund amount must be greater than zero.")
    if refund_amount > refundable:
        raise ValidationError(f"Refund cannot exceed the refundable amount of {refundable}.")
    if not reason or len(reason.strip()) < 3:
        raise ValidationError("A refund reason is required.")
    number = next_document_number(invoice.clinic_id, "refund")
    refund = Refund(
        payment_id=payment.id,
        invoice_id=invoice.id,
        clinic_id=invoice.clinic_id,
        refund_code=format_document_number("REF-", number, width=6),
        amount=refund_amount,
        reason=reason[:255],
        status="completed",
        approved_by=actor.id,
        created_by=actor.id,
    )
    db.session.add(refund)
    db.session.flush()
    if already + refund_amount >= payment.amount:
        payment.status = "refunded"
    else:
        payment.status = "partially_refunded"
    db.session.flush()
    recalculate_invoice(invoice)
    audit(
        "payment.refunded",
        "refund",
        refund.id,
        {"invoice_id": invoice.id, "payment_id": payment.id, "amount": str(refund_amount)},
        clinic_id=invoice.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return refund


def void_invoice(invoice: Invoice, actor, reason: str) -> Invoice:
    if invoice.status == InvoiceStatus.CANCELLED:
        raise ConflictError("This invoice is already cancelled.")
    if invoice.payments:
        raise ConflictError("Invoices with payments cannot be voided. Record a refund instead.")
    if not reason or len(reason.strip()) < 3:
        raise ValidationError("A void reason is required.")
    invoice.status = InvoiceStatus.CANCELLED
    invoice.voided_at = datetime.now(timezone.utc)
    invoice.voided_by = actor.id
    invoice.void_reason = reason[:255]
    audit(
        "invoice.voided",
        "invoice",
        invoice.id,
        {"reason": reason[:150]},
        clinic_id=invoice.clinic_id,
        user_id=actor.id,
    )
    db.session.commit()
    return invoice


def collection_summary(clinic, start: date, end: date) -> dict:
    start_utc, end_utc = utc_bounds_for_local_range(clinic, start, end)
    payments = (
        Payment.query.filter(
            Payment.clinic_id == clinic.id,
            Payment.paid_at >= start_utc,
            Payment.paid_at < end_utc,
        )
        .order_by(Payment.paid_at.desc())
        .all()
    )
    refunds = (
        Refund.query.filter(
            Refund.clinic_id == clinic.id,
            Refund.created_at >= start_utc,
            Refund.created_at < end_utc,
        ).all()
    )
    by_method = {}
    for payment in payments:
        by_method[payment.method] = by_method.get(payment.method, 0) + float(payment.amount)
    gross = sum((p.amount for p in payments), Decimal("0"))
    refunded = sum((r.amount for r in refunds), Decimal("0"))
    return {
        "payments": payments,
        "refunds": refunds,
        "gross": float(gross),
        "refunded": float(refunded),
        "net": float(gross - refunded),
        "by_method": by_method,
        "count": len(payments),
    }
