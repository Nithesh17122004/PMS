"""Fictional demonstration data for ClinicFlow.

Everything here is invented. Names, phone numbers and clinical records are not
real. Demo accounts share the password ``Demo@12345`` and are clearly labelled
in the UI. Never run this against a production database containing real PHI.
"""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.auth.security import hash_password
from backend.extensions import db
from backend.models import (
    Appointment,
    AppointmentStatus,
    AuditLog,
    Clinic,
    ClinicSetting,
    Consultation,
    ConsultationStatus,
    DailyToken,
    Diagnosis,
    Doctor,
    DoctorLeave,
    DoctorSchedule,
    DocumentSequence,
    FollowUpPlan,
    FollowUpReminder,
    FollowUpStatus,
    InventoryBatch,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    LabOrder,
    LabOrderItem,
    LabOrderStatus,
    LabResult,
    LabTest,
    MedicalDocument,
    Medication,
    Notification,
    NotificationChannel,
    NotificationStatus,
    Patient,
    Payment,
    PaymentMethod,
    Prescription,
    PrescriptionItem,
    Refund,
    Role,
    StockMovement,
    Supplier,
    TokenSequence,
    TokenStatus,
    User,
    UserRole,
    VisitType,
)
from backend.permissions.rbac import create_super_admin_role, seed_permissions
from backend.services.sequence_service import (
    allocate_token_number,
    format_document_number,
    format_token_number,
    next_document_number,
)
from backend.utils.crypto import normalize_email

DEMO_PASSWORD = "Demo@12345"
DEMO_SLUGS = ("aster-family-clinic", "harbor-childrens-clinic")

FIRST_NAMES = [
    "Aarav", "Ananya", "Rohan", "Isha", "Kabir", "Meera", "Vihaan", "Diya",
    "Arjun", "Saanvi", "Aditya", "Naina", "Dev", "Pooja", "Karan", "Riya",
    "Nikhil", "Tara", "Siddharth", "Anjali", "Rahul", "Sneha", "Aryan", "Kavya",
    "Manish", "Divya", "Varun", "Neha", "Harsh", "Priya", "Yash", "Aisha",
]
LAST_NAMES = [
    "Sharma", "Rao", "Iyer", "Menon", "Nair", "Pillai", "Kapoor", "Verma",
    "Gupta", "Reddy", "Patel", "Desai", "Joshi", "Mehta", "Bhat", "Kulkarni",
    "Chopra", "Malhotra", "Sethi", "Bose",
]
CITIES = ["Bengaluru", "Mumbai", "Pune", "Hyderabad", "Chennai", "Kochi"]
BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]
ALLERGIES = [None, None, "Penicillin", "Sulfa drugs", "Peanuts", "Dust mites", "Lactose"]
DIAGNOSES = [
    ("J06.9", "Acute upper respiratory infection"),
    ("E11.9", "Type 2 diabetes mellitus without complications"),
    ("I10", "Essential hypertension"),
    ("K29.70", "Gastritis, unspecified"),
    ("L20.9", "Atopic dermatitis"),
    ("J45.909", "Unspecified asthma, uncomplicated"),
    ("R51.9", "Headache, unspecified"),
    ("M54.5", "Low back pain"),
]
MEDICINES = [
    ("Paracetamol", "500 mg", "Tablet", "1 tablet", "Twice daily", 5, "After food"),
    ("Amoxicillin", "250 mg", "Capsule", "1 capsule", "Thrice daily", 5, "Complete the course"),
    ("Metformin", "500 mg", "Tablet", "1 tablet", "Twice daily", 30, "With meals"),
    ("Atorvastatin", "10 mg", "Tablet", "1 tablet", "Once at night", 30, "At bedtime"),
    ("Omeprazole", "20 mg", "Capsule", "1 capsule", "Once daily", 14, "Before breakfast"),
    ("Cetirizine", "10 mg", "Tablet", "1 tablet", "Once at night", 7, "May cause drowsiness"),
    ("Azithromycin", "500 mg", "Tablet", "1 tablet", "Once daily", 3, "Before food"),
    ("Salbutamol Inhaler", "100 mcg", "Inhaler", "2 puffs", "When required", 30, "Rinse mouth after use"),
]
LAB_TESTS = [
    ("CBC", "Complete Blood Count", "Haematology", "Blood", 350, "4.0–11.0 x10^9/L"),
    ("HBA1C", "HbA1c", "Biochemistry", "Blood", 450, "4.0–5.6%"),
    ("LIPID", "Lipid Profile", "Biochemistry", "Blood", 650, "<200 mg/dL total cholesterol"),
    ("THYROID", "Thyroid Profile", "Biochemistry", "Blood", 700, "0.4–4.0 mIU/L TSH"),
    ("URINE", "Urine Routine", "Pathology", "Urine", 250, "Clear, no protein"),
    ("LFT", "Liver Function Test", "Biochemistry", "Blood", 800, "ALT 7–56 U/L"),
]


