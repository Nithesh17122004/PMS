"""Consistent JSON serializers. Keep PHI out of logs, not out of authorized APIs."""
from __future__ import annotations

from datetime import date, datetime, time

from ..extensions import db
from ..models import Clinic
from ..utils.crypto import mask_email, mask_phone
from ..utils.datetime_utils import as_utc, clinic_now, clinic_today


def iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        value = as_utc(value)
        return value.isoformat() if value else None
    if isinstance(value, (date, time)):
        return value.isoformat()
    return value


def num(value):
    return float(value) if value is not None else 0.0


def user_brief(user):
    if not user:
        return None
    return {
        "id": user.id,
        "full_name": user.full_name,
        "initials": user.initials,
        "email": user.email,
        "role": user.role.name if user.role else None,
        "role_slug": user.role.slug if user.role else None,
        "avatar_color": user.avatar_color,
    }


def clinic_brief(clinic):
    if not clinic:
        return None
    return {
        "id": clinic.id,
        "name": clinic.name,
        "slug": clinic.slug,
        "logo_url": f"/api/public/clinics/{clinic.slug}/logo" if clinic.logo_path else None,
        "is_demo": clinic.is_demo,
        "timezone": clinic.settings.timezone if clinic.settings else "Asia/Kolkata",
        "currency": clinic.settings.currency if clinic.settings else "INR",
    }


def settings_dict(settings):
    if not settings:
        return None
    return {
        "timezone": settings.timezone,
        "currency": settings.currency,
        "locale": settings.locale,
        "tax_rate": num(settings.tax_rate),
        "tax_label": settings.tax_label,
        "invoice_prefix": settings.invoice_prefix,
        "patient_prefix": settings.patient_prefix,
        "token_prefix": settings.token_prefix,
        "token_mode": settings.token_mode,
        "working_days": settings.working_days,
        "open_time": iso(settings.open_time),
        "close_time": iso(settings.close_time),
        "slot_minutes": settings.slot_minutes,
        "consultation_fee_default": num(settings.consultation_fee_default),
        "follow_up_fee_default": num(settings.follow_up_fee_default),
        "reminder_email_enabled": settings.reminder_email_enabled,
        "reminder_sms_enabled": settings.reminder_sms_enabled,
        "reminder_whatsapp_enabled": settings.reminder_whatsapp_enabled,
        "reminder_day_before": settings.reminder_day_before,
        "reminder_on_day": settings.reminder_on_day,
        "overdue_followup_alert": settings.overdue_followup_alert,
        "appointment_reminders": settings.appointment_reminders,
        "low_stock_alerts": settings.low_stock_alerts,
        "receipt_footer": settings.receipt_footer,
        "display_message": settings.display_message,
        "public_display_enabled": settings.public_display_enabled,
        "allow_walk_in": settings.allow_walk_in,
        "auto_invoice_on_completion": settings.auto_invoice_on_completion,
    }


def clinic_detail(clinic):
    if not clinic:
        return None
    return {
        "id": clinic.id,
        "name": clinic.name,
        "slug": clinic.slug,
        "legal_name": clinic.legal_name,
        "registration_number": clinic.registration_number,
        "address_line1": clinic.address_line1,
        "address_line2": clinic.address_line2,
        "city": clinic.city,
        "state": clinic.state,
        "postal_code": clinic.postal_code,
        "country": clinic.country,
        "phone": clinic.phone,
        "email": clinic.email,
        "website": clinic.website,
        "logo_url": f"/api/public/clinics/{clinic.slug}/logo" if clinic.logo_path else None,
        "is_active": clinic.is_active,
        "is_demo": clinic.is_demo,
        "plan": clinic.plan,
        "display_key": clinic.display_key,
        "settings": settings_dict(clinic.settings),
        "created_at": iso(clinic.created_at),
    }


def user_me(user):
    data = {
        "id": user.id,
        "full_name": user.full_name,
        "initials": user.initials,
        "email": user.email,
        "phone": user.phone,
        "designation": user.designation,
        "avatar_color": user.avatar_color,
        "role": {"id": user.role.id, "name": user.role.name, "slug": user.role.slug} if user.role else None,
        "permissions": sorted(user.permission_codes()),
        "clinic": clinic_detail(user.clinic) if user.clinic else None,
        "doctor_id": user.doctor_profile.id if user.doctor_profile else None,
        "is_super_admin": user.is_super_admin,
        "must_change_password": user.must_change_password,
        "last_login_at": iso(user.last_login_at),
        "notification_email": user.notification_email,
        "notification_in_app": user.notification_in_app,
    }
    return data


