"""Public display and public endpoint tests."""
from __future__ import annotations

from tests.conftest import login, create_patient, add_schedule


def test_public_display_data(client, clinic, clinic_admin, doctor, db):
    from tests.conftest import create_patient, add_schedule, login

    today = date.today() if False else __import__("datetime").date.today()
    add_schedule(clinic, doctor, weekday=today.weekday(), start_time=__import__("datetime").time(9, 0), end_time=__import__("datetime").time(18, 0), slot_minutes=15)
    login(client, "admin@clinic.test")
    patient = create_patient(clinic, clinic_admin, first_name="P1", phone="+919000000001")
    client.post("/api/tokens", json={"patient_id": patient.id, "doctor_id": doctor.id})

    resp = client.get(f"/api/public/display/{clinic.display_key}")
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["clinic"]["name"] == clinic.name
    assert "queues" in body
    assert "now_serving" in body
    # Token numbers only, no patient names in payload.
    blob = str(body)
    assert "P1" not in blob


def test_public_display_unknown_key_returns_404(client):
    resp = client.get("/api/public/display/DOESNOTEXIST1234567890")
    assert resp.status_code == 404


def test_public_display_disabled_returns_404(client, clinic, db):
    clinic.settings.public_display_enabled = False
    db.session.commit()
    resp = client.get(f"/api/public/display/{clinic.display_key}")
    assert resp.status_code == 404
