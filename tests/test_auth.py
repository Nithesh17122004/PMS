"""Authentication, password and session security tests."""
from __future__ import annotations

from tests.conftest import login, TEST_PASSWORD, NEW_PASSWORD

from datetime import datetime, timedelta, timezone

from backend.models import PasswordResetToken
from backend.auth.security import generate_reset_token, hash_reset_token


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_login_page_renders(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


def test_login_success_returns_user_with_permissions(client, clinic_admin, clinic):
    data = login(client, "admin@clinic.test")
    assert data["user"]["email"] == "admin@clinic.test"
    assert data["user"]["clinic"]["id"] == clinic.id
    assert "patients.view" in data["user"]["permissions"]


def test_login_wrong_password_is_generic(client, clinic_admin):
    resp = client.post("/api/auth/login", json={"email": "admin@clinic.test", "password": "Wrong@1234567"})
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "invalid_credentials"


def test_login_unknown_email_is_generic(client):
    resp = client.post("/api/auth/login", json={"email": "nobody@clinic.test", "password": "Test@1234567"})
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "invalid_credentials"


def test_login_locks_account_after_failed_attempts(client, clinic_admin):
    for _ in range(5):
        resp = client.post("/api/auth/login", json={"email": "admin@clinic.test", "password": "Wrong@1234567"})
        assert resp.status_code == 401
    resp = client.post("/api/auth/login", json={"email": "admin@clinic.test", "password": "Test@1234567"})
    assert resp.status_code == 423
    assert resp.get_json()["error"]["code"] == "account_locked"


def test_logout_clears_session(client, clinic_admin):
    login(client, "admin@clinic.test")
    assert client.get("/api/auth/me").status_code == 200
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_change_password_requires_current_password(client, clinic_admin):
    login(client, "admin@clinic.test")
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "Wrong@1234567", "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "validation_error"


def test_change_password_flow(client, clinic_admin):
    login(client, "admin@clinic.test")
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 200
    data = login(client, "admin@clinic.test", password=NEW_PASSWORD)
    assert data["user"]["must_change_password"] is False


def test_password_reset_flow(client, clinic_admin, db):
    resp = client.post("/api/auth/forgot-password", json={"email": "admin@clinic.test"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["message"]

    raw, token_hash = generate_reset_token()
    token = PasswordResetToken(
        user_id=clinic_admin.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        requested_ip="127.0.0.1",
    )
    db.session.add(token)
    db.session.commit()

    resp = client.post("/api/auth/reset-password", json={"token": raw, "new_password": NEW_PASSWORD})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    resp = client.post(
        "/api/auth/reset-password", json={"token": raw, "new_password": NEW_PASSWORD}
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "invalid_token"

    data = login(client, "admin@clinic.test", password=NEW_PASSWORD)
    assert data["user"]["email"] == "admin@clinic.test"


def test_me_requires_authentication(client):
    assert client.get("/api/auth/me").status_code == 401