def _local(clinic, day: date, hour: int, minute: int = 0) -> datetime:
    tz = ZoneInfo(clinic.settings.timezone)
    return datetime.combine(day, time(hour, minute), tzinfo=tz).astimezone(timezone.utc)


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _purge_demo_clinics() -> int:
    clinics = Clinic.query.filter(Clinic.slug.in_(DEMO_SLUGS)).all()
    if not clinics:
        return 0
    ids = [c.id for c in clinics]
    invoice_ids = select(Invoice.id).where(Invoice.clinic_id.in_(ids))
    prescription_ids = select(Prescription.id).where(Prescription.clinic_id.in_(ids))
    consultation_ids = select(Consultation.id).where(Consultation.clinic_id.in_(ids))
    lab_order_ids = select(LabOrder.id).where(LabOrder.clinic_id.in_(ids))
    lab_item_ids = select(LabOrderItem.id).where(LabOrderItem.order_id.in_(lab_order_ids))

    for model in (
        Notification,
        FollowUpReminder,
        DailyToken,
        TokenSequence,
        FollowUpPlan,
    ):
        model.query.filter(model.clinic_id.in_(ids)).delete(synchronize_session=False)
    LabResult.query.filter(LabResult.lab_order_item_id.in_(lab_item_ids)).delete(synchronize_session=False)
    LabOrderItem.query.filter(LabOrderItem.order_id.in_(lab_order_ids)).delete(synchronize_session=False)
    LabOrder.query.filter(LabOrder.clinic_id.in_(ids)).delete(synchronize_session=False)
    LabTest.query.filter(LabTest.clinic_id.in_(ids)).delete(synchronize_session=False)
    StockMovement.query.filter(StockMovement.clinic_id.in_(ids)).delete(synchronize_session=False)
    InventoryBatch.query.filter(InventoryBatch.clinic_id.in_(ids)).delete(synchronize_session=False)
    Medication.query.filter(Medication.clinic_id.in_(ids)).delete(synchronize_session=False)
    Supplier.query.filter(Supplier.clinic_id.in_(ids)).delete(synchronize_session=False)
    Refund.query.filter(Refund.clinic_id.in_(ids)).delete(synchronize_session=False)
    Payment.query.filter(Payment.clinic_id.in_(ids)).delete(synchronize_session=False)
    InvoiceItem.query.filter(InvoiceItem.invoice_id.in_(invoice_ids)).delete(synchronize_session=False)
    Invoice.query.filter(Invoice.clinic_id.in_(ids)).delete(synchronize_session=False)
    PrescriptionItem.query.filter(PrescriptionItem.prescription_id.in_(prescription_ids)).delete(synchronize_session=False)
    Prescription.query.filter(Prescription.clinic_id.in_(ids)).delete(synchronize_session=False)
    Diagnosis.query.filter(Diagnosis.consultation_id.in_(consultation_ids)).delete(synchronize_session=False)
    Consultation.query.filter(Consultation.clinic_id.in_(ids)).delete(synchronize_session=False)
    Appointment.query.filter(Appointment.clinic_id.in_(ids)).delete(synchronize_session=False)
    DoctorLeave.query.filter(DoctorLeave.clinic_id.in_(ids)).delete(synchronize_session=False)
    DoctorSchedule.query.filter(DoctorSchedule.clinic_id.in_(ids)).delete(synchronize_session=False)
    Doctor.query.filter(Doctor.clinic_id.in_(ids)).delete(synchronize_session=False)
    MedicalDocument.query.filter(MedicalDocument.clinic_id.in_(ids)).delete(synchronize_session=False)
    Patient.query.filter(Patient.clinic_id.in_(ids)).delete(synchronize_session=False)
    DocumentSequence.query.filter(DocumentSequence.clinic_id.in_(ids)).delete(synchronize_session=False)
    UserRole.query.filter(UserRole.clinic_id.in_(ids)).delete(synchronize_session=False)
    AuditLog.query.filter(AuditLog.clinic_id.in_(ids)).delete(synchronize_session=False)
    User.query.filter(User.clinic_id.in_(ids)).delete(synchronize_session=False)
    Role.query.filter(Role.clinic_id.in_(ids)).delete(synchronize_session=False)
    ClinicSetting.query.filter(ClinicSetting.clinic_id.in_(ids)).delete(synchronize_session=False)
    for clinic in clinics:
        db.session.delete(clinic)
    db.session.commit()
    return len(clinics)


def _role(clinic: Clinic, slug: str) -> Role:
    role = Role.query.filter_by(clinic_id=clinic.id, slug=slug).first()
    if role is None:
        raise RuntimeError(f"Role {slug} was not created for the demo clinic.")
    return role


def _staff(clinic: Clinic, slug: str, email: str, name: str, designation: str) -> User:
    existing = User.query.filter_by(email=email).first()
    if existing:
        return existing
    user = User(
        clinic_id=clinic.id,
        role_id=_role(clinic, slug).id,
        email=email,
        password_hash=hash_password(DEMO_PASSWORD),
        full_name=name,
        designation=designation,
        avatar_color={
            "clinic_admin": "#1d4ed8",
            "receptionist": "#0f9d8f",
            "doctor": "#0ea5a4",
            "nurse": "#7c3aed",
            "accountant": "#b45309",
            "pharmacist": "#be123c",
            "lab_technician": "#0369a1",
        }.get(slug, "#2563eb"),
    )
    db.session.add(user)
    db.session.flush()
    return user


