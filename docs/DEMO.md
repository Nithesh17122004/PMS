# Demo environment

ClinicFlow ships a fully populated demonstration environment with fictional data.

## Provisioning

```bash
flask --app wsgi init-db
flask --app wsgi seed-demo
```

Or on Render, apply `render.demo.yaml` (sets `DEMO_MODE=true`).

## Accounts (password `Demo@12345`)

- Aster Family Clinic (Bengaluru):
  - `demo.admin@clinicflow.demo` — Clinic Admin
  - `demo.reception@clinicflow.demo` — Receptionist
  - `demo.doctor@clinicflow.demo` — Doctor
- Harbor Children's Clinic (Mumbai):
  - `demo.admin2@clinicflow.demo` — Clinic Admin
  - `demo.reception2@clinicflow.demo` — Receptionist
  - `demo.doctor2@clinicflow.demo` — Doctor

## Data

- 2 clinics, 3 doctors each, 25 patients per clinic, 8 appointments, 25 consultations, 25 prescriptions, 5 lab orders, 10 medications, 20 pharmacy alerts, notifications, audit logs.
- All names, phones, emails and clinical content are fictional.

## Features demonstrated

- Token queue with public TV display (`/display/<display_key>`).
- Follow-up plans that generate tokens only on patient arrival.
- Consultations, prescriptions (PDF), invoices (PDF), lab reports (PDF).
- Pharmacy low-stock/expiry alerts.
- Reports and CSV/PDF exports.

## Reset

```bash
flask --app wsgi seed-demo --reset
```

The demo banner is shown in the UI when `DEMO_MODE=true`.
