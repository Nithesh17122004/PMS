from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, g, request
from sqlalchemy import or_

from ..auth.security import audit
from ..extensions import db
from ..models import (
    Doctor,
    LabOrder,
    LabOrderItem,
    LabOrderStatus,
    LabResult,
    LabTest,
    Patient,
)
from ..permissions.rbac import permission_required
from ..permissions.tenant import current_clinic, get_scoped_or_404
from ..services.pdf_service import lab_report_pdf
from ..services.sequence_service import format_document_number, next_document_number
from ..utils.datetime_utils import clinic_today, parse_date
from ..utils.errors import ConflictError, NotFoundError, ValidationError
from ..utils.responses import ok, pagination_meta, parse_pagination
from ..utils.serializers import lab_order_dict, lab_test_dict
from ..utils.uploads import save_lab_attachment
from .helpers import json_body, pdf_response

lab_bp = Blueprint("lab", __name__)

INTERPRETATIONS = {"normal", "abnormal", "critical", "inconclusive"}


@lab_bp.get("/api/lab/tests")
@permission_required("lab.view")
def list_tests():
    clinic = current_clinic()
    query = LabTest.query.filter_by(clinic_id=clinic.id)
    if request.args.get("status", "active") == "active":
        query = query.filter(LabTest.is_active.is_(True))
    term = (request.args.get("q") or "").strip()
    if term:
        query = query.filter(
            or_(LabTest.name.ilike(f"%{term}%"), LabTest.code.ilike(f"%{term}%"))
        )
    return ok([lab_test_dict(t) for t in query.order_by(LabTest.name.asc()).all()])


@lab_bp.post("/api/lab/tests")
@permission_required("lab.manage")
def create_test():
    clinic = current_clinic()
    payload = json_body()
    name = (payload.get("name") or "").strip()
    code = (payload.get("code") or "").strip().upper()
    if not name or not code:
        raise ValidationError("Test name and code are required.")
    if LabTest.query.filter_by(clinic_id=clinic.id, code=code).first():
        raise ConflictError("A lab test with this code already exists.")
    test = LabTest(
        clinic_id=clinic.id,
        code=code[:30],
        name=name[:160],
        category=(payload.get("category") or "Pathology")[:80],
        sample_type=(payload.get("sample_type") or "Blood")[:60],
        price=payload.get("price") or 0,
        turnaround_hours=int(payload.get("turnaround_hours") or 24),
        reference_range=(payload.get("reference_range") or None),
        is_active=bool(payload.get("is_active", True)),
    )
    db.session.add(test)
    audit("lab.test_created", "lab_test", test.id, {"code": test.code}, clinic_id=clinic.id, user_id=g.user.id)
    db.session.commit()
    return ok({"test": lab_test_dict(test)}, status=201)


@lab_bp.put("/api/lab/tests/<test_id>")
@permission_required("lab.manage")
def update_test(test_id):
    test = get_scoped_or_404(LabTest, test_id)
    payload = json_body()
    if "code" in payload:
        code = (payload.get("code") or "").strip().upper()
        existing = LabTest.query.filter(
            LabTest.clinic_id == test.clinic_id, LabTest.code == code, LabTest.id != test.id
        ).first()
        if existing:
            raise ConflictError("A lab test with this code already exists.")
        test.code = code[:30]
    for field in ("name", "category", "sample_type", "reference_range"):
        if field in payload:
            value = (payload.get(field) or "").strip()
            setattr(test, field, value or None)
    if "price" in payload:
        test.price = payload.get("price") or 0
    if "turnaround_hours" in payload:
        test.turnaround_hours = max(1, int(payload.get("turnaround_hours") or 24))
    if "is_active" in payload:
        test.is_active = bool(payload.get("is_active"))
    audit("lab.test_updated", "lab_test", test.id, clinic_id=test.clinic_id, user_id=g.user.id)
    db.session.commit()
    return ok({"test": lab_test_dict(test)})