def _doctor(
    clinic: Clinic,
    user: User,
    name: str,
    specialization: str,
    qualifications: str,
    fee: int,
    followup_fee: int,
    room: str,
    registration: str,
) -> Doctor:
    number = next_document_number(clinic.id, "doctor")
    doctor = Doctor(
        clinic_id=clinic.id,
        user_id=user.id,
        doctor_code=format_document_number("DR-", number, width=4),
        full_name=name,
        specialization=specialization,
        qualifications=qualifications,
        registration_number=registration,
        experience_years=8,
        consultation_fee=fee,
        follow_up_fee=followup_fee,
        bio=f"{name} provides {specialization.lower()} care at {clinic.name}.",
        room_number=room,
        avg_consult_minutes=12,
        is_available=True,
    )
    db.session.add(doctor)
    db.session.flush()
    for weekday in range(7):
        db.session.add(
            DoctorSchedule(
                clinic_id=clinic.id,
                doctor_id=doctor.id,
                weekday=weekday,
                start_time=time(9, 0),
                end_time=time(13, 0),
                break_start=time(11, 0),
                break_end=time(11, 30),
                slot_minutes=15,
                max_tokens=24,
            )
        )
    return doctor


def _patient(clinic: Clinic, rng: random.Random, index: int) -> Patient:
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    period = date.today().strftime("%Y%m")
    number = next_document_number(clinic.id, "patient", period=period)
    prefix = (clinic.settings.patient_prefix if clinic.settings else "P") or "P"
    patient = Patient(
        clinic_id=clinic.id,
        patient_code=format_document_number(f"{prefix}-", number, width=4, period=period),
        first_name=first,
        last_name=last,
        date_of_birth=date(1955, 1, 1) + timedelta(days=rng.randint(0, 70 * 365)),
        gender=rng.choice(["female", "male", "other"]),
        blood_group=rng.choice(BLOOD_GROUPS),
        city=rng.choice(CITIES),
        state="Karnataka" if rng.random() > 0.4 else "Maharashtra",
        allergies=rng.choice(ALLERGIES),
        medical_history=rng.choice([None, "No known chronic illness.", "Hypertension — on treatment.", "Type 2 diabetes — on treatment."]),
        consent_email=True,
        consent_sms=True,
        consent_whatsapp=rng.random() > 0.25,
        preferred_contact="phone",
    )
    phone = f"+91 9{rng.randint(100000000, 999999999)}"
    patient.set_phone(phone)
    if rng.random() > 0.2:
        patient.email = f"{first.lower()}.{last.lower()}{index}@example.test"
    db.session.add(patient)
    db.session.flush()
    return patient


def _token(
    clinic: Clinic,
    doctor: Doctor,
    patient: Patient,
    day: date,
    status: str,
    rng: random.Random,
    visit_type: str = VisitType.WALK_IN,
    priority: int = 0,
    hour: int = 9,
) -> DailyToken:
    queue_key = "COMMON" if clinic.settings and clinic.settings.token_mode == "clinic" else doctor.id
    number = allocate_token_number(clinic.id, day, queue_key)
    prefix = clinic.settings.token_prefix if clinic.settings else ""
    created = _local(clinic, day, hour, rng.randint(0, 50))
    token = DailyToken(
        clinic_id=clinic.id,
        doctor_id=doctor.id,
        patient_id=patient.id,
        token_date=day,
        queue_key=queue_key,
        token_number=number,
        display_number=format_token_number(prefix, number),
        visit_type=visit_type,
        status=status,
        priority=priority,
        created_at=created,
        created_by=doctor.user_id,
    )
    if status in (TokenStatus.CALLED, TokenStatus.RECALLED, TokenStatus.IN_CONSULTATION, TokenStatus.COMPLETED):
        token.called_at = created + timedelta(minutes=rng.randint(8, 25))
    if status in (TokenStatus.IN_CONSULTATION, TokenStatus.COMPLETED):
        token.started_at = token.called_at + timedelta(minutes=2)
    if status == TokenStatus.COMPLETED:
        token.completed_at = token.started_at + timedelta(minutes=rng.randint(8, 20))
    if status == TokenStatus.SKIPPED:
        token.skip_reason = "Patient did not respond when called"
    if status == TokenStatus.NO_SHOW:
        token.skip_reason = "Patient unavailable"
    db.session.add(token)
    db.session.flush()
    return token


