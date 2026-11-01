from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, g, request
from sqlalchemy import func, or_

from ..auth.security import audit
from ..extensions import db
from ..models import (
    InventoryBatch,
    Medication,
    Prescription,
    StockMovement,
    Supplier,
)
from ..permissions.rbac import permission_required
from ..permissions.tenant import current_clinic, get_scoped_or_404
from ..utils.datetime_utils import clinic_today, iso, parse_date
from ..utils.errors import ConflictError, ValidationError
from ..utils.responses import ok, pagination_meta, parse_pagination
from ..utils.serializers import (
    inventory_dict,
    medication_dict,
    stock_movement_dict,
)
from .helpers import json_body

pharmacy_bp = Blueprint("pharmacy", __name__)

MOVEMENT_TYPES = {
    "purchase", "dispense", "adjustment", "return", "damage", "expired", "transfer",
}


def _decimal(value, field="Amount"):
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number.")
    if amount < 0:
        raise ValidationError(f"{field} cannot be negative.")
    return amount


def _int(value, field="Quantity"):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a whole number.")
    return number


def _medication_payload(medication: Medication, payload: dict, clinic_id: str) -> None:
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            raise ValidationError("Medicine name is required.")
        medication.name = name[:160]
    if "sku" in payload:
        sku = (payload.get("sku") or "").strip().upper()
        if not sku:
            raise ValidationError("SKU is required.")
        medication.sku = sku[:40]
    for field in ("generic_name", "strength", "manufacturer", "form", "category"):
        if field in payload:
            value = (payload.get(field) or "").strip()
            setattr(medication, field, value[:160] if value else None)
    if not medication.form:
        medication.form = "Tablet"
    if not medication.category:
        medication.category = "General"
    if "unit_price" in payload:
        medication.unit_price = _decimal(payload.get("unit_price"), "Unit price")
    if "reorder_level" in payload:
        level = _int(payload.get("reorder_level") or 0, "Reorder level")
        if level < 0:
            raise ValidationError("Reorder level cannot be negative.")
        medication.reorder_level = level
    if "is_active" in payload:
        medication.is_active = bool(payload.get("is_active"))


@pharmacy_bp.get("/api/pharmacy/medications")
@permission_required("pharmacy.view")
def list_medications():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args, default_per_page=50)
    query = Medication.query.filter(Medication.clinic_id == clinic.id)
    status = request.args.get("status", "active")
    if status == "active":
        query = query.filter(Medication.is_active.is_(True))
    elif status == "inactive":
        query = query.filter(Medication.is_active.is_(False))
    term = (request.args.get("q") or "").strip()
    if term:
        query = query.filter(
            or_(
                Medication.name.ilike(f"%{term}%"),
                Medication.generic_name.ilike(f"%{term}%"),
                Medication.sku.ilike(f"%{term}%"),
            )
        )
    category = request.args.get("category")
    if category:
        query = query.filter(Medication.category == category)
    query = query.order_by(Medication.name.asc())
    total = query.count()
    medications = query.offset((page - 1) * per_page).limit(per_page).all()
    data = [medication_dict(m) for m in medications]
    if request.args.get("low_stock") in ("1", "true"):
        data = [m for m in data if m["low_stock"]]
    return ok(data, pagination_meta(total, page, per_page))


@pharmacy_bp.post("/api/pharmacy/medications")
@permission_required("pharmacy.manage")
def create_medication():
    clinic = current_clinic()
    payload = json_body()
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValidationError("Medicine name is required.")
    sku = (payload.get("sku") or "").strip().upper()
    if not sku:
        raise ValidationError("SKU is required.")
    if Medication.query.filter_by(clinic_id=clinic.id, sku=sku).first():
        raise ConflictError("A medicine with this SKU already exists.")
    medication = Medication(clinic_id=clinic.id, name=name[:160], sku=sku[:40])
    _medication_payload(medication, payload, clinic.id)
    db.session.add(medication)
    db.session.flush()
    audit(
        "pharmacy.medication_created",
        "medication",
        medication.id,
        {"sku": medication.sku, "name": medication.name},
        clinic_id=clinic.id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"medication": medication_dict(medication)}, status=201)


@pharmacy_bp.get("/api/pharmacy/medications/<medication_id>")
@permission_required("pharmacy.view")
def get_medication(medication_id):
    medication = get_scoped_or_404(Medication, medication_id)
    data = medication_dict(medication)
    data["batches"] = [inventory_dict(b) for b in medication.batches]
    data["movements"] = [
        stock_movement_dict(m)
        for m in StockMovement.query.filter_by(
            clinic_id=medication.clinic_id, medication_id=medication.id
        )
        .order_by(StockMovement.created_at.desc())
        .limit(30)
        .all()
    ]
    return ok({"medication": data})


