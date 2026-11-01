"""Backup creation and inspection tests."""
from __future__ import annotations

import os
import tempfile

from scripts.backup_db import create_backup, inspect_backup


def test_create_and_inspect_backup(tmp_path, monkeypatch):
    # Point at the in-memory... actually _sqlite_bytes reads from DATABASE_URL file.
    # Use a temp sqlite file.
    db_path = tmp_path / "clinicflow.db"
    import sqlite3

    sqlite3.connect(str(db_path)).close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    out = tmp_path / "backups"
    out.mkdir()
    path = create_backup(output_dir=str(out))
    assert os.path.exists(path)
    info = inspect_backup(path)
    assert "database.db.gz" in info["files"]
    assert "MANIFEST.txt" in info["files"]
    assert "ClinicFlow backup" in info["manifest"]