def _consultation(
    clinic: Clinic,
    doctor: Doctor,
    patient: Patient,
    token: DailyToken | None,
    day: date,
    rng: random.Random,
    completed: bool = True,
) -> Consultation:
    number = next_document_number(clinic.id, "consultation")
    code, description = rng.choice(DIAGNOSES)
    started = _local(clinic, day, 10, rng.randint(0, 40))
    consultation = Consultation(
        clinic_id=clinic.id,
        consultation_code=format_document_number("CONS-", number, width=6),
        patient_id=patient.id,
        doctor_id=doctor.id,
        appointment_id=token.appointment_id if token else None,
        status=ConsultationStatus.COMPLETED if completed else ConsultationStatus.DRAFT,
        symptoms=rng.choice([
            "Fever and sore throat for three days.",
            "Recurring headache with mild nausea.",
            "Cough and wheezing at night.",
            "Routine diabetes review.",
            "Itchy rash on both forearms.",
        ]),
        observations="Alert, oriented, no acute distress. Chest clear. No pedal oedema.",
        vitals={
            "blood_pressure": f"{rng.randint(110, 138)}/{rng.randint(70, 88)} mmHg",
            "pulse": f"{rng.randint(64, 92)} bpm",
            "temperature": f"{rng.randint(97, 100)}.{rng.randint(0, 9)} °F",
            "weight_kg": f"{rng.randint(48, 92)}",
            "spo2": f"{rng.randint(96, 99)}%",
        },
        diagnosis_summary=description,
        treatment_plan="Medication, hydration, review in one week. Red-flag advice explained.",
        doctor_notes="Counselled on lifestyle and medication adherence.",
        started_at=started,
        created_by=doctor.user_id,
    )
    if completed:
        consultation.completed_at = started + timedelta(minutes=rng.randint(10, 18))
        consultation.completed_by = doctor.user_id
    db.session.add(consultation)
    db.session.flush()
    db.session.add(
        Diagnosis(
            consultation_id=consultation.id,
            clinic_id=clinic.id,
            icd_code=code,
            description=description,
            diagnosis_type="primary",
        )
    )
    if completed and token:
        token.consultation_id = consultation.id
        token.status = TokenStatus.COMPLETED
        token.completed_at = consultation.completed_at
        _prescription(clinic, doctor, patient, consultation, rng)
    elif not completed and token:
        token.consultation_id = consultation.id
        token.status = TokenStatus.IN_CONSULTATION
    return consultation


def _prescription(clinic, doctor, patient, consultation, rng) -> Prescription:
    number = next_document_number(clinic.id, "prescription")
    prescription = Prescription(
        clinic_id=clinic.id,
        consultation_id=consultation.id,
        patient_id=patient.id,
        doctor_id=doctor.id,
        prescription_code=format_document_number("RX-", number, width=6),
        notes="Take medicines as directed. Return if symptoms worsen.",
        created_by=doctor.user_id,
    )
    db.session.add(prescription)
    db.session.flush()
    for index, (name, strength, form, dosage, frequency, days, instructions) in enumerate(
        rng.sample(MEDICINES, rng.randint(1, 3))
    ):
        db.session.add(
            PrescriptionItem(
                prescription_id=prescription.id,
                clinic_id=clinic.id,
                medicine_name=name,
                strength=strength,
                form=form,
                dosage=dosage,
                frequency=frequency,
                duration_days=days,
                quantity=str(days * 2),
                instructions=instructions,
                sort_order=index,
            )
        )
    return prescription


def _invoice(clinic, doctor, patient, consultation, token, actor_id, rng, status="paid") -> Invoice:
    period = (consultation.completed_at or datetime.now(timezone.utc)).astimezone(
        ZoneInfo(clinic.settings.timezone)
    ).strftime("%Y%m")
    number = next_document_number(clinic.id, "invoice", period=period)
    prefix = (clinic.settings.invoice_prefix if clinic.settings else "INV") or "INV"
    subtotal = _money(doctor.consultation_fee)
    tax_rate = _money(clinic.settings.tax_rate if clinic.settings else 0)
    tax = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"))
    total = subtotal + tax
    if status == "paid":
        paid = total
        balance = Decimal("0")
        invoice_status = InvoiceStatus.PAID
    elif status == "partial":
        paid = (total / 2).quantize(Decimal("0.01"))
        balance = total - paid
        invoice_status = InvoiceStatus.PARTIAL
    else:
        paid = Decimal("0")
        balance = total
        invoice_status = InvoiceStatus.UNPAID
    issued = consultation.completed_at or datetime.now(timezone.utc)
    invoice = Invoice(
        clinic_id=clinic.id,
        invoice_number=format_document_number(f"{prefix}-", number, width=5, period=period),
        patient_id=patient.id,
        consultation_id=consultation.id,
        token_id=token.id if token else None,
        status=invoice_status,
        subtotal=subtotal,
        discount_amount=Decimal("0"),
        tax_rate=tax_rate,
        tax_amount=tax,
        total=total,
        amount_paid=paid,
        balance=balance,
        notes="Thank you for visiting.",
        issued_at=issued,
        created_by=actor_id,
    )
    db.session.add(invoice)
    db.session.flush()
    db.session.add(
        InvoiceItem(
            invoice_id=invoice.id,
            clinic_id=clinic.id,
            item_type="consultation",
            description=f"Consultation — {doctor.full_name}",
            quantity=1,
            unit_price=subtotal,
            amount=subtotal,
            reference_id=consultation.id,
        )
    )
    if paid > 0:
        payment_number = next_document_number(clinic.id, "payment")
        db.session.add(
            Payment(
                invoice_id=invoice.id,
                clinic_id=clinic.id,
                patient_id=patient.id,
                payment_code=format_document_number("PAY-", payment_number, width=6),
                amount=paid,
                method=rng.choice(PaymentMethod.ALL[:5]),
                status="completed",
                received_by=actor_id,
                paid_at=issued + timedelta(minutes=rng.randint(1, 15)),
            )
        )
    return invoice


