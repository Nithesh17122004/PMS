"""Token generation, sequencing, queue transitions and follow-up arrival tests."""
from __future__ import annotations

from tests.conftest import login, create_patient, auth_context

from datetime import date, timedelta

from tests.conftest import auth_context, create_patient


def test_generate_token_numbers_increment(client, clinic, clinic_admin, doctor, db):
    login(client, "admin@clinic.test")
    p1 = create_patient(clinic, clinic_admin, first_name="P1", phone="+919000000001")
    p2 = create_patient(clinic, clinic_admin, first_name="P2", phone="+919000000002")
    resp = client.post("/api/tokens", json={"patient_id": p1.id, "doctor_id": doctor.id})
    assert resp.status_code == 201
    assert resp.get_json()["data"]["token"]["display_number"] == "001"
    resp = client.post("/api/tokens", json={"patient_id": p2.id, "doctor_id": doctor.id})
    assert resp.status_code == 201
    assert resp.get_json()["data"]["token"]["display_number"] == "002"


def test_clinic_wide_token_mode_shares_sequence(client, clinic, clinic_admin, doctor, db):
    clinic.settings.token_mode = "clinic"
    db.session.commit()
    login(client, "admin@clinic.test")
    p1 = create_patient(clinic, clinic_admin, first_name="P1", phone="+919000000001")
    p2 = create_patient(clinic, clinic_admin, first_name="P2", phone="+919000000002")
    r1 = client.post("/api/tokens", json={"patient_id": p1.id, "doctor_id": doctor.id})
    r2 = client.post("/api/tokens", json={"patient_id": p2.id, "doctor_id": doctor.id})
    assert r1.get_json()["data"]["token"]["queue_key"] == "COMMON"
    assert r1.get_json()["data"]["token"]["display_number"] == "001"
    assert r2.get_json()["data"]["token"]["display_number"] == "002"


def test_queue_transitions(client, clinic, clinic_admin, doctor, db):
    login(client, "admin@clinic.test")
    p1 = create_patient(clinic, clinic_admin, first_name="P1", phone="+919000000001")
    p2 = create_patient(clinic, clinic_admin, first_name="P2", phone="+919000000002")
    r1 = client.post("/api/tokens", json={"patient_id": p1.id, "doctor_id": doctor.id})
    r2 = client.post("/api/tokens", json={"patient_id": p2.id, "doctor_id": doctor.id})
    t1 = r1.get_json()["data"]["token"]["id"]
    t2 = r2.get_json()["data"]["token"]["id"]

    # call next -> t1 called
    resp = client.post(f"/api/tokens/{t1}/call")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["token"]["status"] == "called"

    # calling again conflicts
    resp = client.post(f"/api/tokens/{t1}/call")
    assert resp.status_code == 409

    # recall
    resp = client.post(f"/api/tokens/{t1}/recall")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["token"]["status"] == "recalled"

    # skip t2
    resp = client.post(f"/api/tokens/{t2}/skip", json={"reason": "Patient unavailable"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["token"]["status"] == "skipped"

    # no-show on t1 not allowed (recalled? Actually allowed from called/recalled/waiting)
    resp = client.post(f"/api/tokens/{t1}/no-show")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["token"]["status"] == "no_show"


def test_token_receipt_pdf(client, clinic, clinic_admin, doctor, db):
    login(client, "admin@clinic.test")
    p1 = create_patient(clinic, clinic_admin, first_name="P1", phone="+919000000001")
    r = client.post("/api/tokens", json={"patient_id": p1.id, "doctor_id": doctor.id})
    tid = r.get_json()["data"]["token"]["id"]
    resp = client.get(f"/api/tokens/{tid}/receipt.pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:5] == b"%PDF-"


def test_daily_reset_per_clinic_date(client, clinic, clinic_admin, doctor, db, app):
    from datetime import date, timedelta

    from backend.auth.security import hash_password
    from backend.models import User
    from backend.services.token_service import generate_token

    user = clinic_admin
    yesterday = date.today() - timedelta(days=1)
    p1 = create_patient(clinic, clinic_admin, first_name="P1", phone="+919000000001")
    ctx = auth_context(app, user, clinic)
    try:
        token = generate_token(patient=p1, doctor=doctor, actor=user, token_date=yesterday)
        assert token.token_date == yesterday
        assert token.token_number == 1
        assert token.display_number == "001"
    finally:
        ctx.pop()


def test_followup_does_not_auto_generate_token(client, clinic, clinic_admin, doctor, db):
    # A follow-up plan created during consultation completion does not create a token.
    from datetime import date, timedelta

    login(client, "doctor@clinic.test")
    p1 = create_patient(clinic, clinic_admin, first_name="P1", phone="+919000000001")
    from tests.conftest import add_schedule

    today = date.today()
    add_schedule(clinic, doctor, weekday=today.weekday(), start_time=__import__("datetime").time(9, 0), end_time=__import__("datetime").time(18, 0), slot_minutes=15)
    # create consultation standalone
    resp = client.post("/api/consultations", json={"patient_id": p1.id, "doctor_id": doctor.id})
    assert resp.status_code == 201
    cid = resp.get_json()["data"]["consultation"]["id"]
    # update diagnosis + treatment
    client.put(f"/api/consultations/{cid}", json={"diagnosis_summary": "URI", "treatment_plan": "Rest", "follow_up_required": True, "follow_up_date": (today + timedelta(days=7)).isoformat()})
    resp = client.post(f"/api/consultations/{cid}/complete", json={"diagnosis_summary": "URI", "treatment_plan": "Rest", "follow_up_required": True, "follow_up_date": (today + timedelta(days=7)).isoformat()})
    assert resp.status_code == 200
    # No token should have been created.
    from backend.models import DailyToken

    count = DailyToken.query.filter_by(clinic_id=clinic.id, patient_id=p1.id).count()
    assert count == 0

def test_receptionist_can_generate_and_call_doctor_queue(client, clinic, clinic_admin, receptionist, doctor):
    login(client, "reception@clinic.test")
    patient = create_patient(clinic, clinic_admin, first_name="Queue", phone="+919000000099")
    generated = client.post(
        "/api/tokens",
        json={"patient_id": patient.id, "doctor_id": doctor.id, "visit_type": "walk_in"},
    )
    assert generated.status_code == 201, generated.get_json()
    token_id = generated.get_json()["data"]["token"]["id"]

    called = client.post(f"/api/tokens/{token_id}/call")
    assert called.status_code == 200, called.get_json()
    assert called.get_json()["data"]["token"]["status"] == "called"

    recalled = client.post(f"/api/tokens/{token_id}/recall")
    assert recalled.status_code == 200, recalled.get_json()
    assert recalled.get_json()["data"]["token"]["status"] == "recalled"

def test_receptionist_queue_board_includes_each_doctor_and_next_patient(client, clinic, clinic_admin, receptionist, doctor):
    login(client, "reception@clinic.test")
    patient = create_patient(clinic, clinic_admin, first_name="Board", phone="+919000000097")
    created = client.post(
        "/api/tokens",
        json={"patient_id": patient.id, "doctor_id": doctor.id},
    )
    assert created.status_code == 201, created.get_json()

    response = client.get("/api/tokens/queue")
    assert response.status_code == 200, response.get_json()
    queues = response.get_json()["data"]["queues"]
    doctor_queue = next(queue for queue in queues if queue["doctor"]["id"] == doctor.id)
    assert doctor_queue["counts"]["waiting"] == 1
    assert doctor_queue["next"]["patient"]["patient_code"] == patient.patient_code
