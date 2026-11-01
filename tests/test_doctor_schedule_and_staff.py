"""Regression tests for doctor schedules and staff-account workflows."""
from __future__ import annotations

import pytest

from backend.auth.security import verify_password
from backend.models import Doctor, DoctorSchedule, User
from backend.permissions.rbac import create_clinic_roles
from tests.conftest import login


def _schedule_payload(weekday=0, **overrides):
    payload = {
        "weekday": weekday,
        "start_time": "09:00",
        "end_time": "12:00",
        "slot_minutes": 15,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("weekday", range(7))
def test_doctor_schedule_accepts_each_weekday(client, clinic_admin, doctor, weekday):
    login(client, "admin@clinic.test")
    response = client.post(
        f"/api/doctors/{doctor.id}/schedules",
        json=_schedule_payload(weekday),
    )
    assert response.status_code == 201, response.get_json()
    saved = DoctorSchedule.query.filter_by(doctor_id=doctor.id, weekday=weekday).one()
    assert saved.weekday == weekday


@pytest.mark.parametrize("weekday", [-1, 7, "Monday", 1.5, True])
def test_doctor_schedule_rejects_invalid_weekday(client, clinic_admin, doctor, weekday):
    login(client, "admin@clinic.test")
    response = client.post(
        f"/api/doctors/{doctor.id}/schedules",
        json=_schedule_payload(weekday),
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_time": ""},
        {"start_time": None},
        {"end_time": ""},
        {"end_time": None},
        {"start_time": "13:00", "end_time": "12:00"},
        {"start_time": "09:00", "end_time": "09:00"},
        {"start_time": "bad", "end_time": "12:00"},
    ],
)
def test_doctor_schedule_rejects_missing_or_invalid_times(client, clinic_admin, doctor, overrides):
    login(client, "admin@clinic.test")
    response = client.post(
        f"/api/doctors/{doctor.id}/schedules",
        json=_schedule_payload(**overrides),
    )
    assert response.status_code == 422


@pytest.mark.parametrize("slot_minutes", [0, 4, 241, 1.5, "invalid"])
def test_doctor_schedule_rejects_invalid_slot_duration(client, clinic_admin, doctor, slot_minutes):
    login(client, "admin@clinic.test")
    response = client.post(
        f"/api/doctors/{doctor.id}/schedules",
        json=_schedule_payload(slot_minutes=slot_minutes),
    )
    assert response.status_code == 422


def test_doctor_schedule_rejects_overlapping_active_shift(client, clinic_admin, doctor):
    login(client, "admin@clinic.test")
    first = client.post(
        f"/api/doctors/{doctor.id}/schedules",
        json=_schedule_payload(weekday=2, start_time="09:00", end_time="12:00"),
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/doctors/{doctor.id}/schedules",
        json=_schedule_payload(weekday=2, start_time="11:00", end_time="13:00"),
    )
    assert second.status_code == 409


def test_inactive_schedule_does_not_conflict_with_active_shift(client, clinic_admin, doctor):
    login(client, "admin@clinic.test")
    first = client.post(
        f"/api/doctors/{doctor.id}/schedules",
        json=_schedule_payload(weekday=3),
    )
    assert first.status_code == 201
    inactive = client.post(
        f"/api/doctors/{doctor.id}/schedules",
        json=_schedule_payload(weekday=3, is_active=False),
    )
    assert inactive.status_code == 201


def test_staff_admin_can_create_user_with_securely_hashed_password(client, clinic_admin, roles):
    login(client, "admin@clinic.test")
    response = client.post(
        "/api/clinic/staff",
        json={
            "full_name": "Nurse Test",
            "email": "nurse.new@example.test",
            "role_id": roles["nurse"].id,
            "password": "Strong@Test123",
            "designation": "Ward Nurse",
        },
    )
    assert response.status_code == 201, response.get_json()
    user = User.query.filter_by(email="nurse.new@example.test").one()
    assert user.role.slug == "nurse"
    assert user.password_hash != "Strong@Test123"
    assert verify_password("Strong@Test123", user.password_hash)
    assert user.must_change_password is False