def patient_summary(patient, include_contact=True):
    if not patient:
        return None
    return {
        "id": patient.id,
        "patient_code": patient.patient_code,
        "full_name": patient.full_name,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "age": patient.age,
        "gender": patient.gender,
        "date_of_birth": iso(patient.date_of_birth),
        "blood_group": patient.blood_group,
        "phone": patient.phone if include_contact else mask_phone(patient.phone),
        "phone_masked": mask_phone(patient.phone),
        "email": patient.email if include_contact else mask_email(patient.email),
        "is_active": patient.is_active,
        "merged_into_id": patient.merged_into_id,
        "created_at": iso(patient.created_at),
    }


def patient_detail(patient):
    data = patient_summary(patient)
    data.update(
        {
            "alternate_phone": patient.alternate_phone,
            "emergency_contact_name": patient.emergency_contact_name,
            "emergency_contact_relation": patient.emergency_contact_relation,
            "emergency_contact_phone": patient.emergency_contact_phone,
            "address_line1": patient.address_line1,
            "address_line2": patient.address_line2,
            "city": patient.city,
            "state": patient.state,
            "postal_code": patient.postal_code,
            "country": patient.country,
            "allergies": patient.allergies,
            "medical_history": patient.medical_history,
            "notes": patient.notes,
            "consent_email": patient.consent_email,
            "consent_sms": patient.consent_sms,
            "consent_whatsapp": patient.consent_whatsapp,
            "preferred_contact": patient.preferred_contact,
            "updated_at": iso(patient.updated_at),
        }
    )
    return data


def doctor_summary(doctor):
    if not doctor:
        return None
    return {
        "id": doctor.id,
        "doctor_code": doctor.doctor_code,
        "full_name": doctor.full_name,
        "specialization": doctor.specialization,
        "qualifications": doctor.qualifications,
        "consultation_fee": num(doctor.consultation_fee),
        "follow_up_fee": num(doctor.follow_up_fee),
        "room_number": doctor.room_number,
        "is_available": doctor.is_available,
        "is_active": doctor.is_active,
        "avg_consult_minutes": doctor.avg_consult_minutes,
        "user_id": doctor.user_id,
        "email": doctor.user.email if doctor.user else None,
        "phone": doctor.user.phone if doctor.user else None,
        "avatar_color": doctor.user.avatar_color if doctor.user else "#0ea5a4",
    }


def doctor_detail(doctor):
    data = doctor_summary(doctor)
    data.update(
        {
            "registration_number": doctor.registration_number,
            "experience_years": doctor.experience_years,
            "bio": doctor.bio,
            "schedules": [schedule_dict(s) for s in sorted(doctor.schedules, key=lambda x: (x.weekday, x.start_time)) if s.is_active],
            "leaves": [leave_dict(l) for l in sorted(doctor.leaves, key=lambda x: x.start_date, reverse=True) if l.end_date >= clinic_today(doctor.clinic)][:20],
        }
    )
    return data


def schedule_dict(schedule):
    return {
        "id": schedule.id,
        "weekday": schedule.weekday,
        "start_time": iso(schedule.start_time),
        "end_time": iso(schedule.end_time),
        "break_start": iso(schedule.break_start),
        "break_end": iso(schedule.break_end),
        "slot_minutes": schedule.slot_minutes,
        "max_tokens": schedule.max_tokens,
        "is_active": schedule.is_active,
    }


def leave_dict(leave):
    return {
        "id": leave.id,
        "doctor_id": leave.doctor_id,
        "start_date": iso(leave.start_date),
        "end_date": iso(leave.end_date),
        "leave_type": leave.leave_type,
        "reason": leave.reason,
        "status": leave.status,
    }


