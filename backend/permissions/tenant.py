from __future__ import annotations

from flask import g

from ..extensions import db
from ..models import Clinic, Doctor, Patient, User
from ..utils.errors import ForbiddenError, NotFoundError


def current_clinic() -> Clinic:
    clinic = getattr(g, "clinic", None)
    if clinic is None:
        raise ForbiddenError("This action requires a clinic account.")
    return clinic


def current_user() -> User:
    user = getattr(g, "user", None)
    if user is None:
        raise ForbiddenError("Authentication required.")
    return user


def current_doctor(required: bool = True) -> Doctor | None:
    user = current_user()
    doctor = user.doctor_profile
    if required and doctor is None:
        raise ForbiddenError("This action is only available to a doctor account.")
    return doctor


def scoped_query(model):
    """Query a clinic-scoped model, always filtered to the active clinic."""
    clinic = current_clinic()
    if not hasattr(model, "clinic_id"):
        raise ValueError(f"{model.__name__} is not clinic scoped")
    return model.query.filter(model.clinic_id == clinic.id)


def get_scoped_or_404(model, record_id: str, *, active_only: bool = False):
    clinic = current_clinic()
    record = db.session.get(model, record_id)
    if record is None or getattr(record, "clinic_id", None) != clinic.id:
        raise NotFoundError()
    if active_only and hasattr(record, "is_active") and not record.is_active:
        raise NotFoundError()
    return record


def get_patient(patient_id: str, active_only: bool = False) -> Patient:
    return get_scoped_or_404(Patient, patient_id, active_only=active_only)


def doctor_queue_scope(doctor_id: str | None = None) -> str | None:
    """Return a doctor id to constrain queue actions, or None for clinic-wide access."""
    user = current_user()
    if "tokens.manage_all" in getattr(g, "permissions", set()):
        return doctor_id
    doctor = user.doctor_profile
    if doctor is None:
        raise ForbiddenError("Queue actions are limited to assigned staff.")
    if doctor_id and doctor_id != doctor.id:
        raise ForbiddenError("Doctors may only manage their own queue.")
    return doctor.id


def assert_clinic_record(record) -> None:
    clinic = current_clinic()
    if record is None or getattr(record, "clinic_id", None) != clinic.id:
        raise NotFoundError()