@pharmacy_bp.put("/api/pharmacy/medications/<medication_id>")
@permission_required("pharmacy.manage")
def update_medication(medication_id):
    medication = get_scoped_or_404(Medication, medication_id)
    payload = json_body()
    if "sku" in payload:
        sku = (payload.get("sku") or "").strip().upper()
        existing = Medication.query.filter(
            Medication.clinic_id == medication.clinic_id,
            Medication.sku == sku,
            Medication.id != medication.id,
        ).first()
        if existing:
            raise ConflictError("A medicine with this SKU already exists.")
    _medication_payload(medication, payload, medication.clinic_id)
    audit(
        "pharmacy.medication_updated",
        "medication",
        medication.id,
        {"sku": medication.sku},
        clinic_id=medication.clinic_id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"medication": medication_dict(medication)})


@pharmacy_bp.get("/api/pharmacy/inventory")
@permission_required("pharmacy.view")
def list_inventory():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args, default_per_page=50)
    query = InventoryBatch.query.join(Medication, InventoryBatch.medication_id == Medication.id).filter(
        InventoryBatch.clinic_id == clinic.id
    )
    term = (request.args.get("q") or "").strip()
    if term:
        query = query.filter(
            or_(
                Medication.name.ilike(f"%{term}%"),
                Medication.sku.ilike(f"%{term}%"),
                InventoryBatch.batch_number.ilike(f"%{term}%"),
            )
        )
    if request.args.get("expired") in ("1", "true"):
        query = query.filter(InventoryBatch.expiry_date < clinic_today(clinic))
    days = request.args.get("expiring_days")
    if days:
        try:
            days = int(days)
        except ValueError:
            raise ValidationError("Expiring days must be a number.")
        query = query.filter(
            InventoryBatch.expiry_date >= clinic_today(clinic),
            InventoryBatch.expiry_date <= clinic_today(clinic) + timedelta(days=days),
        )
    if request.args.get("in_stock") in ("1", "true"):
        query = query.filter(InventoryBatch.quantity > 0)
    query = query.order_by(InventoryBatch.expiry_date.asc())
    total = query.count()
    batches = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok([inventory_dict(b) for b in batches], pagination_meta(total, page, per_page))


@pharmacy_bp.post("/api/pharmacy/inventory")
@permission_required("pharmacy.manage")
def add_batch():
    clinic = current_clinic()
    payload = json_body()
    medication = get_scoped_or_404(Medication, payload.get("medication_id") or "")
    batch_number = (payload.get("batch_number") or "").strip()
    if not batch_number:
        raise ValidationError("Batch number is required.")
    if InventoryBatch.query.filter_by(
        medication_id=medication.id, batch_number=batch_number
    ).first():
        raise ConflictError("This batch number already exists for the medicine.")
    expiry = parse_date(payload.get("expiry_date"), "Expiry date")
    quantity = _int(payload.get("quantity") or 0, "Quantity")
    if quantity < 0:
        raise ValidationError("Quantity cannot be negative.")
    supplier = None
    if payload.get("supplier_id"):
        supplier = get_scoped_or_404(Supplier, payload.get("supplier_id"))
    batch = InventoryBatch(
        clinic_id=clinic.id,
        medication_id=medication.id,
        supplier_id=supplier.id if supplier else None,
        batch_number=batch_number[:80],
        expiry_date=expiry,
        quantity=quantity,
        purchase_price=_decimal(payload.get("purchase_price"), "Purchase price"),
        mrp=_decimal(payload.get("mrp"), "MRP"),
        created_by=g.user.id,
    )
    db.session.add(batch)
    db.session.flush()
    if quantity:
        db.session.add(
            StockMovement(
                clinic_id=clinic.id,
                medication_id=medication.id,
                inventory_id=batch.id,
                movement_type="purchase",
                quantity_delta=quantity,
                reference_type="inventory_batch",
                reference_id=batch.id,
                notes=f"Received batch {batch.batch_number}",
                created_by=g.user.id,
            )
        )
    audit(
        "pharmacy.batch_received",
        "inventory",
        batch.id,
        {"medication_id": medication.id, "quantity": quantity, "expiry": expiry.isoformat()},
        clinic_id=clinic.id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"batch": inventory_dict(batch)}, status=201)


