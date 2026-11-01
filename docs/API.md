# API reference (summary)

Base URL: `/api`. All responses use the envelope:

```json
{ "ok": true, "data": ..., "meta": { "total": 0, "page": 1, "per_page": 25, "pages": 1 } }
```

Errors:

```json
{ "ok": false, "error": { "code": "...", "message": "...", "details": {} } }
```

## Authentication

- `POST /api/auth/login` — `{ email, password }` → `{ user, redirect }`
- `POST /api/auth/logout`
- `GET /api/auth/me` → `{ user }`
- `GET /api/auth/csrf` → `{ csrf_token }`
- `POST /api/auth/change-password` — `{ current_password, new_password }`
- `POST /api/auth/forgot-password` — `{ email }`
- `POST /api/auth/reset-password` — `{ token, new_password }`

## Core resources

- Patients: `/api/patients`, `/api/patients/search`, `/api/patients/<id>`, `/api/patients/<id>/timeline`, `/api/patients/<id>/documents`, `/api/patients/<id>/merge`
- Doctors: `/api/doctors`, `/api/doctors/<id>`, `/api/doctors/<id>/schedules`, `/api/doctors/<id>/leaves`, `/api/doctors/available`
- Appointments: `/api/appointments`, `/api/appointments/<id>`, `/api/appointments/<id>/reschedule`, `/api/appointments/<id>/cancel`, `/api/appointments/<id>/check-in`
- Tokens: `/api/tokens`, `/api/tokens/queue`, `/api/tokens/<id>`, `/api/tokens/<id>/call|recall|skip|cancel|no-show|transfer|start|complete`, `/api/tokens/<id>/receipt.pdf`
- Follow-ups: `/api/followups`, `/api/followups/dashboard`, `/api/followups/<id>`, `/api/followups/<id>/confirm|reschedule|cancel|arrive|complete|remind`
- Consultations: `/api/consultations`, `/api/consultations/start`, `/api/consultations/<id>`, `/api/consultations/<id>/complete`, `/api/consultations/<id>/invoice`, `/api/consultations/<id>/prescriptions`, `/api/prescriptions`, `/api/prescriptions/<id>`, `/api/prescriptions/<id>/pdf`
- Billing: `/api/invoices`, `/api/invoices/<id>`, `/api/invoices/<id>/payments`, `/api/invoices/<id>/refund`, `/api/invoices/<id>/void`, `/api/invoices/<id>/pdf`, `/api/payments`, `/api/billing/summary`
- Pharmacy: `/api/pharmacy/medications`, `/api/pharmacy/alerts`, `/api/pharmacy/batches`, `/api/pharmacy/dispense`, `/api/pharmacy/stock-movements`
- Lab: `/api/lab/tests`, `/api/lab/orders`, `/api/lab/orders/<id>`, `/api/lab/orders/<id>/pdf`, `/api/lab/orders/<id>/items/<item_id>/result`, `/api/lab/orders/<id>/items/<item_id>/verify`
- Reports: `/api/reports/types`, `/api/reports/<type>`, `/api/reports/<type>/export.csv`, `/api/reports/<type>/export.pdf`
- Notifications: `/api/notifications`, `/api/notifications/unread-count`, `/api/notifications/<id>/read`
- Clinic: `/api/clinic`, `/api/clinic/staff`, `/api/clinic/roles`, `/api/clinic/audit-logs`, `/api/clinic/settings`
- Public: `/api/public/display/<display_key>`, `/api/public/clinics/<slug>/logo`
- Platform: `/api/admin/dashboard`, `/api/admin/clinics`

All clinic-scoped endpoints require an authenticated session. Permission codes are listed in `backend/permissions/rbac.py`.