def test_staff_creation_generates_temporary_password_when_blank(client, clinic_admin, roles):
    login(client, "admin@clinic.test")
    response = client.post(
        "/api/clinic/staff",
        json={
            "full_name": "Reception Temp",
            "email": "reception.temp@example.test",
            "role_id": roles["receptionist"].id,
            "password": "",
        },
    )
    assert response.status_code == 201, response.get_json()
    user = User.query.filter_by(email="reception.temp@example.test").one()
    temporary_password = response.get_json()["data"]["staff"]["temporary_password"]
    assert verify_password(temporary_password, user.password_hash)
    assert user.must_change_password is True


@pytest.mark.parametrize(
    "payload",
    [
        {"full_name": "", "email": "valid@example.test", "role_id": "x"},
        {"full_name": "Valid Name", "email": "", "role_id": "x"},
        {"full_name": "Valid Name", "email": "not-an-email", "role_id": "x"},
        {"full_name": "Valid Name", "email": "valid@example.test", "role_id": ""},
    ],
)
def test_staff_creation_rejects_missing_or_invalid_required_fields(client, clinic_admin, payload):
    login(client, "admin@clinic.test")
    response = client.post("/api/clinic/staff", json=payload)
    assert response.status_code == 422


def test_staff_creation_rejects_duplicate_email(client, clinic_admin, receptionist, roles):
    login(client, "admin@clinic.test")
    response = client.post(
        "/api/clinic/staff",
        json={
            "full_name": "Duplicate",
            "email": receptionist.email,
            "role_id": roles["nurse"].id,
        },
    )
    assert response.status_code == 409


def test_staff_creation_rejects_unknown_or_foreign_clinic_role(client, clinic_admin, clinic_b, roles, db):
    login(client, "admin@clinic.test")
    unknown = client.post(
        "/api/clinic/staff",
        json={
            "full_name": "Unknown Role",
            "email": "unknown.role@example.test",
            "role_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert unknown.status_code == 422

    other_roles = create_clinic_roles(clinic_b.id)
    db.session.commit()
    foreign = client.post(
        "/api/clinic/staff",
        json={
            "full_name": "Foreign Role",
            "email": "foreign.role@example.test",
            "role_id": other_roles["nurse"].id,
        },
    )
    assert foreign.status_code == 422


def test_staff_endpoint_rejects_doctor_role_and_doctor_module_creates_linked_account(client, clinic_admin, roles, db):
    login(client, "admin@clinic.test")
    rejected = client.post(
        "/api/clinic/staff",
        json={
            "full_name": "Doctor Account",
            "email": "doctor.staff@example.test",
            "role_id": roles["doctor"].id,
        },
    )
    assert rejected.status_code == 422

    created = client.post(
        "/api/doctors",
        json={
            "full_name": "Dr Login Link",
            "specialization": "General Medicine",
            "email": "doctor.link@example.test",
            "password": "Strong@Test123",
        },
    )
    assert created.status_code == 201, created.get_json()
    doctor_id = created.get_json()["data"]["doctor"]["id"]
    doctor = db.session.get(Doctor, doctor_id)
    linked_user = db.session.get(User, doctor.user_id)
    assert linked_user.role.slug == "doctor"
    assert linked_user.doctor_profile.id == doctor.id


def test_doctor_creation_does_not_link_non_doctor_user(client, clinic_admin, receptionist):
    login(client, "admin@clinic.test")
    response = client.post(
        "/api/doctors",
        json={
            "full_name": "Doctor Duplicate",
            "specialization": "General Medicine",
            "email": receptionist.email,
        },
    )
    assert response.status_code == 422


def test_staff_creation_requires_staff_manage_permission(client, receptionist, roles):
    login(client, "reception@clinic.test")
    response = client.post(
        "/api/clinic/staff",
        json={
            "full_name": "Unauthorized",
            "email": "unauthorized@example.test",
            "role_id": roles["nurse"].id,
        },
    )
    assert response.status_code == 403


def test_staff_creation_requires_authentication(client):
    response = client.post(
        "/api/clinic/staff",
        json={
            "full_name": "Unauthenticated",
            "email": "no.auth@example.test",
            "role_id": "id",
        },
    )
    assert response.status_code == 401


def test_doctor_schedule_requires_doctors_manage_permission(client, receptionist, doctor):
    login(client, "reception@clinic.test")
    response = client.post(
        f"/api/doctors/{doctor.id}/schedules",
        json=_schedule_payload(),
    )
    assert response.status_code == 403