@pharmacy_bp.put("/api/pharmacy/inventory/<batch_id>")
@permission_required("pharmacy.manage")
def update_batch(batch_id):
    batch = get_scoped_or_404(InventoryBatch, batch_id)
    payload = json_body()
    if "expiry_date" in payload:
        batch.expiry_date = parse_date(payload.get("expiry_date"), "Expiry date")
    for field in ("batch_number", "purchase_price", "mrp"):
        if field in payload:
            if field == "batch_number":
                value = (payload.get(field) or "").strip()
                if not value:
                    raise ValidationError("Batch number is required.")
                batch.batch_number = value[:80]
            else:
                setattr(batch, field, _decimal(payload.get(field), field.replace("_", " ").title()))
    if payload.get("supplier_id"):
        supplier = get_scoped_or_404(Supplier, payload.get("supplier_id"))
        batch.supplier_id = supplier.id
    audit(
        "pharmacy.batch_updated",
        "inventory",
        batch.id,
        clinic_id=batch.clinic_id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"batch": inventory_dict(batch)})


@pharmacy_bp.get("/api/pharmacy/suppliers")
@permission_required("pharmacy.view")
def list_suppliers():
    clinic = current_clinic()
    suppliers = (
        Supplier.query.filter_by(clinic_id=clinic.id)
        .order_by(Supplier.name.asc())
        .all()
    )
    return ok(
        [
            {
                "id": s.id,
                "name": s.name,
                "contact_person": s.contact_person,
                "phone": s.phone,
                "email": s.email,
                "gstin": s.gstin,
                "is_active": s.is_active,
            }
            for s in suppliers
        ]
    )


@pharmacy_bp.post("/api/pharmacy/suppliers")
@permission_required("pharmacy.manage")
def create_supplier():
    clinic = current_clinic()
    payload = json_body()
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValidationError("Supplier name is required.")
    supplier = Supplier(
        clinic_id=clinic.id,
        name=name[:160],
        contact_person=(payload.get("contact_person") or None),
        phone=(payload.get("phone") or None),
        email=(payload.get("email") or None),
        address=(payload.get("address") or None),
        gstin=(payload.get("gstin") or None),
    )
    db.session.add(supplier)
    audit("pharmacy.supplier_created", "supplier", supplier.id, clinic_id=clinic.id, user_id=g.user.id)
    db.session.commit()
    return ok({"supplier": {"id": supplier.id, "name": supplier.name}}, status=201)


@pharmacy_bp.put("/api/pharmacy/suppliers/<supplier_id>")
@permission_required("pharmacy.manage")
def update_supplier(supplier_id):
    supplier = get_scoped_or_404(Supplier, supplier_id)
    payload = json_body()
    for field in ("name", "contact_person", "phone", "email", "address", "gstin"):
        if field in payload:
            value = (payload.get(field) or "").strip()
            setattr(supplier, field, value or None)
    if "is_active" in payload:
        supplier.is_active = bool(payload.get("is_active"))
    audit("pharmacy.supplier_updated", "supplier", supplier.id, clinic_id=supplier.clinic_id, user_id=g.user.id)
    db.session.commit()
    return ok({"supplier": {"id": supplier.id, "name": supplier.name}})


@pharmacy_bp.get("/api/pharmacy/stock-movements")
@permission_required("pharmacy.view")
def list_movements():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args, default_per_page=50)
    query = StockMovement.query.filter(StockMovement.clinic_id == clinic.id)
    medication_id = request.args.get("medication_id")
    if medication_id:
        query = query.filter(StockMovement.medication_id == medication_id)
    movement_type = request.args.get("movement_type")
    if movement_type:
        query = query.filter(StockMovement.movement_type == movement_type)
    query = query.order_by(StockMovement.created_at.desc())
    total = query.count()
    movements = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok([stock_movement_dict(m) for m in movements], pagination_meta(total, page, per_page))


@pharmacy_bp.post("/api/pharmacy/stock-movements")
@permission_required("pharmacy.manage")
def adjust_stock():
    clinic = current_clinic()
    payload = json_body()
    medication = get_scoped_or_404(Medication, payload.get("medication_id") or "")
    movement_type = payload.get("movement_type") or "adjustment"
    if movement_type not in MOVEMENT_TYPES:
        raise ValidationError("Select a valid stock movement type.")
    delta = _int(payload.get("quantity_delta"), "Quantity change")
    if delta == 0:
        raise ValidationError("Quantity change cannot be zero.")
    batch = None
    if payload.get("inventory_id"):
        batch = get_scoped_or_404(InventoryBatch, payload.get("inventory_id"))
        if batch.medication_id != medication.id:
            raise ValidationError("The batch does not belong to this medicine.")
        if batch.quantity + delta < 0:
            raise ValidationError("This adjustment would make batch stock negative.")
        batch.quantity += delta
    else:
        stock = sum(b.quantity for b in medication.batches)
        if stock + delta < 0:
            raise ValidationError("This adjustment would make stock negative.")
    movement = StockMovement(
        clinic_id=clinic.id,
        medication_id=medication.id,
        inventory_id=batch.id if batch else None,
        movement_type=movement_type,
        quantity_delta=delta,
        reference_type=payload.get("reference_type"),
        reference_id=payload.get("reference_id"),
        notes=(payload.get("notes") or None),
        created_by=g.user.id,
    )
    db.session.add(movement)
    audit(
        "pharmacy.stock_adjusted",
        "medication",
        medication.id,
        {"delta": delta, "movement_type": movement_type},
        clinic_id=clinic.id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"movement": stock_movement_dict(movement)}, status=201)