@lab_bp.get("/api/lab/orders")
@permission_required("lab.view")
def list_orders():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args, default_per_page=40)
    query = LabOrder.query.filter(LabOrder.clinic_id == clinic.id)
    status = request.args.get("status")
    if status and status != "all":
        query = query.filter(LabOrder.status == status)
    priority = request.args.get("priority")
    if priority:
        query = query.filter(LabOrder.priority == priority)
    patient_id = request.args.get("patient_id")
    if patient_id:
        query = query.filter(LabOrder.patient_id == patient_id)
    doctor_id = request.args.get("doctor_id")
    if doctor_id:
        query = query.filter(LabOrder.doctor_id == doctor_id)
    term = (request.args.get("q") or "").strip()
    if term:
        query = query.join(Patient, LabOrder.patient_id == Patient.id).filter(
            or_(
                LabOrder.order_number.ilike(f"%{term}%"),
                Patient.patient_code.ilike(f"%{term}%"),
                Patient.first_name.ilike(f"%{term}%"),
                Patient.last_name.ilike(f"%{term}%"),
            )
        )
    start = parse_date(request.args.get("start"), "Start date", required=False)
    end = parse_date(request.args.get("end"), "End date", required=False)
    if start:
        query = query.filter(LabOrder.ordered_at >= datetime.combine(start, datetime.min.time()).astimezone(timezone.utc))
    if end:
        query = query.filter(LabOrder.ordered_at <= datetime.combine(end, datetime.max.time()).astimezone(timezone.utc))
    query = query.order_by(LabOrder.ordered_at.desc())
    total = query.count()
    orders = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok([lab_order_dict(o) for o in orders], pagination_meta(total, page, per_page))


@lab_bp.post("/api/lab/orders")
@permission_required("lab.manage")
def create_order():
    clinic = current_clinic()
    payload = json_body()
    patient = get_scoped_or_404(Patient, payload.get("patient_id") or "")
    doctor = None
    if payload.get("doctor_id"):
        doctor = get_scoped_or_404(Doctor, payload.get("doctor_id"))
    test_ids = payload.get("test_ids") or []
    if not isinstance(test_ids, list) or not test_ids:
        raise ValidationError("Select at least one lab test.")
    if len(test_ids) > 40:
        raise ValidationError("A lab order cannot contain more than 40 tests.")
    tests = LabTest.query.filter(
        LabTest.clinic_id == clinic.id, LabTest.id.in_(test_ids), LabTest.is_active.is_(True)
    ).all()
    if len(tests) != len(set(test_ids)):
        raise ValidationError("One or more selected tests are unavailable.")
    period = clinic_today(clinic).strftime("%Y%m")
    number = next_document_number(clinic.id, "lab_order", period=period)
    order = LabOrder(
        clinic_id=clinic.id,
        order_number=format_document_number("LAB-", number, width=5, period=period),
        patient_id=patient.id,
        doctor_id=doctor.id if doctor else None,
        status=LabOrderStatus.ORDERED,
        priority=payload.get("priority") if payload.get("priority") in ("routine", "urgent", "stat") else "routine",
        notes=(payload.get("notes") or None),
        total_amount=sum(float(t.price) for t in tests),
        created_by=g.user.id,
    )
    db.session.add(order)
    db.session.flush()
    for test in tests:
        db.session.add(
            LabOrderItem(
                order_id=order.id,
                clinic_id=clinic.id,
                lab_test_id=test.id,
                price=test.price,
                status=LabOrderStatus.ORDERED,
            )
        )
    audit(
        "lab.order_created",
        "lab_order",
        order.id,
        {"order_number": order.order_number, "test_count": len(tests)},
        clinic_id=clinic.id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"order": lab_order_dict(order)}, status=201)


@lab_bp.get("/api/lab/orders/<order_id>")
@permission_required("lab.view")
def get_order(order_id):
    order = get_scoped_or_404(LabOrder, order_id)
    return ok({"order": lab_order_dict(order)})


@lab_bp.post("/api/lab/orders/<order_id>/status")
@permission_required("lab.manage")
def update_order_status(order_id):
    order = get_scoped_or_404(LabOrder, order_id)
    payload = json_body()
    target = payload.get("status")
    now = datetime.now(timezone.utc)
    if target == LabOrderStatus.SAMPLE_COLLECTED:
        if order.status != LabOrderStatus.ORDERED:
            raise ConflictError("Only newly ordered tests can be marked as collected.")
        order.status = target
        order.sample_collected_at = now
        for item in order.items:
            item.status = LabOrderStatus.SAMPLE_COLLECTED
    elif target == LabOrderStatus.PROCESSING:
        if order.status not in (LabOrderStatus.ORDERED, LabOrderStatus.SAMPLE_COLLECTED):
            raise ConflictError("This order cannot move to processing.")
        order.status = target
        if order.sample_collected_at is None:
            order.sample_collected_at = now
        for item in order.items:
            if item.status in (LabOrderStatus.ORDERED, LabOrderStatus.SAMPLE_COLLECTED):
                item.status = LabOrderStatus.PROCESSING
    elif target == LabOrderStatus.COMPLETED:
        if order.status == LabOrderStatus.CANCELLED:
            raise ConflictError("A cancelled order cannot be completed.")
        missing = [i.test.name for i in order.items if not i.result or not (i.result.result_value or "").strip()]
        if missing:
            raise ValidationError("Enter results for every test before completing: " + ", ".join(missing[:4]))
        order.status = target
        order.completed_at = now
        for item in order.items:
            item.status = LabOrderStatus.COMPLETED
    elif target == LabOrderStatus.CANCELLED:
        if order.status == LabOrderStatus.COMPLETED:
            raise ConflictError("Completed orders cannot be cancelled.")
        order.status = target
        for item in order.items:
            item.status = LabOrderStatus.CANCELLED
    else:
        raise ValidationError("Select a valid lab order status.")
    audit(
        "lab.order_status_changed",
        "lab_order",
        order.id,
        {"status": target},
        clinic_id=order.clinic_id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"order": lab_order_dict(order)})


