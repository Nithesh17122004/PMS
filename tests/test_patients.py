"""Patient registration, search, merge and encryption tests."""
from __future__ import annotations

from tests.conftest import login, create_patient

from sqlalchemy import text

from backend.utils.crypto import decrypt_value


def test_create_patient_assigns_code_and_encrypts_phone(client, clinic, clinic_admin, db):
    login(client, "admin@clinic.test")
    resp = client.post(
        "/api/patients",
        json={
            "first_name": "Jane",
            "last_name": "Doe",
            "gender": "female",
            "date_of_birth": "1992-05-10",
            "phone": "+919876543210",
            "email": "jane@example.com",
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]["patient"]
    assert data["patient_code"].startswith("P-")
    assert data["phone_masked"].endswith("3210")

    # Field is encrypted at rest.
    row = db.session.execute(
        text("SELECT phone FROM patients WHERE id = :id"), {"id": data["id"]}
    ).scalar()
    assert row is not None
    assert row != "+919876543210"
    assert decrypt_value(row) == "+919876543210"


def test_duplicate_patient_conflict(client, clinic, clinic_admin):
    login(client, "admin@clinic.test")
    payload = {
        "first_name": "Jane",
        "last_name": "Doe",
        "gender": "female",
        "date_of_birth": "1992-05-10",
        "phone": "+919876543210",
    }
    assert client.post("/api/patients", json=payload).status_code == 201
    resp = client.post("/api/patients", json=payload)
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "conflict"


def test_patient_search_by_phone(client, clinic, clinic_admin, db):
    login(client, "admin@clinic.test")
    client.post(
        "/api/patients",
        json={
            "first_name": "Jane",
            "last_name": "Doe",
            "gender": "female",
            "date_of_birth": "1992-05-10",
            "phone": "+919876543210",
        },
    )
    resp = client.post("/api/patients/search", json={"query": "9876543210", "limit": 10})
    assert resp.status_code == 200
    rows = resp.get_json()["data"]["patients"]
    assert rows
    assert any(r["first_name"] == "Jane" for r in rows)


def test_merge_patients(client, clinic, clinic_admin, db):
    from backend.models import Patient

    login(client, "admin@clinic.test")
    r1 = client.post(
        "/api/patients",
        json={
            "first_name": "John",
            "last_name": "Smith",
            "gender": "male",
            "date_of_birth": "1985-01-01",
            "phone": "+919111111111",
        },
    )
    r2 = client.post(
        "/api/patients",
        json={
            "first_name": "Jon",
            "last_name": "Smith",
            "gender": "male",
            "date_of_birth": "1985-01-01",
            "phone": "+919222222222",
            "override_duplicate": True,
            "duplicate_reason": "Different spelling entered at reception",
        },
    )
    # second may conflict with first via name+dob; use override_duplicate to force.
    if r2.status_code != 201:
        r2 = client.post(
            "/api/patients",
            json={
                "first_name": "Jon",
                "last_name": "Smith",
                "gender": "male",
                "date_of_birth": "1985-01-01",
                "phone": "+919222222222",
                "override_duplicate": True,
                "duplicate_reason": "Different spelling entered at reception",
            },
        )
    assert r1.status_code == 201
    assert r2.status_code == 201
    source_id = r2.get_json()["data"]["patient"]["id"]
    target_id = r1.get_json()["data"]["patient"]["id"]
    resp = client.post(
        f"/api/patients/{source_id}/merge",
        json={"target_id": target_id, "reason": "Same patient registered twice"},
    )
    assert resp.status_code == 200
    source = db.session.get(Patient, source_id)
    assert source.merged_into_id == target_id