def _appointments(clinic, doctors, patients, actor_id, rng):
    today = date.today()
    for index in range(8):
        doctor = doctors[index % len(doctors)]
        patient = patients[(index * 3 + 1) % len(patients)]
        day = today + timedelta(days=index % 4)
        start = time(9 + (index % 7), (index % 4) * 15)
        end = (datetime.combine(day, start) + timedelta(minutes=15)).time()
        number = next_document_number(clinic.id, "appointment")
        db.session.add(
            Appointment(
                clinic_id=clinic.id,
                appointment_code=format_document_number("APT-", number, width=6),
                patient_id=patient.id,
                doctor_id=doctor.id,
                appointment_date=day,
                start_time=start,
                end_time=end,
                status=AppointmentStatus.CONFIRMED if index % 2 == 0 else AppointmentStatus.SCHEDULED,
                visit_type="consultation" if index % 3 else "follow_up",
                reason=rng.choice(["Fever", "Follow-up review", "Routine check-up", "Skin rash", "Child vaccination"]),
                source="reception",
                created_by=actor_id,
            )
        )


def _followups(clinic, doctors, patients, actor_id, rng):
    today = date.today()
    offsets = [-3, 0, 0, 1, 2, 7]
    statuses = [
        FollowUpStatus.UPCOMING,
        FollowUpStatus.CONFIRMED,
        FollowUpStatus.UPCOMING,
        FollowUpStatus.UPCOMING,
        FollowUpStatus.CONFIRMED,
        FollowUpStatus.COMPLETED,
    ]
    for index, offset in enumerate(offsets):
        doctor = doctors[index % len(doctors)]
        patient = patients[(index * 4 + 2) % len(patients)]
        due = today + timedelta(days=offset)
        plan = FollowUpPlan(
            clinic_id=clinic.id,
            patient_id=patient.id,
            doctor_id=doctor.id,
            due_date=due,
            original_due_date=due,
            instructions=rng.choice([
                "Review blood pressure and medication adherence.",
                "Review lab reports and adjust treatment.",
                "Wound review and dressing change.",
                "Discuss lifestyle changes and repeat HbA1c in 3 months.",
            ]),
            status=statuses[index],
            priority="high" if index == 1 else "normal",
            reminder_count=1 if index < 3 else 0,
            last_reminder_at=datetime.now(timezone.utc) - timedelta(days=1) if index < 3 else None,
            created_by=actor_id,
        )
        if plan.status == FollowUpStatus.CONFIRMED:
            plan.confirmed_at = datetime.now(timezone.utc) - timedelta(days=1)
        if plan.status == FollowUpStatus.COMPLETED:
            plan.completed_at = datetime.now(timezone.utc) - timedelta(days=2)
        db.session.add(plan)


def _lab(clinic, doctors, patients, staff, rng):
    tests = []
    for code, name, category, sample, price, reference in LAB_TESTS:
        test = LabTest(
            clinic_id=clinic.id,
            code=code,
            name=name,
            category=category,
            sample_type=sample,
            price=price,
            turnaround_hours=24,
            reference_range=reference,
        )
        db.session.add(test)
        tests.append(test)
    db.session.flush()
    period = date.today().strftime("%Y%m")
    statuses = [
        LabOrderStatus.COMPLETED,
        LabOrderStatus.PROCESSING,
        LabOrderStatus.ORDERED,
        LabOrderStatus.SAMPLE_COLLECTED,
        LabOrderStatus.CANCELLED,
    ]
    for index, status in enumerate(statuses):
        number = next_document_number(clinic.id, "lab_order", period=period)
        patient = patients[(index * 5 + 1) % len(patients)]
        doctor = doctors[index % len(doctors)]
        order = LabOrder(
            clinic_id=clinic.id,
            order_number=format_document_number("LAB-", number, width=5, period=period),
            patient_id=patient.id,
            doctor_id=doctor.id,
            status=status,
            priority="urgent" if index == 1 else "routine",
            notes="Please correlate with clinical findings.",
            total_amount=Decimal("0"),
            payment_status="paid" if status == LabOrderStatus.COMPLETED else "pending",
            ordered_at=datetime.now(timezone.utc) - timedelta(days=index, hours=2),
            created_by=staff.id,
        )
        if status in (LabOrderStatus.SAMPLE_COLLECTED, LabOrderStatus.PROCESSING, LabOrderStatus.COMPLETED):
            order.sample_collected_at = order.ordered_at + timedelta(hours=1)
        if status == LabOrderStatus.COMPLETED:
            order.completed_at = order.ordered_at + timedelta(hours=4)
        db.session.add(order)
        db.session.flush()
        selected = rng.sample(tests, 2 if index != 2 else 3)
        total = Decimal("0")
        for test in selected:
            item = LabOrderItem(
                order_id=order.id,
                clinic_id=clinic.id,
                lab_test_id=test.id,
                price=test.price,
                status=status,
            )
            db.session.add(item)
            db.session.flush()
            total += Decimal(str(test.price))
            if status in (LabOrderStatus.COMPLETED, LabOrderStatus.PROCESSING) and index < 2:
                result = LabResult(
                    lab_order_item_id=item.id,
                    clinic_id=clinic.id,
                    result_value=rng.choice(["5.6", "7.1", "12.4", "138", "0.8", "Normal"]),
                    unit="mg/dL" if test.code in ("HBA1C", "LIPID") else "",
                    reference_range=test.reference_range,
                    interpretation=rng.choice(["normal", "normal", "abnormal"]),
                    result_notes="Correlate with clinical picture.",
                    entered_by=staff.id,
                    verified_by=staff.id if status == LabOrderStatus.COMPLETED else None,
                    verified_at=order.completed_at if status == LabOrderStatus.COMPLETED else None,
                )
                db.session.add(result)
        order.total_amount = total


