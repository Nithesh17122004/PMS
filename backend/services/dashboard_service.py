from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, or_

from ..extensions import db
from ..models import (
    Appointment,
    AppointmentStatus,
    Clinic,
    Consultation,
    ConsultationStatus,
    DailyToken,
    Doctor,
    DoctorLeave,
    FollowUpPlan,
    FollowUpStatus,
    Invoice,
    InvoiceStatus,
    Patient,
    Payment,
    Refund,
    TokenStatus,
)
from ..utils.datetime_utils import (
    as_utc,
    clinic_timezone,
    clinic_today,
    utc_bounds_for_local_day,
    utc_bounds_for_local_range,
)

PAID_INVOICE_STATUSES = (InvoiceStatus.PAID, InvoiceStatus.PARTIAL)


def _money(value) -> float:
    return float(Decimal(str(value or 0)))


def _sum_payments(clinic, start, end, doctor_id=None):
    payments_q = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.clinic_id == clinic.id,
        Payment.paid_at >= start,
        Payment.paid_at < end,
    )
    refunds_q = db.session.query(func.coalesce(func.sum(Refund.amount), 0)).filter(
        Refund.clinic_id == clinic.id,
        Refund.created_at >= start,
        Refund.created_at < end,
    )
    if doctor_id:
        payments_q = payments_q.join(Invoice, Payment.invoice_id == Invoice.id).join(
            Consultation, Invoice.consultation_id == Consultation.id
        ).filter(Consultation.doctor_id == doctor_id)
        refunds_q = refunds_q.join(Invoice, Refund.invoice_id == Invoice.id).join(
            Consultation, Invoice.consultation_id == Consultation.id
        ).filter(Consultation.doctor_id == doctor_id)
    gross = Decimal(str(payments_q.scalar() or 0))
    refunded = Decimal(str(refunds_q.scalar() or 0))
    return float(gross - refunded)


def _doctor_filter(query, model, doctor_id):
    if doctor_id:
        return query.filter(model.doctor_id == doctor_id)
    return query


def available_doctors(clinic, day=None):
    day = day or clinic_today(clinic)
    doctors = Doctor.query.filter_by(clinic_id=clinic.id, is_active=True, is_available=True).all()
    leave_ids = {
        row[0]
        for row in db.session.query(DoctorLeave.doctor_id)
        .filter(
            DoctorLeave.clinic_id == clinic.id,
            DoctorLeave.status == "approved",
            DoctorLeave.start_date <= day,
            DoctorLeave.end_date >= day,
        )
        .all()
    }
    result = []
    for doctor in doctors:
        if doctor.id in leave_ids:
            continue
        has_schedule = any(s.is_active and s.weekday == day.weekday() for s in doctor.schedules)
        if has_schedule:
            result.append(doctor)
    return result