@pharmacy_bp.post("/api/pharmacy/dispense")
@permission_required("pharmacy.dispense")
def dispense():
    clinic = current_clinic()
    payload = json_body()
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        raise ValidationError("Add at least one medicine to dispense.")
    if len(items) > 50:
        raise ValidationError("Too many items in one dispense action.")
    prescription = None
    if payload.get("prescription_id"):
        prescription = get_scoped_or_404(Prescription, payload["prescription_id"])
    patient_id = payload.get("patient_id") or (prescription.patient_id if prescription else None)

    prepared = []
    for item in items:
        medication = get_scoped_or_404(Medication, item.get("medication_id") or "")
        quantity = _int(item.get("quantity"), "Dispense quantity")
        if quantity <= 0:
            raise ValidationError("Dispense quantity must be greater than zero.")
        batches = (
            InventoryBatch.query.filter(
                InventoryBatch.clinic_id == clinic.id,
                InventoryBatch.medication_id == medication.id,
                InventoryBatch.quantity > 0,
                InventoryBatch.expiry_date >= clinic_today(clinic),
            )
            .order_by(InventoryBatch.expiry_date.asc())
            .with_for_update()
            .all()
        )
        available = sum(b.quantity for b in batches)
        if available < quantity:
            raise ValidationError(
                f"Only {available} unit(s) of {medication.name} are available in unexpired stock."
            )
        prepared.append((medication, quantity, batches))

    dispensed = []
    for medication, quantity, batches in prepared:
        remaining = quantity
        for batch in batches:
            if remaining <= 0:
                break
            take = min(batch.quantity, remaining)
            batch.quantity -= take
            remaining -= take
            db.session.add(
                StockMovement(
                    clinic_id=clinic.id,
                    medication_id=medication.id,
                    inventory_id=batch.id,
                    movement_type="dispense",
                    quantity_delta=-take,
                    reference_type="prescription" if prescription else "dispense",
                    reference_id=prescription.id if prescription else None,
                    notes=(payload.get("notes") or None),
                    created_by=g.user.id,
                )
            )
            dispensed.append(
                {
                    "medication_id": medication.id,
                    "medication": medication.name,
                    "batch_number": batch.batch_number,
                    "quantity": take,
                    "expiry_date": batch.expiry_date.isoformat(),
                }
            )
    audit(
        "pharmacy.dispensed",
        "prescription" if prescription else "dispense",
        prescription.id if prescription else None,
        {"patient_id": patient_id, "line_count": len(prepared), "quantity": sum(p[1] for p in prepared)},
        clinic_id=clinic.id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"dispensed": dispensed, "patient_id": patient_id}, status=201)


@pharmacy_bp.get("/api/pharmacy/alerts")
@permission_required("pharmacy.view")
def alerts():
    clinic = current_clinic()
    today = clinic_today(clinic)
    medications = Medication.query.filter_by(clinic_id=clinic.id, is_active=True).all()
    low_stock = [medication_dict(m) for m in medications if sum(b.quantity for b in m.batches) <= m.reorder_level]
    expiring = (
        InventoryBatch.query.filter(
            InventoryBatch.clinic_id == clinic.id,
            InventoryBatch.quantity > 0,
            InventoryBatch.expiry_date >= today,
            InventoryBatch.expiry_date <= today + timedelta(days=90),
        )
        .order_by(InventoryBatch.expiry_date.asc())
        .all()
    )
    expired = (
        InventoryBatch.query.filter(
            InventoryBatch.clinic_id == clinic.id,
            InventoryBatch.quantity > 0,
            InventoryBatch.expiry_date < today,
        )
        .order_by(InventoryBatch.expiry_date.asc())
        .all()
    )
    return ok(
        {
            "low_stock": low_stock,
            "expiring": [inventory_dict(b) for b in expiring],
            "expired": [inventory_dict(b) for b in expired],
            "counts": {
                "low_stock": len(low_stock),
                "expiring": len(expiring),
                "expired": len(expired),
            },
        }
    )