def _pharmacy(clinic, staff, rng):
    suppliers = [
        Supplier(
            clinic_id=clinic.id,
            name="MediSupply Distributors",
            contact_person="Ramesh Kumar",
            phone="+91 80 4123 8890",
            email="orders@medisupply.example",
            gstin="29ABCDE1234F1Z5",
        ),
        Supplier(
            clinic_id=clinic.id,
            name="CareLine Pharma",
            contact_person="Sunita Desai",
            phone="+91 22 2640 7712",
            email="hello@careline.example",
            gstin="27PQRSX5678G1Z2",
        ),
    ]
    db.session.add_all(suppliers)
    db.session.flush()
    catalogue = [
        ("PARA500", "Paracetamol", "Acetaminophen", "Analgesic", "Tablet", "500 mg", 2.50, 20),
        ("AMOX250", "Amoxicillin", "Amoxicillin", "Antibiotic", "Capsule", "250 mg", 6.80, 20),
        ("MET500", "Metformin", "Metformin hydrochloride", "Antidiabetic", "Tablet", "500 mg", 3.20, 30),
        ("ATOR10", "Atorvastatin", "Atorvastatin calcium", "Cardiovascular", "Tablet", "10 mg", 5.40, 20),
        ("OME20", "Omeprazole", "Omeprazole", "Gastro", "Capsule", "20 mg", 4.10, 20),
        ("CET10", "Cetirizine", "Cetirizine hydrochloride", "Antihistamine", "Tablet", "10 mg", 1.80, 30),
        ("AZI500", "Azithromycin", "Azithromycin", "Antibiotic", "Tablet", "500 mg", 18.50, 10),
        ("SAL100", "Salbutamol Inhaler", "Salbutamol", "Respiratory", "Inhaler", "100 mcg", 165.00, 5),
        ("ORS", "ORS Sachet", "Oral rehydration salts", "General", "Sachet", "20.5 g", 12.00, 25),
        ("INSGLAR", "Insulin Glargine", "Insulin glargine", "Antidiabetic", "Injection", "100 IU/mL", 480.00, 4),
    ]
    for index, (sku, name, generic, category, form, strength, price, reorder) in enumerate(catalogue):
        medication = Medication(
            clinic_id=clinic.id,
            sku=sku,
            name=name,
            generic_name=generic,
            category=category,
            form=form,
            strength=strength,
            manufacturer="Fictional Pharma Ltd.",
            unit_price=price,
            reorder_level=reorder,
        )
        db.session.add(medication)
        db.session.flush()
        quantity = reorder - 2 if index in (1, 7, 9) else rng.randint(reorder + 10, reorder + 90)
        expiry = date.today() + timedelta(days=40 if index == 7 else rng.randint(120, 700))
        batch = InventoryBatch(
            clinic_id=clinic.id,
            medication_id=medication.id,
            supplier_id=suppliers[index % 2].id,
            batch_number=f"B{date.today().strftime('%y%m')}{index + 1:02d}",
            expiry_date=expiry,
            quantity=quantity,
            purchase_price=(Decimal(str(price)) * Decimal("0.7")).quantize(Decimal("0.01")),
            mrp=price,
            created_by=staff.id,
        )
        db.session.add(batch)
        db.session.flush()
        db.session.add(
            StockMovement(
                clinic_id=clinic.id,
                medication_id=medication.id,
                inventory_id=batch.id,
                movement_type="purchase",
                quantity_delta=quantity,
                reference_type="inventory_batch",
                reference_id=batch.id,
                notes="Opening demonstration stock",
                created_by=staff.id,
            )
        )


def _notifications(clinic, users):
    messages = [
        ("Your queue has 3 patients waiting.", "queue_update"),
        ("Low stock alert: Salbutamol Inhaler is below reorder level.", "low_stock"),
        ("2 follow-ups are overdue and need review.", "overdue_followups"),
    ]
    for index, user in enumerate(users[:3]):
        body, kind = messages[index]
        db.session.add(
            Notification(
                clinic_id=clinic.id,
                user_id=user.id,
                notification_type=kind,
                channel=NotificationChannel.IN_APP,
                subject="ClinicFlow update",
                body=body,
                status=NotificationStatus.SENT,
                sent_at=datetime.now(timezone.utc) - timedelta(minutes=20 * (index + 1)),
                dedupe_key=f"demo-notification:{clinic.id}:{user.id}:{kind}",
            )
        )


