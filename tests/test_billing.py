"""Billing, payments, refunds and summary tests."""
from __future__ import annotations

from tests.conftest import login, create_patient

from datetime import date


def test_create_invoice_payment_refund(client, clinic, clinic_admin, db):
    login(client, "admin@clinic.test")
    from tests.conftest import create_patient

    patient = create_patient(clinic, clinic_admin)
    resp = client.post(
        "/api/invoices",
        json={
            "patient_id": patient.id,
            "items": [
                {"item_type": "consultation", "description": "Consultation", "quantity": 1, "unit_price": 500}
            ],
        },
    )
    assert resp.status_code == 201
    invoice = resp.get_json()["data"]["invoice"]
    assert invoice["invoice_number"].startswith("INV-")
    assert invoice["status"] == "unpaid"
    assert invoice["balance"] == 500.0

    inv_id = invoice["id"]
    resp = client.post(f"/api/invoices/{inv_id}/payments", json={"amount": 500, "method": "cash"})
    assert resp.status_code == 201
    pay = resp.get_json()["data"]["payment"]
    assert pay["payment_code"].startswith("PAY-")
    assert resp.get_json()["data"]["invoice"]["status"] == "paid"
    assert resp.get_json()["data"]["invoice"]["balance"] == 0.0

    resp = client.post(
        f"/api/invoices/{inv_id}/refund",
        json={"payment_id": pay["id"], "amount": 500, "reason": "Patient requested refund"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["data"]["refund"]["refund_code"].startswith("REF-")

    resp = client.get("/api/billing/summary")
    assert resp.status_code == 200
    assert "gross" in resp.get_json()["data"]


def test_invoice_pdf(client, clinic, clinic_admin, db):
    login(client, "admin@clinic.test")
    from tests.conftest import create_patient

    patient = create_patient(clinic, clinic_admin)
    resp = client.post(
        "/api/invoices",
        json={
            "patient_id": patient.id,
            "items": [{"item_type": "service", "description": "Service", "quantity": 1, "unit_price": 100}],
        },
    )
    inv_id = resp.get_json()["data"]["invoice"]["id"]
    resp = client.get(f"/api/invoices/{inv_id}/pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:5] == b"%PDF-"
