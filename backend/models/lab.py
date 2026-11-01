from __future__ import annotations

from ..extensions import db
from .base import ClinicScopedMixin, TimestampMixin, UUIDMixin, utcnow


class LabOrderStatus:
    ORDERED = "ordered"
    SAMPLE_COLLECTED = "sample_collected"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    ALL = [ORDERED, SAMPLE_COLLECTED, PROCESSING, COMPLETED, CANCELLED]


class LabTest(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "lab_tests"
    __table_args__ = (
        db.UniqueConstraint("clinic_id", "code", name="uq_labtest_clinic_code"),
        db.Index("ix_labtest_clinic_active", "clinic_id", "is_active"),
    )

    code = db.Column(db.String(30), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(80), nullable=False, default="Pathology")
    sample_type = db.Column(db.String(60), nullable=False, default="Blood")
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    turnaround_hours = db.Column(db.Integer, nullable=False, default=24)
    reference_range = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class LabOrder(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "lab_orders"
    __table_args__ = (
        db.UniqueConstraint("clinic_id", "order_number", name="uq_laborder_clinic_number"),
        db.Index("ix_laborder_clinic_status", "clinic_id", "status", "created_at"),
        db.Index("ix_laborder_clinic_patient", "clinic_id", "patient_id", "created_at"),
    )

    order_number = db.Column(db.String(30), nullable=False, index=True)
    patient_id = db.Column(
        db.String(36), db.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doctor_id = db.Column(
        db.String(36), db.ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True
    )
    status = db.Column(db.String(30), nullable=False, default=LabOrderStatus.ORDERED)
    priority = db.Column(db.String(20), nullable=False, default="routine")
    notes = db.Column(db.Text)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    payment_status = db.Column(db.String(20), nullable=False, default="pending")
    ordered_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    sample_collected_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    created_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))

    patient = db.relationship("Patient", foreign_keys=[patient_id])
    doctor = db.relationship("Doctor", foreign_keys=[doctor_id])
    items = db.relationship(
        "LabOrderItem", back_populates="order", cascade="all, delete-orphan",
        order_by="LabOrderItem.created_at",
    )

    def __repr__(self) -> str:
        return f"<LabOrder {self.order_number}>"


class LabOrderItem(UUIDMixin, db.Model):
    __tablename__ = "lab_order_items"
    __table_args__ = (db.Index("ix_labitem_order", "order_id"),)

    order_id = db.Column(
        db.String(36), db.ForeignKey("lab_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clinic_id = db.Column(
        db.String(36), db.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )
    lab_test_id = db.Column(
        db.String(36), db.ForeignKey("lab_tests.id", ondelete="RESTRICT"), nullable=False
    )
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    status = db.Column(db.String(30), nullable=False, default=LabOrderStatus.ORDERED)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    order = db.relationship("LabOrder", back_populates="items")
    test = db.relationship("LabTest", foreign_keys=[lab_test_id])
    result = db.relationship(
        "LabResult", back_populates="item", cascade="all, delete-orphan", uselist=False
    )


class LabResult(UUIDMixin, db.Model):
    __tablename__ = "lab_results"
    __table_args__ = (
        db.UniqueConstraint("lab_order_item_id", name="uq_labresult_item"),
        db.Index("ix_labresult_clinic_created", "clinic_id", "created_at"),
    )

    lab_order_item_id = db.Column(
        db.String(36),
        db.ForeignKey("lab_order_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clinic_id = db.Column(
        db.String(36), db.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )
    result_value = db.Column(db.String(160))
    unit = db.Column(db.String(40))
    reference_range = db.Column(db.String(160))
    interpretation = db.Column(db.String(40), nullable=False, default="normal")
    result_notes = db.Column(db.Text)
    attachment_path = db.Column(db.String(255))
    entered_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    verified_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    verified_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    item = db.relationship("LabOrderItem", back_populates="result")
    enterer = db.relationship("User", foreign_keys=[entered_by])
    verifier = db.relationship("User", foreign_keys=[verified_by])
