from __future__ import annotations

from ..extensions import db
from .base import ClinicScopedMixin, TimestampMixin, UUIDMixin, utcnow


class Supplier(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "suppliers"
    __table_args__ = (db.Index("ix_supplier_clinic", "clinic_id", "name"),)

    name = db.Column(db.String(160), nullable=False)
    contact_person = db.Column(db.String(120))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(160))
    address = db.Column(db.Text)
    gstin = db.Column(db.String(30))
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Medication(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "medications"
    __table_args__ = (
        db.UniqueConstraint("clinic_id", "sku", name="uq_medication_clinic_sku"),
        db.Index("ix_medication_clinic_name", "clinic_id", "name"),
        db.Index("ix_medication_clinic_active", "clinic_id", "is_active"),
    )

    sku = db.Column(db.String(40), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    generic_name = db.Column(db.String(160))
    category = db.Column(db.String(80), nullable=False, default="General")
    form = db.Column(db.String(40), nullable=False, default="Tablet")
    strength = db.Column(db.String(60))
    manufacturer = db.Column(db.String(160))
    unit_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    reorder_level = db.Column(db.Integer, nullable=False, default=10)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    batches = db.relationship(
        "InventoryBatch", back_populates="medication", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Medication {self.name}>"


class InventoryBatch(UUIDMixin, TimestampMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "inventory"
    __table_args__ = (
        db.UniqueConstraint("medication_id", "batch_number", name="uq_inventory_med_batch"),
        db.CheckConstraint("quantity >= 0", name="ck_inventory_quantity_non_negative"),
        db.Index("ix_inventory_clinic_expiry", "clinic_id", "expiry_date"),
    )

    medication_id = db.Column(
        db.String(36), db.ForeignKey("medications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id = db.Column(
        db.String(36), db.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    batch_number = db.Column(db.String(80), nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    purchase_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    mrp = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    received_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    created_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))

    medication = db.relationship("Medication", back_populates="batches")
    supplier = db.relationship("Supplier", foreign_keys=[supplier_id])


class StockMovement(UUIDMixin, ClinicScopedMixin, db.Model):
    __tablename__ = "stock_movements"
    __table_args__ = (
        db.Index("ix_stock_clinic_created", "clinic_id", "created_at"),
        db.Index("ix_stock_medication", "medication_id", "created_at"),
    )

    medication_id = db.Column(
        db.String(36), db.ForeignKey("medications.id", ondelete="RESTRICT"), nullable=False
    )
    inventory_id = db.Column(
        db.String(36), db.ForeignKey("inventory.id", ondelete="SET NULL"), nullable=True
    )
    movement_type = db.Column(db.String(30), nullable=False)
    quantity_delta = db.Column(db.Integer, nullable=False)
    reference_type = db.Column(db.String(40))
    reference_id = db.Column(db.String(36))
    notes = db.Column(db.String(255))
    created_by = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    medication = db.relationship("Medication", foreign_keys=[medication_id])
    batch = db.relationship("InventoryBatch", foreign_keys=[inventory_id])
    creator = db.relationship("User", foreign_keys=[created_by])
