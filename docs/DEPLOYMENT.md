# Deployment guide

## First deployment

1. Deploy via `render.yaml` (or `render.demo.yaml` for demo).
2. Open the app URL. With an empty database you are redirected to `/setup`.
3. Complete the form (clinic name/email, admin name/email, password). The first Clinic Admin is created and logged in.
4. You are redirected to `/app`. Configure staff, roles, permissions and settings from Settings.

No command-line administrator creation is required. Demo seeding is optional (`flask --app wsgi seed-demo`) and is disabled in production by default.

The repository includes Render blueprints:

- `render.yaml` — production web service + scheduler worker.
- `render.demo.yaml` — demo environment.

Deploy steps:

1. Push to GitHub.
2. In Render: New → Blueprint, select repo, apply `render.yaml`.
3. Create the PostgreSQL database when prompted (or use an external managed Postgres).
4. Set any remaining secrets manually if the blueprint did not (SMTP credentials, etc.).

The web service:

- Build: `pip install --upgrade pip && pip install -r requirements.txt`
- Start: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 wsgi:app`
- Health check: `/healthz`

The worker:

- Start: `flask --app wsgi run-scheduler`
- Runs reminders, missed follow-ups, notification retries, cleanup.

### Environment variables (production)

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string (Render internal database URL) |
| `SECRET_KEY` | Session/CSRF signing secret (generate with `python -c "import secrets;print(secrets.token_urlsafe(48))"`) |
| `FIELD_ENCRYPTION_KEY` | Stable Fernet key for patient field encryption |
| `BLIND_INDEX_KEY` | Stable HMAC key for phone/email blind indexes |
| `SESSION_COOKIE_SECURE` | `true` |
| `RATELIMIT_STORAGE_URI` | `redis://...` recommended on Render |
| `ENABLE_SCHEDULER` | `true` on the dedicated worker |

Provision dedicated keys instead of deriving from `SECRET_KEY` for long-lived stores:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_hex(32))"
```

## Local development

```bash
cp .env.example .env
flask --app wsgi init-db
flask --app wsgi seed-demo
flask --app wsgi run
```

## Migrations & start order

```bash
flask --app wsgi db upgrade
flask --app wsgi migrate   # after model changes
```

## Demo deployment

`render.demo.yaml` provisions a demo environment with `DEMO_MODE=true`, fictional data and public display enabled.

## Notes

- The scheduler must run on exactly one instance; the blueprint runs it on a dedicated worker.
- Backups: `flask --app wsgi backup-db`; restore with `flask --app wsgi restore-db --path <file> --confirm`.
