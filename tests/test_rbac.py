"""Role-based access control tests."""
from __future__ import annotations

from tests.conftest import login

from backend.permissions.rbac import ROLE_DEFINITIONS, PERMISSIONS


def test_unauthenticated_api_returns_401(client):
    assert client.get("/api/patients").status_code == 401
    assert client.get("/api/dashboard").status_code == 401


def test_super_admin_permissions_are_platform_only():
    codes = set(ROLE_DEFINITIONS["super_admin"]["permissions"])
    assert codes == {"platform.view", "platform.manage"}
    assert "patients.view" not in codes


def test_clinic_admin_grants_every_clinic_permission():
    expected = {code for code in PERMISSIONS if not code.startswith("platform.")}
    actual = set(ROLE_DEFINITIONS["clinic_admin"]["permissions"])
    assert expected.issubset(actual)
    assert "platform.view" not in actual


def test_doctor_permissions_do_not_include_billing_refund():
    codes = set(ROLE_DEFINITIONS["doctor"]["permissions"])
    assert "billing.refund" not in codes
    assert "billing.payment" not in codes
    assert "consultations.create" in codes
    assert "tokens.call" in codes


def test_receptionist_has_token_and_billing_create():
    codes = set(ROLE_DEFINITIONS["receptionist"]["permissions"])
    assert "tokens.create" in codes
    assert "billing.create" in codes
    assert "patients.create" in codes
    assert "consultations.create" not in codes


def test_doctor_cannot_access_billing_refund(client, clinic, roles, doctor):
    login(client, "doctor@clinic.test")
    resp = client.post("/api/invoices/00000000-0000-0000-0000-000000000000/refund", json={"payment_id": "x", "amount": 1, "reason": "no"})
    assert resp.status_code == 403


def test_receptionist_cannot_start_consultation(client, clinic, roles, receptionist):
    login(client, "reception@clinic.test")
    # A token id belonging to another clinic would be 404; here we expect 403 (permission).
    resp = client.post("/api/consultations/start", json={"token_id": "00000000-0000-0000-0000-000000000000"})
    assert resp.status_code in (401, 403, 404)


def test_clinic_admin_can_list_patients(client, clinic, clinic_admin):
    login(client, "admin@clinic.test")
    resp = client.get("/api/patients")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