def _seed_clinic(clinic: Clinic, admin: User, profile: str):
    rng = random.Random(20261101 + (1 if profile == "full" else 2))
    clinic_admin = admin
    receptionist = _staff(clinic, "receptionist", "demo.reception@clinicflow.demo" if profile == "full" else "demo.reception2@clinicflow.demo", "Priya Nair", "Front Desk Executive")
    nurse = _staff(clinic, "nurse", "demo.nurse@clinicflow.demo" if profile == "full" else "demo.nurse2@clinicflow.demo", "Neha Kulkarni", "Staff Nurse")
    accountant = _staff(clinic, "accountant", "demo.accountant@clinicflow.demo" if profile == "full" else "demo.accountant2@clinicflow.demo", "Rahul Mehta", "Accounts Executive")
    pharmacist = _staff(clinic, "pharmacist", "demo.pharmacist@clinicflow.demo" if profile == "full" else "demo.pharmacist2@clinicflow.demo", "Sana Sheikh", "Chief Pharmacist")
    lab_staff = _staff(clinic, "lab_technician", "demo.lab@clinicflow.demo" if profile == "full" else "demo.lab2@clinicflow.demo", "Arun Pillai", "Laboratory Technician")

    if profile == "full":
        doctor_specs = [
            ("demo.doctor@clinicflow.demo", "Dr. Ananya Rao", "General Medicine", "MBBS, MD (Internal Medicine)", 600, 200, "101", "KMC-45821"),
            ("demo.doctor.peds@clinicflow.demo", "Dr. Vikram Menon", "Pediatrics", "MBBS, DCH, DNB", 700, 250, "102", "KMC-51209"),
            ("demo.doctor.derm@clinicflow.demo", "Dr. Meera Iyer", "Dermatology", "MBBS, MD (Dermatology)", 800, 300, "103", "KMC-39014"),
        ]
    else:
        doctor_specs = [
            ("demo.doctor2@clinicflow.demo", "Dr. Arjun Nair", "Pediatrics", "MBBS, DCH", 650, 200, "201", "KMC-60218"),
            ("demo.doctor3@clinicflow.demo", "Dr. Kavya Pillai", "General Medicine", "MBBS, MD", 550, 150, "202", "KMC-47310"),
        ]
    doctors = []
    for email, name, spec, qual, fee, followup, room, reg in doctor_specs:
        user = _staff(clinic, "doctor", email, name, "Doctor")
        doctors.append(_doctor(clinic, user, name, spec, qual, fee, followup, room, reg))

    patient_count = 26 if profile == "full" else 16
    patients = [_patient(clinic, rng, i + 1) for i in range(patient_count)]
    _appointments(clinic, doctors, patients, receptionist.id, rng)
    _followups(clinic, doctors, patients, receptionist.id, rng)
    _lab(clinic, doctors, patients, lab_staff, rng)
    _pharmacy(clinic, pharmacist, rng)

    today = date.today()
    # Past two weeks: enough volume for charts and reports.
    for offset in range(14, 0, -1):
        day = today - timedelta(days=offset)
        for doctor in doctors:
            for slot in range(2 + rng.randint(0, 2)):
                patient = rng.choice(patients)
                status = TokenStatus.COMPLETED if rng.random() > 0.14 else rng.choice([TokenStatus.SKIPPED, TokenStatus.NO_SHOW])
                token = _token(clinic, doctor, patient, day, status, rng, hour=9 + slot)
                if status == TokenStatus.COMPLETED:
                    consultation = _consultation(clinic, doctor, patient, token, day, rng, completed=True)
                    if slot == 0:
                        invoice_status = "paid" if rng.random() > 0.22 else "unpaid"
                        _invoice(clinic, doctor, patient, consultation, token, receptionist.id, rng, invoice_status)
                elif status == TokenStatus.NO_SHOW:
                    token.status = TokenStatus.NO_SHOW

    # Today's live queue.
    for doctor in doctors:
        for slot in range(2):
            patient = rng.choice(patients)
            token = _token(clinic, doctor, patient, today, TokenStatus.COMPLETED, rng, hour=9 + slot)
            consultation = _consultation(clinic, doctor, patient, token, today, rng, completed=True)
            _invoice(clinic, doctor, patient, consultation, token, receptionist.id, rng, "paid")
        patient = rng.choice(patients)
        token = _token(clinic, doctor, patient, today, TokenStatus.IN_CONSULTATION, rng, hour=11)
        _consultation(clinic, doctor, patient, token, today, rng, completed=False)
        _token(clinic, doctor, rng.choice(patients), today, TokenStatus.CALLED, rng, hour=11)
        for _ in range(3):
            _token(clinic, doctor, rng.choice(patients), today, TokenStatus.WAITING, rng, hour=11)
        _token(clinic, doctor, rng.choice(patients), today, TokenStatus.SKIPPED, rng, hour=10)
        if profile == "full" and doctor.specialization == "General Medicine":
            _token(
                clinic, doctor, rng.choice(patients), today, TokenStatus.WAITING, rng,
                visit_type=VisitType.EMERGENCY, priority=10, hour=11,
            )

    _notifications(clinic, [clinic_admin, receptionist, nurse, pharmacist, lab_staff, *[d.user for d in doctors if d.user]])
    db.session.add(
        AuditLog(
            clinic_id=clinic.id,
            user_id=clinic_admin.id,
            action="demo.environment_seeded",
            entity_type="clinic",
            entity_id=clinic.id,
            details={"profile": profile, "note": "Fictional demonstration data"},
            user_agent="seed",
        )
    )
    db.session.commit()