@lab_bp.post("/api/lab/orders/<order_id>/results")
@permission_required("lab.results")
def enter_results(order_id):
    order = get_scoped_or_404(LabOrder, order_id)
    if order.status == LabOrderStatus.CANCELLED:
        raise ConflictError("Cannot enter results for a cancelled order.")
    payload = json_body()
    results = payload.get("results")
    if results is None and payload.get("item_id"):
        results = [payload]
    if not isinstance(results, list) or not results:
        raise ValidationError("Provide at least one result.")
    items = {item.id: item for item in order.items}
    entered = []
    for entry in results:
        item = items.get(entry.get("item_id"))
        if item is None:
            raise ValidationError("A result refers to an item that is not part of this order.")
        value = (entry.get("result_value") or "").strip()
        if not value:
            raise ValidationError("Result value is required.")
        interpretation = entry.get("interpretation") or "normal"
        if interpretation not in INTERPRETATIONS:
            raise ValidationError("Select a valid interpretation.")
        result = item.result
        if result is None:
            result = LabResult(
                lab_order_item_id=item.id,
                clinic_id=order.clinic_id,
                entered_by=g.user.id,
            )
            db.session.add(result)
        result.result_value = value[:160]
        result.unit = (entry.get("unit") or item.test.sample_type or "")[:40] or None
        result.reference_range = (entry.get("reference_range") or item.test.reference_range or "")[:160] or None
        result.interpretation = interpretation
        result.result_notes = (entry.get("result_notes") or None)
        result.entered_by = g.user.id
        result.verified_at = None
        result.verified_by = None
        item.status = LabOrderStatus.COMPLETED
        entered.append(result)
    if order.status in (LabOrderStatus.ORDERED, LabOrderStatus.SAMPLE_COLLECTED):
        order.status = LabOrderStatus.PROCESSING
        if order.sample_collected_at is None:
            order.sample_collected_at = datetime.now(timezone.utc)
    audit(
        "lab.results_entered",
        "lab_order",
        order.id,
        {"count": len(entered)},
        clinic_id=order.clinic_id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"order": lab_order_dict(order)})


@lab_bp.post("/api/lab/orders/<order_id>/verify")
@permission_required("lab.results")
def verify_results(order_id):
    order = get_scoped_or_404(LabOrder, order_id)
    now = datetime.now(timezone.utc)
    verified = 0
    for item in order.items:
        result = item.result
        if result and (result.result_value or "").strip() and result.verified_at is None:
            result.verified_by = g.user.id
            result.verified_at = now
            verified += 1
    if verified == 0:
        raise ConflictError("There are no unverified results to verify.")
    audit(
        "lab.results_verified",
        "lab_order",
        order.id,
        {"count": verified},
        clinic_id=order.clinic_id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"order": lab_order_dict(order), "verified": verified})


@lab_bp.post("/api/lab/orders/<order_id>/items/<item_id>/attachment")
@permission_required("lab.results")
def upload_attachment(order_id, item_id):
    order = get_scoped_or_404(LabOrder, order_id)
    item = LabOrderItem.query.filter_by(id=item_id, order_id=order.id).first()
    if item is None:
        raise NotFoundError("Lab order item not found.")
    file = request.files.get("file")
    relative_path, stored_name, size = save_lab_attachment(file, order.clinic_id)
    result = item.result
    if result is None:
        result = LabResult(
            lab_order_item_id=item.id,
            clinic_id=order.clinic_id,
            interpretation="inconclusive",
            entered_by=g.user.id,
        )
        db.session.add(result)
    result.attachment_path = relative_path
    audit(
        "lab.attachment_uploaded",
        "lab_order",
        order.id,
        {"item_id": item.id, "size": size},
        clinic_id=order.clinic_id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"attachment_path": relative_path, "size_bytes": size}, status=201)


@lab_bp.get("/api/lab/orders/<order_id>/pdf")
@permission_required("lab.view")
def download_report(order_id):
    order = get_scoped_or_404(LabOrder, order_id)
    buffer = lab_report_pdf(order)
    return pdf_response(buffer, f"lab-report-{order.order_number}.pdf")
