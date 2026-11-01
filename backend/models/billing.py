from __future__ import annotations

from ..extensions import db
from .base import ClinicScopedMixin, TimestampMixin, UUIDMixin, utcnow


class InvoiceStatus:
    DRAFT = "draft"
    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

    ALL = [DRAFT, UNPAID, PARTIAL, PAID, CANCELLED, REFUNDED]


class Invoice(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "invoices"
    __table_args__ = (
        db.UniqueConstraint("clinic_id", "invoice_number", name="uq_invoice_clinic_number"),
        db.Index("ix_invoice_clinic_patient", "clinic_id", "patient_id", "created_at"),
        db.Index("ix_invoice_clinic_status", "clinic_id", "status", "created_at"),
        db.Index("ix_invoice_clinic_date", "clinic_id", "issued_at"),
    )

    invoice_number = db.Column(db.String(30), nullable=False, index=True)
    patient_id = db.Column(
        db.String(36), db.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    consultation_id = db.Column(
        db.String(36), db.ForeignKey("consultations.id", ondelete="SET NULL")
    )
    token_id = db.Column(db.String(36), db.ForeignKey("daily_tokens.id", ondelete="SET NULL"))
    status = db.Column(db.String(20), nullable=False, default=InvoiceStatus.UNPAID)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount_reason = db.Column(db.String(255))
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    amount_paid = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    notes = db.Column(db.Text)
    due_date = db.Column(db.Date)
    issued_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    created_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    voided_at = db.Column(db.DateTime(timezone=True))
    voided_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    void_reason = db.Column(db.String(255))

    patient = db.relationship("Patient", foreign_keys=[patient_id])
    consultation = db.relationship("Consultation", foreign_keys=[consultation_id])
    token = db.relationship("DailyToken", foreign_keys=[token_id])
    items = db.relationship(
        "InvoiceItem", back_populates="invoice", cascade="all, delete-orphan",
        order_by="InvoiceItem.created_at",
    )
    payments = db.relationship(
        "Payment", back_populates="invoice", cascade="all, delete-orphan",
        order_by="Payment.paid_at",
    )
    refunds = db.relationship("Refund", back_populates="invoice", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Invoice {self.invoice_number}>"


class InvoiceItem(UUIDMixin, db.Model):
    __tablename__ = "invoice_items"

    invoice_id = db.Column(
        db.String(36), db.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clinic_id = db.Column(
        db.String(36), db.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )
    item_type = db.Column(db.String(30), nullable=False, default="service")
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    reference_id = db.Column(db.String(36))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    invoice = db.relationship("Invoice", back_populates="items")


class PaymentMethod:
    CASH = "cash"
    CARD = "card"
    UPI = "upi"
    BANK = "bank_transfer"
    INSURANCE = "insurance"
    OTHER = "other"

    ALL = [CASH, CARD, UPI, BANK, INSURANCE, OTHER]


class Payment(UUIDMixin, db.Model):
    __tablename__ = "payments"
    __table_args__ = (
        db.UniqueConstraint("clinic_id", "payment_code", name="uq_payment_clinic_code"),
        db.Index("ix_payment_clinic_paid", "clinic_id", "paid_at"),
        db.Index("ix_payment_invoice", "invoice_id", "paid_at"),
    )

    invoice_id = db.Column(
        db.String(36), db.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clinic_id = db.Column(
        db.String(36), db.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )
    patient_id = db.Column(
        db.String(36), db.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    payment_code = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    method = db.Column(db.String(30), nullable=False, default=PaymentMethod.CASH)
    reference_number = db.Column(db.String(120))
    notes = db.Column(db.String(255))
    status = db.Column(db.String(20), nullable=False, default="completed")
    received_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    paid_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    invoice = db.relationship("Invoice", back_populates="payments")
    patient = db.relationship("Patient", foreign_keys=[patient_id])
    receiver = db.relationship("User", foreign_keys=[received_by])
    refunds = db.relationship("Refund", back_populates="payment")


class Refund(UUIDMixin, db.Model):
    __tablename__ = "refunds"
    __table_args__ = (
        db.UniqueConstraint("clinic_id", "refund_code", name="uq_refund_clinic_code"),
    )

    payment_id = db.Column(
        db.String(36), db.ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id = db.Column(
        db.String(36), db.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clinic_id = db.Column(
        db.String(36), db.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )
    refund_code = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="completed")
    approved_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    created_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    payment = db.relationship("Payment", back_populates="refunds")
    invoice = db.relationship("Invoice", back_populates="refunds")
    approver = db.relationship("User", foreign_keys=[approved_by])
