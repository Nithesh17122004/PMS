# Security

ClinicFlow is designed for healthcare data. The following controls are implemented.

## Authentication and sessions

- Passwords are hashed with bcrypt (cost factor 12).
- Password policy: at least 10 characters with uppercase, lowercase, number and symbol.
- Accounts lock for 15 minutes after 5 failed attempts.
- Sessions are signed, HttpOnly, SameSite=Lax cookies with an 8-hour lifetime.
- Sessions are invalidated when a password changes.
- Password reset tokens are single-use, time-limited (30 minutes), stored as SHA-256 hashes.
- CSRF tokens are issued per session and validated on every unsafe request.

## Multi-tenancy

- Every clinic-scoped record carries `clinic_id`.
- All queries filter by the authenticated user's clinic.
- `get_scoped_or_404` rejects cross-clinic access with 404 (no information leak).
- Super Admin accounts have no clinic and only platform permissions.

## Authorisation

- 65 granular permissions grouped into 8 system roles.
- `permission_required` decorator enforces on every API route.
- Doctors are limited to their own queue and consultations by default.

## Data protection

- Patient phone, email, alternate phone and emergency contact phone are encrypted at rest with Fernet (AES-128-CBC + HMAC).
- Phone blind index (HMAC-SHA256) supports search without decrypting.
- Only masked phone/email are returned to non-privileged views.
- Public displays expose token numbers only — no patient data.

## Audit and monitoring

- Every state change writes an `AuditLog` row with actor, IP, user agent and non-PHI details.
- No PHI in audit details, logs, URLs or public displays.
- Structured JSON logging in production.

## Uploads

- Extension allow-list (pdf, png, jpg, jpeg, webp, doc, docx).
- Size limits (10 MB default).
- Stored with random names; served through authenticated routes.

## Rate limiting

- Per-IP limits on login, password reset and public endpoints.
- Configurable storage (memory/Redis).

## Backups

- Encrypted, compressed archives (`BACKUP_ENCRYPTION_KEY`).
- SQLite online backup API; PostgreSQL via `pg_dump`.
- Restore requires explicit `--confirm`.

## Production checklist

- Set `SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, `BLIND_INDEX_KEY` to dedicated random values.
- Use PostgreSQL (`DATABASE_URL`).
- `SESSION_COOKIE_SECURE=true`.
- Run the scheduler on a single instance.
- Keep `DEMO_MODE=false`.
- Rotate keys only with a documented migration plan (encrypted fields need re-encryption).
