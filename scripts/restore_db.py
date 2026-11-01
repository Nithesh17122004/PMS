"""Restore a ClinicFlow backup. Destructive: requires --confirm."""
from __future__ import annotations

import gzip
import io
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from pathlib import Path

import click
from sqlalchemy.engine import make_url

from .backup_db import _database_url


def _read_archive(path: str) -> bytes:
    data = Path(path).read_bytes()
    key = os.environ.get("BACKUP_ENCRYPTION_KEY", "").strip()
    if path.endswith(".enc"):
        if not key:
            raise RuntimeError("BACKUP_ENCRYPTION_KEY is required to decrypt this backup.")
        from cryptography.fernet import Fernet

        data = Fernet(key.encode()).decrypt(data)
    return data


def restore_backup(path: str, restore_uploads: bool = False) -> str:
    database_url = _database_url()
    payload = _read_archive(path)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if database_url.startswith("postgresql"):
            if "database.sql.gz" not in names:
                raise RuntimeError("This archive does not contain a PostgreSQL dump.")
            sql = gzip.decompress(archive.read("database.sql.gz"))
            psql = shutil.which("psql")
            if not psql:
                raise RuntimeError("psql was not found. Install PostgreSQL client tools.")
            temp = tempfile.NamedTemporaryFile(suffix=".sql", delete=False)
            try:
                temp.write(sql)
                temp.close()
                result = subprocess.run(
                    [psql, "--dbname", database_url, "--file", temp.name, "--set", "ON_ERROR_STOP=on"],
                    check=False,
                    capture_output=True,
                    timeout=900,
                )
                if result.returncode != 0:
                    raise RuntimeError("psql restore failed. Check the database and dump compatibility.")
            finally:
                try:
                    os.unlink(temp.name)
                except OSError:
                    pass
        else:
            if "database.db.gz" not in names:
                raise RuntimeError("This archive does not contain a SQLite database.")
            data = gzip.decompress(archive.read("database.db.gz"))
            url = make_url(database_url)
            target = Path(url.database or "clinicflow.db")
            if not target.is_absolute():
                target = Path.cwd() / target
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = Path(str(target) + ".restore-tmp")
            temp.write_bytes(data)
            for suffix in ("-wal", "-shm"):
                try:
                    Path(str(target) + suffix).unlink()
                except OSError:
                    pass
            temp.replace(target)
        if restore_uploads:
            upload_root = Path(os.environ.get("UPLOAD_FOLDER") or "instance/uploads")
            for name in names:
                if not name.startswith("uploads/") or name.endswith("/"):
                    continue
                relative = name[len("uploads/"):]
                destination = upload_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(name))
    return "Restore completed. Restart the application and verify data integrity."


@click.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--confirm", is_flag=True, help="Required to run a destructive restore.")
@click.option("--uploads", is_flag=True, help="Also restore uploaded documents.")
def main(path, confirm, uploads):
    if not confirm:
        raise click.ClickException("Refusing to restore without --confirm.")
    click.echo(restore_backup(path, restore_uploads=uploads))


if __name__ == "__main__":
    main()
