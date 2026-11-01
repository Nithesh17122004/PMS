"""Consultation, prescription and PDF tests."""
from __future__ import annotations

from tests.conftest import login, create_patient, add_schedule

from datetime import date, timedelta


def test_full_clinical_flow(client, clinic, clinic_admin, doctor, db):
    from datetime import datetime, time

    login(client, "admin@clinic.test")
    from tests.conftest import create_patient, add_schedule

    today = date.today()
    now = datetime.now()
    hour = (now.hour + 1) if now.hour < 17 else 12
    slot_time = f"{hour:02d}:00"
    add_schedule(clinic, doctor, weekday=today.weekday(), start_time=time(0, 0), end_time=time(23, 59), slot_minutes=15)
    patient = create_patient(clinic, clinic_admin, first_name="P1", phone="+919000000001")

    # book + check-in
    resp = client.post(
        "/api/appointments",
        json={"patient_id": patient.id, "doctor_id": doctor.id, "appointment_date": today.isoformat(), "start_time": slot_time},
    )
    appt_id = resp.get_json()["data"]["appointment"]["id"]
    checkin = client.post(f"/api/appointments/{appt_id}/check-in")
    token_id = checkin.get_json()["data"]["token"]["id"]

    # call the token before starting consultation
    client.post(f"/api/tokens/{token_id}/call")

    # start consultation as doctor
    login(client, "doctor@clinic.test")
    resp = client.post("/api/consultations/start", json={"token_id": token_id})
    assert resp.status_code == 200
    cid = resp.get_json()["data"]["consultation"]["id"]
    assert resp.get_json()["data"]["token"]["status"] == "in_consultation"

    # update draft
    resp = client.put(
        f"/api/consultations/{cid}",
        json={
            "symptoms": "Fever, cough",
            "diagnosis_summary": "Acute upper respiratory infection",
            "treatment_plan": "Rest and paracetamol",
            "doctor_notes": "Patient improving",
            "vitals": {"temperature": "38.5", "pulse": "92"},
            "diagnoses": [{"icd_code": "J06.9", "description": "Acute URI", "diagnosis_type": "primary"}],
        },
    )
    assert resp.status_code == 200

    # complete
    resp = client.post(
        f"/api/consultations/{cid}/complete",
        json={
            "diagnosis_summary": "Acute upper respiratory infection",
            "treatment_plan": "Rest and paracetamol",
            "follow_up_required": False,
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["consultation"]["status"] == "completed"

    # issue prescription
    resp = client.post(
        f"/api/consultations/{cid}/prescriptions",
        json={
            "items": [
                {
                    "medicine_name": "Paracetamol",
                    "strength": "500mg",
                    "form": "tablet",
                    "dosage": "500mg",
                    "frequency": "twice daily",
                    "duration_days": 5,
                    "quantity": 10,
                }
            ],
            "notes": "Take after food",
        },
    )
    assert resp.status_code == 201
    rx = resp.get_json()["data"]["prescription"]
    assert rx["prescription_code"].startswith("RX-")

    # prescription pdf
    resp = client.get(f"/api/prescriptions/{rx['id']}/pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:5] == b"%PDF-"

    # consultation invoice (billing.create)
    login(client, "admin@clinic.test")
    resp = client.post(f"/api/consultations/{cid}/invoice")
    assert resp.status_code == 201
    assert resp.get_json()["data"]["invoice"]["invoice_number"].startswith("INV-")


def test_prescription_authorization(client, clinic, clinic_admin, doctor, db):
    # A doctor cannot issue a prescription for another doctor's consultation.
    from backend.auth.security import hash_password
    from backend.models import User, Doctor, Consultation
    from backend.permissions.rbac import create_clinic_roles

    roles = create_clinic_roles(clinic.id, __import__("backend.permissions.rbac", fromlist=["seed_permissions"]).seed_permissions())
    # create second doctor user
    u2 = User(clinic_id=clinic.id, role_id=roles["doctor"].id, email="doctor2@clinic.test", password_hash=hash_password("Test@1234567"), full_name="Dr. Two", is_active=True)
    db.session.add(u2)
    db.session.flush()
    d2 = Doctor(clinic_id=clinic.id, doctor_code="DR-2", full_name="Dr. Two", specialization="GP", user_id=u2.id, is_active=True, is_available=True)
    db.session.add(d2)
    db.session.flush()
    u2.doctor_profile = d2
    db.session.commit()

    # create a consultation by doctor1 via standalone draft
    login(client, "doctor@clinic.test")
    from tests.conftest import create_patient

    patient = create_patient(clinic, clinic_admin, first_name="P1", phone="+919000000001")
    resp = client.post("/api/consultations", json={"patient_id": patient.id, "doctor_id": doctor.id})
    cid = resp.get_json()["data"]["consultation"]["id"]
    # update + complete as doctor1
    client.put(f"/api/consultations/{cid}", json={"diagnosis_summary": "URI", "treatment_plan": "Rest"})
    client.post(f"/api/consultations/{cid}/complete", json={"diagnosis_summary": "URI", "treatment_plan": "Rest", "follow_up_required": False})

    # doctor2 tries to issue prescription -> 403
    login(client, "doctor2@clinic.test")
    resp = client.post(
        f"/api/consultations/{cid}/prescriptions",
        json={"items": [{"medicine_name": "Paracetamol", "dosage": "500mg", "frequency": "twice daily"}]},
    )
    assert resp.status_code == 403