def appointment_dict(appointment):
    if not appointment:
        return None
    return {
        "id": appointment.id,
        "appointment_code": appointment.appointment_code,
        "patient": patient_summary(appointment.patient),
        "doctor": doctor_summary(appointment.doctor),
        "appointment_date": iso(appointment.appointment_date),
        "start_time": iso(appointment.start_time),
        "end_time": iso(appointment.end_time),
        "status": appointment.status,
        "visit_type": appointment.visit_type,
        "reason": appointment.reason,
        "notes": appointment.notes,
        "source": appointment.source,
        "token": token_brief(appointment.token),
        "override_reason": appointment.override_reason,
        "cancellation_reason": appointment.cancellation_reason,
        "created_at": iso(appointment.created_at),
    }


def token_brief(token):
    if not token:
        return None
    return {
        "id": token.id,
        "display_number": token.display_number,
        "token_number": token.token_number,
        "token_date": iso(token.token_date),
        "status": token.status,
        "visit_type": token.visit_type,
        "doctor_id": token.doctor_id,
        "priority": token.priority,
    }


def token_dict(token, include_patient=True):
    if not token:
        return None
    waiting_minutes = None
    if token.status in ("waiting", "called", "recalled") and token.created_at:
        now = clinic_now(token.doctor.clinic)
        created = as_utc(token.created_at).astimezone(now.tzinfo)
        waiting_minutes = max(0, int((now - created).total_seconds() // 60))
    return {
        "id": token.id,
        "display_number": token.display_number,
        "token_number": token.token_number,
        "token_date": iso(token.token_date),
        "queue_key": token.queue_key,
        "visit_type": token.visit_type,
        "status": token.status,
        "priority": token.priority,
        "notes": token.notes,
        "skip_reason": token.skip_reason,
        "patient": patient_summary(token.patient) if include_patient else None,
        "doctor": doctor_summary(token.doctor),
        "appointment_id": token.appointment_id,
        "follow_up_plan_id": token.follow_up_plan_id,
        "consultation_id": token.consultation_id,
        "transferred_from_id": token.transferred_from_id,
        "recall_count": token.recall_count,
        "waiting_minutes": waiting_minutes,
        "called_at": iso(token.called_at),
        "started_at": iso(token.started_at),
        "completed_at": iso(token.completed_at),
        "created_at": iso(token.created_at),
    }


def consultation_dict(consultation, include_clinical=True):
    if not consultation:
        return None
    data = {
        "id": consultation.id,
        "consultation_code": consultation.consultation_code,
        "version": consultation.version,
        "status": consultation.status,
        "patient": patient_summary(consultation.patient),
        "doctor": doctor_summary(consultation.doctor),
        "appointment_id": consultation.appointment_id,
        "token": token_brief(consultation.token),
        "follow_up_required": consultation.follow_up_required,
        "follow_up_notes": consultation.follow_up_notes,
        "started_at": iso(consultation.started_at),
        "completed_at": iso(consultation.completed_at),
        "created_at": iso(consultation.created_at),
        "prescriptions": [prescription_brief(p) for p in consultation.prescriptions],
    }
    if include_clinical:
        data.update(
            {
                "symptoms": consultation.symptoms,
                "observations": consultation.observations,
                "vitals": consultation.vitals or {},
                "diagnosis_summary": consultation.diagnosis_summary,
                "treatment_plan": consultation.treatment_plan,
                "doctor_notes": consultation.doctor_notes,
                "diagnoses": [
                    {
                        "id": d.id,
                        "icd_code": d.icd_code,
                        "description": d.description,
                        "diagnosis_type": d.diagnosis_type,
                        "notes": d.notes,
                    }
                    for d in consultation.diagnoses
                ],
            }
        )
    return data


def prescription_brief(prescription):
    if not prescription:
        return None
    return {
        "id": prescription.id,
        "prescription_code": prescription.prescription_code,
        "status": prescription.status,
        "issued_at": iso(prescription.issued_at),
        "item_count": len(prescription.items),
    }


def prescription_dict(prescription):
    if not prescription:
        return None
    return {
        "id": prescription.id,
        "prescription_code": prescription.prescription_code,
        "status": prescription.status,
        "issued_at": iso(prescription.issued_at),
        "notes": prescription.notes,
        "patient": patient_summary(prescription.patient),
        "doctor": doctor_summary(prescription.doctor),
        "consultation_id": prescription.consultation_id,
        "clinic": clinic_brief(prescription.consultation.doctor.clinic) if prescription.consultation else None,
        "items": [
            {
                "id": item.id,
                "medication_id": item.medication_id,
                "medicine_name": item.medicine_name,
                "strength": item.strength,
                "form": item.form,
                "dosage": item.dosage,
                "frequency": item.frequency,
                "duration_days": item.duration_days,
                "quantity": item.quantity,
                "instructions": item.instructions,
            }
            for item in prescription.items
        ],
    }


def followup_dict(plan):
    if not plan:
        return None
    tokens = sorted(
        plan.tokens,
        key=lambda item: (item.created_at.isoformat() if item.created_at else (item.token_date.isoformat() if item.token_date else ""), item.token_number),
        reverse=True,
    )
    token = next(
        (item for item in tokens if item.status not in ("cancelled", "completed", "skipped", "no_show")),
        tokens[0] if tokens else None,
    )
    return {
        "id": plan.id,
        "patient": patient_summary(plan.patient),
        "doctor": doctor_summary(plan.doctor),
        "consultation_id": plan.consultation_id,
        "appointment_id": plan.appointment_id,
        "due_date": iso(plan.due_date),
        "original_due_date": iso(plan.original_due_date),
        "instructions": plan.instructions,
        "status": plan.status,
        "priority": plan.priority,
        "contact_notes": plan.contact_notes,
        "confirmed_at": iso(plan.confirmed_at),
        "arrived_at": iso(plan.arrived_at),
        "completed_at": iso(plan.completed_at),
        "cancelled_at": iso(plan.cancelled_at),
        "cancellation_reason": plan.cancellation_reason,
        "reminder_count": plan.reminder_count,
        "last_reminder_at": iso(plan.last_reminder_at),
        "token": token_brief(token),
        "created_at": iso(plan.created_at),
    }


def invoice_item_dict(item):
    return {
        "id": item.id,
        "item_type": item.item_type,
        "description": item.description,
        "quantity": item.quantity,
        "unit_price": num(item.unit_price),
        "amount": num(item.amount),
    }


def payment_dict(payment):
    return {
        "id": payment.id,
        "payment_code": payment.payment_code,
        "amount": num(payment.amount),
        "method": payment.method,
        "reference_number": payment.reference_number,
        "notes": payment.notes,
        "status": payment.status,
        "paid_at": iso(payment.paid_at),
        "receiver": user_brief(payment.receiver),
        "refunded_amount": num(sum((r.amount for r in payment.refunds), 0)),
    }


def refund_dict(refund):
    return {
        "id": refund.id,
        "refund_code": refund.refund_code,
        "payment_id": refund.payment_id,
        "amount": num(refund.amount),
        "reason": refund.reason,
        "status": refund.status,
        "created_at": iso(refund.created_at),
        "approver": user_brief(refund.approver),
    }


def invoice_dict(invoice, include_payments=True):
    if not invoice:
        return None
    data = {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "patient": patient_summary(invoice.patient),
        "consultation_id": invoice.consultation_id,
        "token": token_brief(invoice.token),
        "status": invoice.status,
        "subtotal": num(invoice.subtotal),
        "discount_amount": num(invoice.discount_amount),
        "discount_reason": invoice.discount_reason,
        "tax_rate": num(invoice.tax_rate),
        "tax_amount": num(invoice.tax_amount),
        "total": num(invoice.total),
        "amount_paid": num(invoice.amount_paid),
        "balance": num(invoice.balance),
        "notes": invoice.notes,
        "due_date": iso(invoice.due_date),
        "issued_at": iso(invoice.issued_at),
        "created_at": iso(invoice.created_at),
        "items": [invoice_item_dict(i) for i in invoice.items],
        "refunded_amount": num(sum((r.amount for r in invoice.refunds), 0)),
    }
    if include_payments:
        data["payments"] = [payment_dict(p) for p in invoice.payments]
        data["refunds"] = [refund_dict(r) for r in invoice.refunds]
    return data


def medication_dict(medication, stock=None):
    batches = [b for b in medication.batches if b.quantity > 0]
    if stock is None:
        stock = sum(b.quantity for b in medication.batches)
    return {
        "id": medication.id,
        "sku": medication.sku,
        "name": medication.name,
        "generic_name": medication.generic_name,
        "category": medication.category,
        "form": medication.form,
        "strength": medication.strength,
        "manufacturer": medication.manufacturer,
        "unit_price": num(medication.unit_price),
        "reorder_level": medication.reorder_level,
        "is_active": medication.is_active,
        "stock": stock,
        "low_stock": stock <= medication.reorder_level,
        "nearest_expiry": iso(min((b.expiry_date for b in batches), default=None)),
    }


def inventory_dict(batch):
    return {
        "id": batch.id,
        "medication_id": batch.medication_id,
        "medication": medication_dict(batch.medication, stock=None) if batch.medication else None,
        "batch_number": batch.batch_number,
        "expiry_date": iso(batch.expiry_date),
        "quantity": batch.quantity,
        "purchase_price": num(batch.purchase_price),
        "mrp": num(batch.mrp),
        "supplier_id": batch.supplier_id,
        "supplier": batch.supplier.name if batch.supplier else None,
        "received_at": iso(batch.received_at),
        "expired": bool(batch.medication and batch.expiry_date < clinic_today(db.session.get(Clinic, batch.medication.clinic_id))) if batch.medication else False,
    }


def stock_movement_dict(movement):
    return {
        "id": movement.id,
        "medication": movement.medication.name if movement.medication else None,
        "medication_id": movement.medication_id,
        "movement_type": movement.movement_type,
        "quantity_delta": movement.quantity_delta,
        "reference_type": movement.reference_type,
        "reference_id": movement.reference_id,
        "notes": movement.notes,
        "created_by": user_brief(movement.creator),
        "created_at": iso(movement.created_at),
    }


def lab_test_dict(test):
    return {
        "id": test.id,
        "code": test.code,
        "name": test.name,
        "category": test.category,
        "sample_type": test.sample_type,
        "price": num(test.price),
        "turnaround_hours": test.turnaround_hours,
        "reference_range": test.reference_range,
        "is_active": test.is_active,
    }


def lab_item_dict(item):
    result = item.result
    return {
        "id": item.id,
        "test": lab_test_dict(item.test),
        "price": num(item.price),
        "status": item.status,
        "result": {
            "id": result.id,
            "result_value": result.result_value,
            "unit": result.unit,
            "reference_range": result.reference_range,
            "interpretation": result.interpretation,
            "result_notes": result.result_notes,
            "attachment_path": result.attachment_path,
            "verified_at": iso(result.verified_at),
            "verified_by": user_brief(result.verifier),
        }
        if result
        else None,
    }


def lab_order_dict(order):
    if not order:
        return None
    return {
        "id": order.id,
        "order_number": order.order_number,
        "patient": patient_summary(order.patient),
        "doctor": doctor_summary(order.doctor),
        "status": order.status,
        "priority": order.priority,
        "notes": order.notes,
        "total_amount": num(order.total_amount),
        "payment_status": order.payment_status,
        "ordered_at": iso(order.ordered_at),
        "sample_collected_at": iso(order.sample_collected_at),
        "completed_at": iso(order.completed_at),
        "items": [lab_item_dict(i) for i in order.items],
    }


def notification_dict(notification):
    return {
        "id": notification.id,
        "notification_type": notification.notification_type,
        "channel": notification.channel,
        "recipient": notification.recipient_masked,
        "subject": notification.subject,
        "body": notification.body,
        "status": notification.status,
        "attempts": notification.attempts,
        "provider": notification.provider,
        "error": notification.error,
        "sent_at": iso(notification.sent_at),
        "read_at": iso(notification.read_at),
        "created_at": iso(notification.created_at),
        "related_type": notification.related_type,
        "related_id": notification.related_id,
        "user_id": notification.user_id,
    }


def audit_dict(log):
    return {
        "id": log.id,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "details": log.details or {},
        "ip_address": log.ip_address,
        "user": user_brief(log.user),
        "created_at": iso(log.created_at),
    }


def staff_dict(user):
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "designation": user.designation,
        "avatar_color": user.avatar_color,
        "role": {"id": user.role.id, "name": user.role.name, "slug": user.role.slug} if user.role else None,
        "is_active": user.is_active,
        "last_login_at": iso(user.last_login_at),
        "created_at": iso(user.created_at),
        "doctor_id": user.doctor_profile.id if user.doctor_profile else None,
    }


def role_dict(role):
    return {
        "id": role.id,
        "name": role.name,
        "slug": role.slug,
        "description": role.description,
        "is_system": role.is_system,
        "permissions": sorted(p.code for p in role.permissions),
        "user_count": len(role.users),
    }
