"""First-time setup flow tests."""
from __future__ import annotations

from backend.auth.security import verify_password
from backend.models import User, Clinic


def test_first_visit_redirects_to_setup(client):
    resp = client.get("/")
    assert resp.status_code in (301, 302)
    assert "/setup" in (resp.headers.get("Location") or "")


def test_setup_page_renders(client):
    resp = client.get("/setup")
    assert resp.status_code == 200
    assert b"First-time setup" in resp.data or b"setup" in resp.data.lower()


def test_setup_creates_clinic_and_admin(client, db):
    resp = client.post(
        "/api/setup",
        json={
            "clinic_name": "Test Clinic",
            "clinic_email": "clinic@test.example",
            "admin_name": "Admin User",
            "admin_email": "admin@test.example",
            "password": "Test@1234567",
            "confirm_password": "Test@1234567",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["data"]["redirect"] == "/app"
    user = User.query.filter_by(email="admin@test.example").first()
    assert user is not None
    assert user.is_active is True
    assert verify_password("Test@1234567", user.password_hash) is True
    assert user.role.slug == "clinic_admin"
    clinic = Clinic.query.filter_by(email="clinic@test.example").first()
    assert clinic is not None
    assert clinic.settings is not None
    # auto-logged in
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["data"]["user"]["email"] == "admin@test.example"


def test_setup_disabled_after_first_user(client, db):
    # first setup
    client.post(
        "/api/setup",
        json={
            "clinic_name": "Test Clinic",
            "clinic_email": "clinic@test.example",
            "admin_name": "Admin User",
            "admin_email": "admin@test.example",
            "password": "Test@1234567",
            "confirm_password": "Test@1234567",
        },
    )
    # second attempt
    resp = client.post(
        "/api/setup",
        json={
            "clinic_name": "Another Clinic",
            "clinic_email": "another@test.example",
            "admin_name": "Another Admin",
            "admin_email": "anotheradmin@test.example",
            "password": "Test@1234567",
            "confirm_password": "Test@1234567",
        },
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "conflict"
    # setup page redirects to login
    resp = client.get("/setup")
    assert resp.status_code in (301, 302)
    assert "/login" in (resp.headers.get("Location") or "")


def test_setup_requires_password_match(client):
    resp = client.post(
        "/api/setup",
        json={
            "clinic_name": "Test Clinic",
            "clinic_email": "clinic@test.example",
            "admin_name": "Admin User",
            "admin_email": "admin@test.example",
            "password": "Test@1234567",
            "confirm_password": "Different@1234567",
        },
    )
    assert resp.status_code == 422


def test_setup_rejects_weak_password(client):
    resp = client.post(
        "/api/setup",
        json={
            "clinic_name": "Test Clinic",
            "clinic_email": "clinic@test.example",
            "admin_name": "Admin User",
            "admin_email": "admin@test.example",
            "password": "weak",
            "confirm_password": "weak",
        },
    )
    assert resp.status_code == 422


def test_login_works_after_setup(client, db):
    client.post(
        "/api/setup",
        json={
            "clinic_name": "Test Clinic",
            "clinic_email": "clinic@test.example",
            "admin_name": "Admin User",
            "admin_email": "admin@test.example",
            "password": "Test@1234567",
            "confirm_password": "Test@1234567",
        },
    )
    client.post("/api/auth/logout")
    resp = client.post("/api/auth/login", json={"email": "admin@test.example", "password": "Test@1234567"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_index_redirects_to_login_after_setup(client, db):
    client.post(
        "/api/setup",
        json={
            "clinic_name": "Test Clinic",
            "clinic_email": "clinic@test.example",
            "admin_name": "Admin User",
            "admin_email": "admin@test.example",
            "password": "Test@1234567",
            "confirm_password": "Test@1234567",
        },
    )
    resp = client.get("/")
    assert resp.status_code in (301, 302)
    assert "/login" in (resp.headers.get("Location") or "") or "/app" in (resp.headers.get("Location") or "")