def seed_demo_environment(reset: bool = False, if_empty: bool = False) -> str:
    seed_permissions()
    create_super_admin_role()
    db.session.commit()

    super_admin = User.query.filter_by(email="demo.superadmin@clinicflow.demo").first()
    if super_admin is None:
        super_admin = User(
            email="demo.superadmin@clinicflow.demo",
            full_name="Demo Platform Admin",
            password_hash=hash_password(DEMO_PASSWORD),
            role=create_super_admin_role(),
            designation="Platform Administrator",
            is_active=True,
            clinic_id=None,
        )
        db.session.add(super_admin)
        db.session.commit()

    if reset:
        _purge_demo_clinics()
    existing = Clinic.query.filter(Clinic.slug.in_(DEMO_SLUGS)).first()
    if existing:
        return (
            "Demo clinics already exist. Use --reset to rebuild them. "
            "Accounts: demo.reception@clinicflow.demo / demo.doctor@clinicflow.demo."
        )
    if if_empty and Clinic.query.filter_by(is_demo=True).first():
        return "Demo data already present."

    from backend.services.clinic_service import create_clinic

    clinic1, admin1, _ = create_clinic(
        {
            "name": "Aster Family Clinic",
            "slug": "aster-family-clinic",
            "legal_name": "Aster Family Clinic LLP",
            "email": "hello@asterfamily.example",
            "phone": "+91 80 4567 1200",
            "address_line1": "14, 3rd Cross, Indiranagar",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560038",
            "country": "India",
            "timezone": "Asia/Kolkata",
            "currency": "INR",
            "tax_rate": 5,
            "invoice_prefix": "AST",
            "patient_prefix": "AST",
            "token_prefix": "",
            "token_mode": "doctor",
            "working_days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
            "open_time": time(9, 0),
            "close_time": time(20, 0),
            "slot_minutes": 15,
            "consultation_fee_default": 600,
            "follow_up_fee_default": 200,
            "is_demo": True,
            "admin_name": "Dr. Ramesh Shenoy",
            "admin_email": "demo.admin@clinicflow.demo",
            "admin_password": DEMO_PASSWORD,
            "admin_phone": "+91 98450 11223",
        },
        super_admin,
    )
    clinic2, admin2, _ = create_clinic(
        {
            "name": "Harbor Children's Clinic",
            "slug": "harbor-childrens-clinic",
            "legal_name": "Harbor Children's Clinic",
            "email": "care@harborchildren.example",
            "phone": "+91 484 234 7788",
            "address_line1": "7B, Marine Drive",
            "city": "Kochi",
            "state": "Kerala",
            "postal_code": "682031",
            "country": "India",
            "timezone": "Asia/Kolkata",
            "currency": "INR",
            "tax_rate": 5,
            "invoice_prefix": "HRB",
            "patient_prefix": "HRB",
            "token_prefix": "H",
            "token_mode": "clinic",
            "working_days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
            "open_time": time(9, 0),
            "close_time": time(18, 0),
            "slot_minutes": 15,
            "consultation_fee_default": 650,
            "follow_up_fee_default": 200,
            "is_demo": True,
            "admin_name": "Dr. Lakshmi Varma",
            "admin_email": "demo.admin2@clinicflow.demo",
            "admin_password": DEMO_PASSWORD,
            "admin_phone": "+91 98470 44556",
        },
        super_admin,
    )
    # Make the demo clinic behaviours explicit and useful for the walkthrough.
    clinic1.settings.auto_invoice_on_completion = True
    clinic1.settings.reminder_email_enabled = True
    clinic1.settings.reminder_sms_enabled = True
    clinic1.settings.reminder_whatsapp_enabled = True
    clinic1.settings.receipt_footer = "Aster Family Clinic · This is a demonstration record."
    clinic2.settings.receipt_footer = "Harbor Children's Clinic · Demonstration record."
    db.session.commit()

    _seed_clinic(clinic1, admin1, "full")
    _seed_clinic(clinic2, admin2, "small")

    return (
        "Demo environment ready.\n"
        "  Clinic 1: Aster Family Clinic (Bengaluru)\n"
        "  Clinic 2: Harbor Children's Clinic (Kochi)\n"
        "  Password for all demo accounts: Demo@12345\n"
        "  Clinic admin: demo.admin@clinicflow.demo\n"
        "  Receptionist: demo.reception@clinicflow.demo\n"
        "  Doctor: demo.doctor@clinicflow.demo\n"
        "  Super admin: demo.superadmin@clinicflow.demo\n"
        "All data is fictional."
    )
