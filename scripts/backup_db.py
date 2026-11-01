"""Encrypted, portable database backups.

PostgreSQL backups use ``pg_dump`` (plain SQL) and SQLite backups use the
sqlite3 online backup API. Uploaded documents are optional because they may be
large and contain PHI; when included they live in the same encrypted archive.

Never log the database URL or encryption key. Restore is intentionally a
separate, confirmation-gated script.
"""
from __future__ import annotations

import gzip
import io
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return "sqlite:///clinicflow.db"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _backup_dir(output_dir: str | None) -> Path:
    directory = Path(output_dir or os.environ.get("BACKUP_DIR") or "instance/backups")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _pg_dump_sql(database_url: str) -> bytes:
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise RuntimeError(
            "pg_dump was not found. Install PostgreSQL client tools or run the backup "
            "on a Render cron/worker service with pg_dump available."
        )
    result = subprocess.run(
        [pg_dump, "--dbname", database_url, "--format=plain", "--no-owner", "--no-privileges", "--clean", "--if-exists"],
        check=False,
        capture_output=True,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError("pg_dump failed. Check database connectivity and credentials.")
    return result.stdout


def _sqlite_bytes(database_url: str) -> bytes:
    url = make_url(database_url)
    path = Path(url.database or "clinicflow.db")
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise RuntimeError("SQLite database file was not found.")
    temp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp.close()
    try:
        source = sqlite3.connect(str(path))
        target = sqlite3.connect(temp.name)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        data = Path(temp.name).read_bytes()
        return data
    finally:
        try:
            os.unlink(temp.name)
        except OSError:
            pass


def _upload_folder() -> Path | None:
    folder = Path(os.environ.get("UPLOAD_FOLDER") or "instance/uploads")
    return folder if folder.exists() else None


def _encrypt(data: bytes) -> bytes:
    key = os.environ.get("BACKUP_ENCRYPTION_KEY", "").strip()
    if not key:
        return data
    from cryptography.fernet import Fernet

    return Fernet(key.encode()).encrypt(data)


def create_backup(output_dir: str | None = None, include_uploads: bool = False) -> str:
    database_url = _database_url()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    directory = _backup_dir(output_dir)
    target = directory / f"clinicflow-backup-{stamp}.zip"
    sql = _pg_dump_sql(database_url) if database_url.startswith("postgresql") else _sqlite_bytes(database_url)
    compressed = gzip.compress(sql, compresslevel=6)
    uploads = _upload_folder() if include_uploads else None

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("database.sql.gz" if database_url.startswith("postgresql") else "database.db.gz", compressed)
        archive.writestr(
            "MANIFEST.txt",
            "\n".join(
                [
                    "ClinicFlow backup",
                    f"created_at={datetime.now(timezone.utc).isoformat()}",
                    f"database={database_url.split('@')[-1].split('/')[0] if '@' in database_url else 'sqlite'}",
                    f"uploads_included={bool(uploads)}",
                    "Restore requires scripts/restore_db.py and explicit confirmation.",
                ]
            ),
        )
        if uploads:
            for path in uploads.rglob("*"):
                if path.is_file():
                    archive.write(path, f"uploads/{path.relative_to(uploads)}")

    payload = _encrypt(buffer.getvalue())
    if os.environ.get("BACKUP_ENCRYPTION_KEY", "").strip():
        target = Path(str(target) + ".enc")
    target.write_bytes(payload)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return str(target)


def inspect_backup(path: str) -> dict:
    data = Path(path).read_bytes()
    key = os.environ.get("BACKUP_ENCRYPTION_KEY", "").strip()
    if key and path.endswith(".enc"):
        from cryptography.fernet import Fernet

        data = Fernet(key.encode()).decrypt(data)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        manifest = ""
        if "MANIFEST.txt" in names:
            manifest = archive.read("MANIFEST.txt").decode("utf-8", "replace")
    return {"files": names, "manifest": manifest}
