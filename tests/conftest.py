"""Shared pytest fixtures for the ClinicFlow backend test suite."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pytest
from flask import g

from backend import create_app
from backend.auth.security import generate_reset_token, hash_password
from backend.extensions import db as _db
from backend.models import (
    Clinic,
    ClinicSetting,
    Doctor,
    DoctorSchedule,
    PasswordResetToken,
    User,
)
from backend.permissions.rbac import create_clinic_roles, create_super_admin_role, seed_permissions
from backend.services.patient_service import create_patient as create_patient_service

TEST_PASSWORD = "Test@1234567"
NEW_PASSWORD = "NewPass@1234567"


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        seed_permissions()
        create_super_admin_role()
        yield app
        _db.session.rollback()
        _db.session.close()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    from backend.extensions import db as _db

    return _db


@pytest.fixture()
def clinic(db):
    clinic = Clinic(
        name="Aster Family Clinic",
        slug="aster-family",
        email="admin@aster.example",
        phone="+910000000000",
        is_active=True,
    )
    db.session.add(clinic)
    db.session.flush()
    db.session.add(
        ClinicSetting(
            clinic_id=clinic.id,
            timezone="Asia/Kolkata",
            currency="INR",
            token_mode="doctor",
            working_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        )
    )
    db.session.commit()
    db.session.refresh(clinic)
    return clinic


@pytest.fixture()
def clinic_b(db):
    clinic = Clinic(
        name="Harbor Children's Clinic",
        slug="harbor-childrens",
        email="admin@harbor.example",
        phone="+910000000001",
        is_active=True,
    )
    db.session.add(clinic)
    db.session.flush()
    db.session.add(
        ClinicSetting(
            clinic_id=clinic.id,
            timezone="Asia/Kolkata",
            currency="INR",
            token_mode="doctor",
            working_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        )
    )
    db.session.commit()
    db.session.refresh(clinic)
    return clinic


@pytest.fixture()
def roles(db, clinic):
    return create_clinic_roles(clinic.id, seed_permissions())


def make_user(clinic, role, *, email, full_name="Staff", password=TEST_PASSWORD, designation="Staff"):
    user = User(
        clinic_id=clinic.id,
        role_id=role.id,
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        designation=designation,
        is_active=True,
        must_change_password=False,
    )
    _db.session.add(user)
    _db.session.flush()
    return user


@pytest.fixture()
def clinic_admin(clinic, roles):
    return make_user(clinic, roles["clinic_admin"], email="admin@clinic.test", full_name="Clinic Admin")


@pytest.fixture()
def receptionist(clinic, roles):
    return make_user(clinic, roles["receptionist"], email="reception@clinic.test", full_name="Receptionist")


@pytest.fixture()
def doctor(clinic, roles, db):
    user = make_user(clinic, roles["doctor"], email="doctor@clinic.test", full_name="Dr. Rao")
    doctor = Doctor(
        clinic_id=clinic.id,
        doctor_code="DR-1",
        full_name="Dr. Rao",
        specialization="General Medicine",
        user_id=user.id,
        is_active=True,
        is_available=True,
        consultation_fee=500,
        follow_up_fee=200,
    )
    db.session.add(doctor)
    db.session.flush()
    user.doctor_profile = doctor
    db.session.commit()
    return doctor


@pytest.fixture()
def doctor_user(doctor):
    return doctor.user


def login(client, email, password=TEST_PASSWORD):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    body = resp.get_json(silent=True) or {}
    if resp.status_code != 200 or not body.get("ok"):
        raise AssertionError(f"login failed: {resp.status_code} {body}")
    return body["data"]


def add_schedule(clinic, doctor, *, weekday=None, start_time=time(9, 0), end_time=time(18, 0), slot_minutes=15):
    if weekday is None:
        from datetime import datetime as _dt

        weekday = _dt.now().weekday()
    schedule = DoctorSchedule(
        clinic_id=clinic.id,
        doctor_id=doctor.id,
        weekday=weekday,
        start_time=start_time,
        end_time=end_time,
        slot_minutes=slot_minutes,
        is_active=True,
    )
    _db.session.add(schedule)
    _db.session.commit()
    _db.session.refresh(doctor)
    return schedule


def create_patient(clinic, actor, *, first_name="John", last_name="Doe", phone="+919876543210", gender="male", dob="1990-01-01"):
    patient = create_patient_service(
        clinic=clinic,
        actor=actor,
        payload={
            "first_name": first_name,
            "last_name": last_name,
            "gender": gender,
            "date_of_birth": dob,
            "age_years": None,
            "phone": phone,
            "email": f"{first_name}.{last_name}@example.com",
        },
    )
    _db.session.refresh(patient)
    return patient


def auth_context(app, user, clinic):
    """Push an app context with tenant/auth context for service-level calls."""
    ctx = app.test_request_context("/api/tokens")
    ctx.push()
    g.user = user
    g.clinic = clinic
    g.permissions = user.permission_codes()
    return ctx
