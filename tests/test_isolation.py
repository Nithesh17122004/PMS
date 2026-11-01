"""Multi-tenant isolation tests."""
from __future__ import annotations

from tests.conftest import login, create_patient

from backend.services.patient_service import create_patient as create_patient_service


def create_patient_in(clinic, actor, first_name="John", phone="+919876543210"):
    return create_patient_service(
        clinic=clinic,
        actor=actor,
        payload={
            "first_name": first_name,
            "last_name": "Doe",
            "gender": "male",
            "date_of_birth": "1990-01-01",
            "age_years": None,
            "phone": phone,
            "email": f"{first_name}@example.com",
        },
    )


def test_patients_isolated_between_clinics(client, clinic, clinic_b, clinic_admin, db):
    # Clinic A admin creates a patient.
    create_patient_in(clinic, clinic_admin, first_name="John", phone="+919876543210")
    # Clinic B admin logs in and must not see Clinic A's patient.
    # Create a clinic B admin user.
    from backend.models import ClinicSetting, User
    from backend.permissions.rbac import create_clinic_roles

    roles_b = create_clinic_roles(clinic_b.id, __import__("backend.permissions.rbac", fromlist=["seed_permissions"]).seed_permissions())
    from backend.auth.security import hash_password

    admin_b = User(
        clinic_id=clinic_b.id,
        role_id=roles_b["clinic_admin"].id,
        email="admin_b@harbor.test",
        password_hash=hash_password("Test@1234567"),
        full_name="Clinic B Admin",
        is_active=True,
    )
    db.session.add(admin_b)
    db.session.commit()

    login(client, "admin_b@harbor.test")
    resp = client.get("/api/patients")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data == [] or all(p.get("full_name") != "John Doe" for p in data)

    login(client, "admin@clinic.test")
    resp = client.get("/api/patients")
    assert resp.status_code == 200
    rows = resp.get_json()["data"]
    assert any(p.get("full_name") == "John Doe" for p in rows)


def test_token_for_foreign_patient_is_rejected(client, clinic, clinic_b, clinic_admin, doctor, db):
    from backend.models import Doctor as DoctorModel
    from backend.permissions.rbac import create_clinic_roles

    # Create a clinic B doctor.
    roles_b = create_clinic_roles(clinic_b.id, __import__("backend.permissions.rbac", fromlist=["seed_permissions"]).seed_permissions())
    from backend.auth.security import hash_password
    from backend.models import User

    admin_b = User(clinic_id=clinic_b.id, role_id=roles_b["clinic_admin"].id, email="admin_b2@harbor.test", password_hash=hash_password("Test@1234567"), full_name="B Admin", is_active=True)
    db.session.add(admin_b)
    db.session.commit()

    # Create a patient in clinic A.
    patient_a = create_patient_in(clinic, clinic_admin, first_name="Alice", phone="+911234567890")

    # Clinic B doctor logs in and tries to generate a token for clinic A's patient -> patient not found.
    # Need a doctor in clinic B.
    doc_user = User(clinic_id=clinic_b.id, role_id=roles_b["doctor"].id, email="doc_b@harbor.test", password_hash=hash_password("Test@1234567"), full_name="Dr B", is_active=True)
    db.session.add(doc_user)
    db.session.flush()
    doc_b = DoctorModel(clinic_id=clinic_b.id, doctor_code="DR-B", full_name="Dr B", specialization="GP", user_id=doc_user.id, is_active=True, is_available=True)
    db.session.add(doc_b)
    db.session.flush()
    doc_user.doctor_profile = doc_b
    db.session.commit()

    login(client, "doc_b@harbor.test")
    resp = client.post("/api/tokens", json={"patient_id": patient_a.id, "doctor_id": doc_b.id})
    assert resp.status_code in (403, 404)
