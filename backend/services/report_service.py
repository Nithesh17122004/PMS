from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func

from ..extensions import db
from ..models import (
    Appointment,
    AppointmentStatus,
    Consultation,
    ConsultationStatus,
    DailyToken,
    Doctor,
    FollowUpPlan,
    FollowUpStatus,
    Invoice,
    LabOrder,
    Medication,
    Patient,
    Payment,
    Refund,
    StockMovement,
    TokenStatus,
)
from ..utils.datetime_utils import (
    as_utc,
    clinic_timezone,
    clinic_today,
    utc_bounds_for_local_range,
)

REPORT_TITLES = {
    "patients": "Patient Registration Report",
    "tokens": "Daily Token Report",
    "doctor_queue": "Doctor-wise Queue Report",
    "waiting_time": "Patient Waiting Time Report",
    "consultation_time": "Average Consultation Time Report",
    "followup_completion": "Follow-up Completion Report",
    "missed_followups": "Missed Follow-up Report",
    "appointments": "Appointment Report",
    "consultations": "Consultation Report",
    "revenue": "Revenue Report",
    "daily_collection": "Daily Collection Report",
    "inventory": "Inventory Report",
    "lab": "Laboratory Report",
    "cancelled_tokens": "Cancelled Token Report",
    "skipped_tokens": "Skipped Token Report",
}


def _range(clinic, start: date, end: date):
    return utc_bounds_for_local_range(clinic, start, end)


def _fmt(dt, clinic, with_time=True):
    if not dt:
        return "—"
    local = as_utc(dt).astimezone(clinic_timezone(clinic))
    return local.strftime("%d %b %Y %I:%M %p") if with_time else local.strftime("%d %b %Y")


