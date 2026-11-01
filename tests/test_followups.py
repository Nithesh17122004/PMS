"""Follow-up plans, arrival token generation and reminders."""
from __future__ import annotations

from tests.conftest import login, create_patient

from datetime import date, timedelta


def test_followup_create_arrive_complete(client, clinic, clinic_admin, doctor, db):
    login(client, "admin@clinic.test")
    p1 = create_patient(clinic, clinic_admin, first_name="P1", phone="+919000000001") if False else None
    from tests.conftest import create_patient

    p1 = create_patient(clinic, clinic_admin, first_name="P1", phone="+919000000001")
    resp = client.post(
        "/api/followups",
        json={
            "patient_id": p1.id,
            "doctor_id": doctor.id,
            "due_date": (date.today() + timedelta(days=7)).isoformat(),
            "instructions": "Review symptoms",
        },
    )
    assert resp.status_code == 201
    plan_id = resp.get_json()["data"]["followup"]["id"] if "followup" in resp.get_json()["data"] else resp.get_json()["data"]["plan"]["id"]

    # arrive -> token generated
    resp = client.post(f"/api/followups/{plan_id}/arrive")
    assert resp.status_code == 201
    assert resp.get_json()["data"]["token"]["status"] == "waiting"

    # complete follow-up
    resp = client.post(f"/api/followups/{plan_id}/complete")
    assert resp.status_code == 200


def test_followup_reminder_requires_consent(client, clinic, clinic_admin, doctor, db):
    login(client, "admin@clinic.test")
    from tests.conftest import create_patient

    p1 = create_patient(clinic, clinic_admin, first_name="P1", phone="+919000000001")
    resp = client.post(
        "/api/followups",
        json={
            "patient_id": p1.id,
            "doctor_id": doctor.id,
            "due_date": (date.today() + timedelta(days=7)).isoformat(),
            "instructions": "Review symptoms",
        },
    )
    plan_id = resp.get_json()["data"].get("followup", {}).get("id") or resp.get_json()["data"].get("plan", {}).get("id")
    # patient has no email consent -> reminder should fail validation
    resp = client.post(f"/api/followups/{plan_id}/remind", json={"channel": "email"})
    assert resp.status_code in (400, 422)


def test_followup_dashboard_counts(client, clinic, clinic_admin, doctor, db):
    login(client, "admin@clinic.test")
    from tests.conftest import create_patient

    p1 = create_patient(clinic, clinic_admin, first_name="P1", phone="+919000000001")
    client.post(
        "/api/followups",
        json={
            "patient_id": p1.id,
            "doctor_id": doctor.id,
            "due_date": (date.today() + timedelta(days=7)).isoformat(),
            "instructions": "Review symptoms",
        },
    )
    resp = client.get("/api/followups/dashboard")
    assert resp.status_code == 200
    assert "counts" in resp.get_json()["data"]

def test_doctor_can_register_followup_arrival_and_generate_token(client, clinic, clinic_admin, doctor):
    login(client, "doctor@clinic.test")
    patient = create_patient(clinic, clinic_admin, first_name="Follow", phone="+919000000098")
    created = client.post(
        "/api/followups",
        json={
            "patient_id": patient.id,
            "doctor_id": doctor.id,
            "due_date": date.today().isoformat(),
            "instructions": "Review response to treatment",
        },
    )
    assert created.status_code == 201, created.get_json()
    plan_id = created.get_json()["data"]["followup"]["id"]

    arrived = client.post(f"/api/followups/{plan_id}/arrive", json={})
    assert arrived.status_code == 201, arrived.get_json()
    assert arrived.get_json()["data"]["token"]["visit_type"] == "follow_up"