def dashboard_data(clinic, user=None, doctor_id=None) -> dict:
    today = clinic_today(clinic)
    day_start, day_end = utc_bounds_for_local_day(clinic, today)
    month_start_local = today.replace(day=1)
    month_start, _ = utc_bounds_for_local_day(clinic, month_start_local)
    _, month_end = utc_bounds_for_local_day(
        clinic, (month_start_local.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    )

    patient_query = Patient.query.filter(
        Patient.clinic_id == clinic.id, Patient.is_active.is_(True), Patient.merged_into_id.is_(None)
    )
    total_patients = patient_query.count()
    new_patients_today = patient_query.filter(
        Patient.created_at >= day_start, Patient.created_at < day_end
    ).count()

    token_base = DailyToken.query.filter(
        DailyToken.clinic_id == clinic.id, DailyToken.token_date == today
    )
    if doctor_id:
        token_base = token_base.filter(DailyToken.doctor_id == doctor_id)
    token_counts = {
        status: token_base.filter(DailyToken.status == status).count() for status in TokenStatus.ALL
    }
    total_tokens = token_base.count()

    appointments_base = Appointment.query.filter(
        Appointment.clinic_id == clinic.id, Appointment.appointment_date == today
    )
    if doctor_id:
        appointments_base = appointments_base.filter(Appointment.doctor_id == doctor_id)
    todays_appointments = appointments_base.count()
    appointment_status_counts = {
        status: appointments_base.filter(Appointment.status == status).count()
        for status in AppointmentStatus.ALL
    }

    followup_base = FollowUpPlan.query.filter(FollowUpPlan.clinic_id == clinic.id)
    if doctor_id:
        followup_base = followup_base.filter(FollowUpPlan.doctor_id == doctor_id)
    followups_today = followup_base.filter(
        FollowUpPlan.due_date == today,
        FollowUpPlan.status.in_(
            [FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED, FollowUpStatus.ARRIVED]
        ),
    ).count()
    overdue_followups = followup_base.filter(
        FollowUpPlan.due_date < today,
        FollowUpPlan.status.in_([FollowUpStatus.UPCOMING, FollowUpStatus.CONFIRMED]),
    ).count()
    followup_status_counts = {
        status: followup_base.filter(FollowUpPlan.status == status).count()
        for status in FollowUpStatus.ALL
    }

    completed_consultations = token_counts.get(TokenStatus.COMPLETED, 0)
    if doctor_id:
        completed_consultations = Consultation.query.filter(
            Consultation.clinic_id == clinic.id,
            Consultation.doctor_id == doctor_id,
            Consultation.status == ConsultationStatus.COMPLETED,
            Consultation.completed_at >= day_start,
            Consultation.completed_at < day_end,
        ).count()

    pending_payments_q = Invoice.query.filter(
        Invoice.clinic_id == clinic.id,
        Invoice.status.in_([InvoiceStatus.UNPAID, InvoiceStatus.PARTIAL]),
        Invoice.balance > 0,
    )
    if doctor_id:
        pending_payments_q = pending_payments_q.join(
            Consultation, Invoice.consultation_id == Consultation.id
        ).filter(Consultation.doctor_id == doctor_id)
    pending_subquery = pending_payments_q.with_entities(Invoice.balance).subquery()
    pending_balance = db.session.query(
        func.coalesce(func.sum(pending_subquery.c.balance), 0)
    ).scalar()

    daily_revenue = _sum_payments(clinic, day_start, day_end, doctor_id)
    monthly_revenue = _sum_payments(clinic, month_start, month_end, doctor_id)

    # Charts: last 14 local days.
    start_day = today - timedelta(days=13)
    chart_start, chart_end = utc_bounds_for_local_range(clinic, start_day, today)
    tz = clinic_timezone(clinic)
    visit_rows = (
        db.session.query(DailyToken.token_date, func.count(DailyToken.id))
        .filter(
            DailyToken.clinic_id == clinic.id,
            DailyToken.token_date >= start_day,
            DailyToken.token_date <= today,
            *((DailyToken.doctor_id == doctor_id,) if doctor_id else ()),
        )
        .group_by(DailyToken.token_date)
        .all()
    )
    visits_by_date = {row[0]: row[1] for row in visit_rows}
    daily_visits = [
        {"date": (start_day + timedelta(days=i)).isoformat(), "count": visits_by_date.get(start_day + timedelta(days=i), 0)}
        for i in range(14)
    ]

    reg_rows = patient_query.filter(
        Patient.created_at >= chart_start, Patient.created_at < chart_end
    ).all()
    reg_by_date = defaultdict(int)
    for patient in reg_rows:
        created = as_utc(patient.created_at).astimezone(tz)
        reg_by_date[created.date()] += 1
    monthly_registrations = [
        {
            "date": (start_day + timedelta(days=i)).isoformat(),
            "count": reg_by_date.get(start_day + timedelta(days=i), 0),
        }
        for i in range(14)
    ]

    payment_rows = (
        Payment.query.filter(
            Payment.clinic_id == clinic.id,
            Payment.paid_at >= chart_start,
            Payment.paid_at < chart_end,
        ).all()
    )
    refund_rows = (
        Refund.query.filter(
            Refund.clinic_id == clinic.id,
            Refund.created_at >= chart_start,
            Refund.created_at < chart_end,
        ).all()
    )
    revenue_by_date = defaultdict(float)
    for payment in payment_rows:
        local_day = as_utc(payment.paid_at).astimezone(tz).date()
        revenue_by_date[local_day] += float(payment.amount)
    for refund in refund_rows:
        local_day = as_utc(refund.created_at).astimezone(tz).date()
        revenue_by_date[local_day] -= float(refund.amount)
    daily_revenue_chart = [
        {
            "date": (start_day + timedelta(days=i)).isoformat(),
            "amount": round(revenue_by_date.get(start_day + timedelta(days=i), 0), 2),
        }
        for i in range(14)
    ]

    doctor_consultations = (
        db.session.query(Doctor.id, Doctor.full_name, Doctor.specialization, func.count(DailyToken.id))
        .join(DailyToken, DailyToken.doctor_id == Doctor.id)
        .filter(
            DailyToken.clinic_id == clinic.id,
            DailyToken.token_date == today,
            DailyToken.status == TokenStatus.COMPLETED,
        )
        .group_by(Doctor.id, Doctor.full_name, Doctor.specialization)
        .order_by(func.count(DailyToken.id).desc())
        .all()
    )

    queue_stats = [
        {"status": status, "count": token_counts.get(status, 0)} for status in TokenStatus.ALL
    ]
    completion_chart = [
        {"status": status, "count": appointment_status_counts.get(status, 0)}
        for status in AppointmentStatus.ALL
    ]
    followup_chart = [
        {"status": status, "count": followup_status_counts.get(status, 0)}
        for status in FollowUpStatus.ALL
    ]

    waits = []
    consults = []
    for token in token_base.filter(DailyToken.called_at.isnot(None)).all():
        if token.created_at and token.called_at:
            waits.append(max(0, (as_utc(token.called_at) - as_utc(token.created_at)).total_seconds() / 60))
    consult_q = Consultation.query.filter(
        Consultation.clinic_id == clinic.id,
        Consultation.status == ConsultationStatus.COMPLETED,
        Consultation.completed_at >= day_start,
        Consultation.completed_at < day_end,
    )
    if doctor_id:
        consult_q = consult_q.filter(Consultation.doctor_id == doctor_id)
    for consultation in consult_q.all():
        if consultation.started_at and consultation.completed_at:
            consults.append(
                max(0, (as_utc(consultation.completed_at) - as_utc(consultation.started_at)).total_seconds() / 60)
            )

    doctors_available = available_doctors(clinic, today)
    return {
        "date": today.isoformat(),
        "scope": {"doctor_id": doctor_id},
        "stats": {
            "total_patients": total_patients,
            "new_patients_today": new_patients_today,
            "todays_appointments": todays_appointments,
            "followups_today": followups_today,
            "total_tokens": total_tokens,
            "waiting": token_counts.get(TokenStatus.WAITING, 0),
            "in_consultation": token_counts.get(TokenStatus.IN_CONSULTATION, 0),
            "completed_consultations": completed_consultations,
            "skipped_tokens": token_counts.get(TokenStatus.SKIPPED, 0),
            "overdue_followups": overdue_followups,
            "available_doctors": len(doctors_available),
            "daily_revenue": round(daily_revenue, 2),
            "monthly_revenue": round(monthly_revenue, 2),
            "pending_payments": _money(pending_balance),
            "avg_wait_minutes": round(sum(waits) / len(waits), 1) if waits else 0,
            "avg_consult_minutes": round(sum(consults) / len(consults), 1) if consults else 0,
            "called": token_counts.get(TokenStatus.CALLED, 0) + token_counts.get(TokenStatus.RECALLED, 0),
        },
        "charts": {
            "daily_visits": daily_visits,
            "monthly_registrations": monthly_registrations,
            "doctor_consultations": [
                {"doctor_id": row[0], "doctor": row[1], "specialization": row[2], "count": row[3]}
                for row in doctor_consultations
            ],
            "daily_revenue": daily_revenue_chart,
            "appointment_completion": completion_chart,
            "followup_completion": followup_chart,
            "token_queue": queue_stats,
        },
        "doctors_available": [
            {"id": d.id, "full_name": d.full_name, "specialization": d.specialization, "room": d.room_number}
            for d in doctors_available
        ],
    }


def platform_data() -> dict:
    clinics = Clinic.query.order_by(Clinic.created_at.desc()).all()
    active = [c for c in clinics if c.is_active]
    total_patients = Patient.query.count()
    total_consultations = Consultation.query.count()
    total_revenue = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).scalar()
    refunds = db.session.query(func.coalesce(func.sum(Refund.amount), 0)).scalar()
    today = date.today()
    return {
        "stats": {
            "clinics": len(clinics),
            "active_clinics": len(active),
            "patients": total_patients,
            "consultations": total_consultations,
            "revenue": float(Decimal(str(total_revenue or 0)) - Decimal(str(refunds or 0))),
            "demo_clinics": len([c for c in clinics if c.is_demo]),
        },
        "clinics": [
            {
                "id": c.id,
                "name": c.name,
                "slug": c.slug,
                "city": c.city,
                "is_active": c.is_active,
                "is_demo": c.is_demo,
                "plan": c.plan,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "patient_count": Patient.query.filter_by(clinic_id=c.id).count(),
            }
            for c in clinics
        ],
    }
