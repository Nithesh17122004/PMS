"""Appointment booking, conflict, reschedule, check-in and cancel tests."""
from __future__ import annotations

from tests.conftest import login, create_patient, add_schedule

from datetime import date, datetime, time, timedelta


def test_create_appointment_requires_schedule(client, clinic, clinic_admin, doctor, db):
    from datetime import date, timedelta, time

    login(client, "admin@clinic.test")
    tomorrow = date.today() + timedelta(days=1)
    from tests.conftest import add_schedule

    add_schedule(clinic, doctor, weekday=tomorrow.weekday(), start_time=time(9, 0), end_time=time(18, 0), slot_minutes=15)

    from tests.conftest import create_patient

    patient = create_patient(clinic, clinic_admin)
    resp = client.post(
        "/api/appointments",
        json={
            "patient_id": patient.id,
            "doctor_id": doctor.id,
            "appointment_date": tomorrow.isoformat(),
            "start_time": "09:00",
        },
    )
    assert resp.status_code == 201
    body = resp.get_json()["data"]
    assert body["appointment"]["appointment_code"].startswith("APT-")
    assert body["appointment"]["status"] == "confirmed"


def test_double_booking_same_slot_conflicts(client, clinic, clinic_admin, receptionist, doctor, db):
    from datetime import date, timedelta, time

    from tests.conftest import add_schedule, create_patient

    tomorrow = date.today() + timedelta(days=1)
    add_schedule(clinic, doctor, weekday=tomorrow.weekday(), start_time=time(9, 0), end_time=time(18, 0), slot_minutes=15)
    patient = create_patient(clinic, clinic_admin)
    login(client, "reception@clinic.test")
    client.post(
        "/api/appointments",
        json={"patient_id": patient.id, "doctor_id": doctor.id, "appointment_date": tomorrow.isoformat(), "start_time": "09:00"},
    )
    resp = client.post(
        "/api/appointments",
        json={"patient_id": patient.id, "doctor_id": doctor.id, "appointment_date": tomorrow.isoformat(), "start_time": "09:00"},
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "conflict"


def test_reschedule_and_cancel(client, clinic, clinic_admin, doctor, db):
    from datetime import date, timedelta, time

    from tests.conftest import add_schedule, create_patient

    tomorrow = date.today() + timedelta(days=1)
    day_after = tomorrow + timedelta(days=1)
    add_schedule(clinic, doctor, weekday=tomorrow.weekday(), start_time=time(9, 0), end_time=time(18, 0), slot_minutes=15)
    add_schedule(clinic, doctor, weekday=day_after.weekday(), start_time=time(9, 0), end_time=time(18, 0), slot_minutes=15)
    patient = create_patient(clinic, clinic_admin)
    login(client, "admin@clinic.test")
    resp = client.post(
        "/api/appointments",
        json={"patient_id": patient.id, "doctor_id": doctor.id, "appointment_date": tomorrow.isoformat(), "start_time": "09:00"},
    )
    appt_id = resp.get_json()["data"]["appointment"]["id"]

    resp = client.post(
        f"/api/appointments/{appt_id}/reschedule",
        json={"appointment_date": day_after.isoformat(), "start_time": "09:15"},
    )
    assert resp.status_code == 200
    new_id = resp.get_json()["data"]["appointment"]["id"]
    assert new_id != appt_id

    resp = client.post(f"/api/appointments/{new_id}/cancel", json={"reason": "Patient moved to walk-in"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["appointment"]["status"] == "cancelled"


def test_check_in_generates_token(client, clinic, clinic_admin, doctor, db):
    from datetime import datetime, time, timedelta

    from tests.conftest import add_schedule, create_patient

    today = date.today() if False else __import__("datetime").date.today()
    now = datetime.now()
    hour = (now.hour + 1) if now.hour < 17 else 12
    slot_time = f"{hour:02d}:00"
    add_schedule(clinic, doctor, weekday=today.weekday(), start_time=time(0, 0), end_time=time(23, 59), slot_minutes=15)
    patient = create_patient(clinic, clinic_admin)
    login(client, "admin@clinic.test")
    resp = client.post(
        "/api/appointments",
        json={"patient_id": patient.id, "doctor_id": doctor.id, "appointment_date": today.isoformat(), "start_time": slot_time},
    )
    appt_id = resp.get_json()["data"]["appointment"]["id"]
    resp = client.post(f"/api/appointments/{appt_id}/check-in")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["token"] is not None
    assert data["token"]["status"] == "waiting"
    assert data["appointment"]["status"] == "checked_in"