def build_report(clinic, report_type: str, start: date, end: date, doctor_id: str | None = None) -> dict:
    if report_type not in REPORT_TITLES:
        raise ValueError("Unknown report type")
    start_utc, end_utc = _range(clinic, start, end)
    columns: list[str] = []
    keys: list[str] = []
    rows: list[list] = []
    summary: dict = {}
    title = REPORT_TITLES[report_type]
    date_label = f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"

    if report_type == "patients":
        query = Patient.query.filter(
            Patient.clinic_id == clinic.id,
            Patient.created_at >= start_utc,
            Patient.created_at < end_utc,
        ).order_by(Patient.created_at.asc())
        patients = query.all()
        columns = ["Patient ID", "Name", "Gender", "Age", "Phone", "Registered"]
        keys = ["patient_code", "name", "gender", "age", "phone", "registered"]
        rows = [
            [p.patient_code, p.full_name, p.gender.title(), p.age or "—", p.phone or "—", _fmt(p.created_at, clinic, False)]
            for p in patients
        ]
        summary = {"Total registrations": len(patients), "Active patients": sum(1 for p in patients if p.is_active)}

    elif report_type in ("tokens", "cancelled_tokens", "skipped_tokens"):
        status_filter = {
            "cancelled_tokens": [TokenStatus.CANCELLED],
            "skipped_tokens": [TokenStatus.SKIPPED],
        }.get(report_type)
        query = DailyToken.query.filter(
            DailyToken.clinic_id == clinic.id,
            DailyToken.token_date >= start,
            DailyToken.token_date <= end,
        )
        if status_filter:
            query = query.filter(DailyToken.status.in_(status_filter))
        if doctor_id:
            query = query.filter(DailyToken.doctor_id == doctor_id)
        tokens = query.order_by(DailyToken.token_date.asc(), DailyToken.token_number.asc()).all()
        columns = ["Date", "Token", "Doctor", "Patient ID", "Visit type", "Status", "Created", "Completed"]
        keys = ["date", "token", "doctor", "patient", "visit", "status", "created", "completed"]
        rows = [
            [
                t.token_date.strftime("%d %b %Y"), t.display_number, t.doctor.full_name,
                t.patient.patient_code, t.visit_type.replace("_", " ").title(), t.status.title(),
                _fmt(t.created_at, clinic), _fmt(t.completed_at, clinic),
            ]
            for t in tokens
        ]
        summary = {"Total tokens": len(tokens), "Completed": sum(1 for t in tokens if t.status == TokenStatus.COMPLETED)}
        if status_filter:
            summary["Filtered status"] = status_filter[0].title()

    elif report_type == "doctor_queue":
        doctors = Doctor.query.filter_by(clinic_id=clinic.id, is_active=True).all()
        columns = ["Doctor", "Specialty", "Waiting", "Called", "In consultation", "Completed", "Skipped", "Total"]
        keys = ["doctor", "specialty", "waiting", "called", "in_consult", "completed", "skipped", "total"]
        for doctor in doctors:
            tokens = DailyToken.query.filter_by(
                clinic_id=clinic.id, doctor_id=doctor.id, token_date=end
            ).all()
            counts = {status: 0 for status in TokenStatus.ALL}
            for token in tokens:
                counts[token.status] = counts.get(token.status, 0) + 1
            rows.append(
                [
                    doctor.full_name, doctor.specialization,
                    counts[TokenStatus.WAITING], counts[TokenStatus.CALLED] + counts[TokenStatus.RECALLED],
                    counts[TokenStatus.IN_CONSULTATION], counts[TokenStatus.COMPLETED],
                    counts[TokenStatus.SKIPPED], len(tokens),
                ]
            )
        summary = {"Report date": end.strftime("%d %b %Y"), "Doctors": len(doctors)}

    elif report_type == "waiting_time":
        query = DailyToken.query.filter(
            DailyToken.clinic_id == clinic.id,
            DailyToken.token_date >= start,
            DailyToken.token_date <= end,
            DailyToken.called_at.isnot(None),
        )
        if doctor_id:
            query = query.filter(DailyToken.doctor_id == doctor_id)
        tokens = query.order_by(DailyToken.token_date.asc()).all()
        columns = ["Date", "Token", "Doctor", "Patient ID", "Generated", "Called", "Wait (min)"]
        keys = ["date", "token", "doctor", "patient", "created", "called", "wait"]
        waits = []
        for token in tokens:
            wait = max(0, int((as_utc(token.called_at) - as_utc(token.created_at)).total_seconds() / 60))
            waits.append(wait)
            rows.append(
                [
                    token.token_date.strftime("%d %b %Y"), token.display_number, token.doctor.full_name,
                    token.patient.patient_code, _fmt(token.created_at, clinic), _fmt(token.called_at, clinic), wait,
                ]
            )
        summary = {
            "Patients measured": len(waits),
            "Average wait (min)": round(sum(waits) / len(waits), 1) if waits else 0,
            "Longest wait (min)": max(waits) if waits else 0,
        }

    elif report_type == "consultation_time":
        query = Consultation.query.filter(
            Consultation.clinic_id == clinic.id,
            Consultation.status == ConsultationStatus.COMPLETED,
            Consultation.completed_at >= start_utc,
            Consultation.completed_at < end_utc,
        )
        if doctor_id:
            query = query.filter(Consultation.doctor_id == doctor_id)
        consultations = query.order_by(Consultation.completed_at.asc()).all()
        columns = ["Date", "Consultation", "Doctor", "Patient ID", "Started", "Completed", "Minutes"]
        keys = ["date", "code", "doctor", "patient", "started", "completed", "minutes"]
        durations = []
        for consultation in consultations:
            minutes = (
                max(0, int((as_utc(consultation.completed_at) - as_utc(consultation.started_at)).total_seconds() / 60))
                if consultation.started_at
                else 0
            )
            durations.append(minutes)
            rows.append(
                [
                    consultation.completed_at.strftime("%d %b %Y"), consultation.consultation_code,
                    consultation.doctor.full_name, consultation.patient.patient_code,
                    _fmt(consultation.started_at, clinic), _fmt(consultation.completed_at, clinic), minutes,
                ]
            )
        summary = {
            "Consultations": len(durations),
            "Average duration (min)": round(sum(durations) / len(durations), 1) if durations else 0,
        }

    elif report_type in ("followup_completion", "missed_followups"):
        query = FollowUpPlan.query.filter(
            FollowUpPlan.clinic_id == clinic.id,
            FollowUpPlan.due_date >= start,
            FollowUpPlan.due_date <= end,
        )
        if doctor_id:
            query = query.filter(FollowUpPlan.doctor_id == doctor_id)
        if report_type == "missed_followups":
            query = query.filter(
                FollowUpPlan.status.in_([FollowUpStatus.MISSED, FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED]),
                FollowUpPlan.due_date < clinic_today(clinic),
            )
        plans = query.order_by(FollowUpPlan.due_date.asc()).all()
        columns = ["Due date", "Patient ID", "Patient", "Doctor", "Status", "Instructions"]
        keys = ["due", "patient_code", "patient", "doctor", "status", "instructions"]
        rows = [
            [
                p.due_date.strftime("%d %b %Y"), p.patient.patient_code, p.patient.full_name,
                p.doctor.full_name, p.status.title(), (p.instructions or "—")[:80],
            ]
            for p in plans
        ]
        completed = sum(1 for p in plans if p.status == FollowUpStatus.COMPLETED)
        summary = {
            "Follow-ups": len(plans),
            "Completed": completed,
            "Completion rate": f"{(completed / len(plans) * 100):.1f}%" if plans else "0%",
        }

    elif report_type == "appointments":
        query = Appointment.query.filter(
            Appointment.clinic_id == clinic.id,
            Appointment.appointment_date >= start,
            Appointment.appointment_date <= end,
        )
        if doctor_id:
            query = query.filter(Appointment.doctor_id == doctor_id)
        appointments = query.order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc()).all()
        columns = ["Date", "Time", "Code", "Patient ID", "Doctor", "Visit", "Status"]
        keys = ["date", "time", "code", "patient", "doctor", "visit", "status"]
        rows = [
            [
                a.appointment_date.strftime("%d %b %Y"), a.start_time.strftime("%I:%M %p"), a.appointment_code,
                a.patient.patient_code, a.doctor.full_name, a.visit_type.replace("_", " ").title(), a.status.title(),
            ]
            for a in appointments
        ]
        summary = {
            "Appointments": len(appointments),
            "Completed": sum(1 for a in appointments if a.status == AppointmentStatus.COMPLETED),
            "Cancelled": sum(1 for a in appointments if a.status == AppointmentStatus.CANCELLED),
            "No shows": sum(1 for a in appointments if a.status == AppointmentStatus.NO_SHOW),
        }

    elif report_type == "consultations":
        query = Consultation.query.filter(
            Consultation.clinic_id == clinic.id,
            Consultation.created_at >= start_utc,
            Consultation.created_at < end_utc,
        )
        if doctor_id:
            query = query.filter(Consultation.doctor_id == doctor_id)
        consultations = query.order_by(Consultation.created_at.asc()).all()
        columns = ["Date", "Code", "Patient ID", "Doctor", "Status", "Diagnosis"]
        keys = ["date", "code", "patient", "doctor", "status", "diagnosis"]
        rows = [
            [
                _fmt(c.created_at, clinic, False), c.consultation_code, c.patient.patient_code,
                c.doctor.full_name, c.status.title(), (c.diagnosis_summary or "—")[:100],
            ]
            for c in consultations
        ]
        summary = {"Consultations": len(consultations), "Completed": sum(1 for c in consultations if c.status == ConsultationStatus.COMPLETED)}

    elif report_type in ("revenue", "daily_collection"):
        payments = Payment.query.filter(
            Payment.clinic_id == clinic.id,
            Payment.paid_at >= start_utc,
            Payment.paid_at < end_utc,
        ).order_by(Payment.paid_at.asc()).all()
        refunds = Refund.query.filter(
            Refund.clinic_id == clinic.id,
            Refund.created_at >= start_utc,
            Refund.created_at < end_utc,
        ).all()
        if report_type == "revenue":
            columns = ["Date", "Receipt", "Invoice", "Patient ID", "Method", "Amount"]
            keys = ["date", "receipt", "invoice", "patient", "method", "amount"]
            rows = [
                [
                    _fmt(p.paid_at, clinic, False), p.payment_code, p.invoice.invoice_number,
                    p.patient.patient_code, p.method.replace("_", " ").title(), float(p.amount),
                ]
                for p in payments
            ]
            gross = sum((p.amount for p in payments), Decimal("0"))
            refunded = sum((r.amount for r in refunds), Decimal("0"))
            summary = {"Payments": len(payments), "Gross": float(gross), "Refunds": float(refunded), "Net": float(gross - refunded)}
        else:
            by_day = defaultdict(lambda: defaultdict(float))
            for payment in payments:
                day = as_utc(payment.paid_at).astimezone(clinic_timezone(clinic)).date()
                by_day[day][payment.method] += float(payment.amount)
            methods = sorted({p.method for p in payments})
            columns = ["Date"] + [m.replace("_", " ").title() for m in methods] + ["Total"]
            keys = ["date"] + methods + ["total"]
            for day in sorted(by_day):
                row = [day.strftime("%d %b %Y")]
                total = 0
                for method in methods:
                    amount = by_day[day][method]
                    row.append(round(amount, 2))
                    total += amount
                row.append(round(total, 2))
                rows.append(row)
            summary = {"Days": len(by_day), "Collected": round(sum(float(p.amount) for p in payments), 2)}

    elif report_type == "inventory":
        medications = Medication.query.filter_by(clinic_id=clinic.id, is_active=True).order_by(Medication.name).all()
        columns = ["SKU", "Medicine", "Category", "Stock", "Reorder level", "Low stock", "Nearest expiry"]
        keys = ["sku", "name", "category", "stock", "reorder", "low", "expiry"]
        for medication in medications:
            stock = sum(b.quantity for b in medication.batches)
            nearest = min((b.expiry_date for b in medication.batches if b.quantity > 0), default=None)
            rows.append(
                [
                    medication.sku, medication.name, medication.category, stock, medication.reorder_level,
                    "Yes" if stock <= medication.reorder_level else "No",
                    nearest.strftime("%d %b %Y") if nearest else "—",
                ]
            )
        summary = {"Medicines": len(medications), "Low stock items": sum(1 for m in medications if sum(b.quantity for b in m.batches) <= m.reorder_level)}

    elif report_type == "lab":
        orders = LabOrder.query.filter(
            LabOrder.clinic_id == clinic.id,
            LabOrder.created_at >= start_utc,
            LabOrder.created_at < end_utc,
        ).order_by(LabOrder.created_at.asc()).all()
        columns = ["Date", "Order", "Patient ID", "Doctor", "Tests", "Status", "Amount"]
        keys = ["date", "order", "patient", "doctor", "tests", "status", "amount"]
        rows = [
            [
                _fmt(o.created_at, clinic, False), o.order_number, o.patient.patient_code,
                o.doctor.full_name if o.doctor else "—", len(o.items), o.status.replace("_", " ").title(),
                float(o.total_amount),
            ]
            for o in orders
        ]
        summary = {"Orders": len(orders), "Completed": sum(1 for o in orders if o.status == "completed")}

    return {
        "type": report_type,
        "title": title,
        "columns": columns,
        "keys": keys,
        "rows": rows,
        "summary": summary,
        "date_label": date_label,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def report_to_csv(report: dict) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([report["title"]])
    writer.writerow([report["date_label"]])
    if report.get("summary"):
        for key, value in report["summary"].items():
            writer.writerow([key, value])
        writer.writerow([])
    writer.writerow(report["columns"])
    for row in report["rows"]:
        writer.writerow(row)
    return output.getvalue()
