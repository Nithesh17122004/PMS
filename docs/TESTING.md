# Testing

## Running

```bash
pytest
```

Configuration: `pytest.ini` (testpaths = tests, pythonpath = .).

## Test database

Tests use `TestingConfig` (in-memory SQLite, CSRF and rate limits disabled, scheduler off). Each test gets a fresh schema via `db.create_all()`.

## Coverage areas

- `test_auth.py` — login, lockout, logout, password change, reset flow, health check.
- `test_rbac.py` — permission matrix, endpoint enforcement.
- `test_isolation.py` — cross-clinic data isolation.
- `test_patients.py` — registration, duplicate conflict, search, merge, field encryption.
- `test_appointments.py` — booking, conflict, reschedule, check-in token generation, cancel.
- `test_tokens.py` — numbering, clinic-wide mode, queue transitions, receipt PDF, daily reset, follow-up no auto-token.
- `test_followups.py` — create, arrive (token), complete, reminder consent, dashboard.
- `test_billing.py` — invoice, payment, refund, PDF.
- `test_clinical.py` — full consultation flow, prescription, authorization, PDF.
- `test_public.py` — public display data, disabled/unknown keys.
- `test_backup.py` — backup creation and inspection.

## Concurrency

Concurrency tests for token numbering require a file-based SQLite database or PostgreSQL. Set `TEST_DATABASE_URL=sqlite:///instance/test_concurrency.db` and run a dedicated concurrency test module (not included in the default suite).

## Adding tests

Use the fixtures in `tests/conftest.py`: `app`, `client`, `clinic`, `clinic_b`, `roles`, `clinic_admin`, `receptionist`, `doctor`, `doctor_user`. Helpers: `login`, `create_patient`, `add_schedule`, `auth_context`.
