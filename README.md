# ClinicFlow

ClinicFlow is a multi-tenant clinic and patient management system built with Flask, SQLAlchemy, PostgreSQL and a vanilla HTML/CSS/JS frontend.

## Features

- **Multi-tenant isolation** — every record is scoped by clinic. Super Admin provisions clinics; clinic staff operate inside one clinic.
- **8 roles** — Super Admin, Clinic Admin, Receptionist, Doctor, Nurse, Accountant, Pharmacist, Lab Technician with configurable permissions.
- **Patients** — registration, duplicate detection, encrypted contact details, merges, documents, timeline.
- **Queue** — doctor-wise or clinic-wide token sequences, daily reset, concurrency-safe numbering, call/recall/skip/no-show/transfer.
- **Appointments** — working hours, slots, booking conflicts, rescheduling, check-in (auto token).
- **Clinical** — consultations, diagnoses, treatment plans, follow-ups (tokens only when patient arrives), prescriptions, lab orders/results.
- **Financial** — invoices, payments, refunds, reports, PDF exports.
- **Operations** — pharmacy inventory/dispensing, lab workflow, notifications, audit logs, backups.
- **Public display** — TV-friendly queue board using only token numbers, no PHI.

## Quick start

```bash
python -m venv .venv
pip install -r requirements.txt
flask --app wsgi init-db
flask --app wsgi seed-demo
flask --app wsgi run
```

Demo accounts (password `Demo@12345`):

- `demo.admin@clinicflow.demo` / `demo.reception@clinicflow.demo` / `demo.doctor@clinicflow.demo` (Aster Family Clinic)
- `demo.admin2@clinicflow.demo` / `demo.reception2@clinicflow.demo` / `demo.doctor2@clinicflow.demo` (Harbor Children's Clinic)

All data is fictional.

## Testing

```bash
pytest
```

## Migrations

```bash
flask --app wsgi db upgrade
```

## Backups

```bash
flask --app wsgi backup-db
flask --app wsgi restore-db --path <backup.zip> --confirm
```

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

Render blueprint: `render.yaml` (production) and `render.demo.yaml` (demo).

```bash
gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 wsgi:app
```

## Security

See [docs/SECURITY.md](docs/SECURITY.md).
