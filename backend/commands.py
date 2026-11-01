from __future__ import annotations

import os

import click
from flask import current_app
from flask.cli import with_appcontext

from .extensions import db
from .models import Role, User
from .permissions.rbac import create_super_admin_role, seed_permissions
from .utils.crypto import normalize_email


def register_cli(app):
    @app.cli.command("init-db")
    @with_appcontext
    def init_db():
        """Create tables (development) and seed roles/permissions."""
        db.create_all()
        seed_permissions()
        create_super_admin_role()
        db.session.commit()
        click.echo("Database initialised.")

    @app.cli.command("check-db")
    @with_appcontext
    def check_db():
        """Verify database connectivity and schema without modifying data."""
        from sqlalchemy.engine import make_url

        from .models import User

        url = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
        try:
            parsed = make_url(url)
            host = parsed.host or "local file"
            database = parsed.database or ""
        except Exception:  # noqa: BLE001
            host = "unknown"
            database = ""
        try:
            db.session.execute(db.text("SELECT 1"))
            conn_ok = True
        except Exception as exc:  # noqa: BLE001
            conn_ok = False
            click.echo(f"Database connection failed: {exc}")
            raise SystemExit(1)
        try:
            user_count = User.query.count()
            schema_ok = True
        except Exception as exc:  # noqa: BLE001
            user_count = None
            schema_ok = False
            click.echo(f"Schema check failed (tables may be missing): {exc}")
        click.echo(f"Host: {host}")
        click.echo(f"Database: {database}")
        click.echo(f"Connection: {'OK' if conn_ok else 'FAILED'}")
        click.echo(f"Schema initialized: {'yes' if schema_ok else 'no'}")
        if schema_ok:
            click.echo(f"Users: {user_count}")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt="Full name")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    @with_appcontext
    def create_superadmin(email, name, password):
        """Create a platform super administrator."""
        from .auth.security import hash_password, validate_password_strength

        validate_password_strength(password)
        email = normalize_email(email)
        if User.query.filter_by(email=email).first():
            raise click.ClickException("A user with that email already exists.")
        role = create_super_admin_role()
        user = User(
            email=email,
            full_name=name,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
            clinic_id=None,
            designation="Platform Administrator",
        )
        db.session.add(user)
        db.session.commit()
        click.echo(f"Super admin created: {email}")

    @app.cli.command("seed-demo")
    @click.option("--reset", is_flag=True, help="Remove existing demo clinics and reseed.")
    @click.option("--if-empty", is_flag=True, help="Seed only when no demo clinic exists.")
    @click.option("--force", is_flag=True, help="Force seeding even if users already exist (development only).")
    @with_appcontext
    def seed_demo(reset, if_empty, force):
        """Load a realistic fictional demonstration environment."""
        from .models import User

        if not force and not reset and User.query.count() > 0:
            click.echo("Setup already completed (users exist). Skipping demo seed. Use --reset or --force to override.")
            return
        from seeds.demo_seed import seed_demo_environment

        result = seed_demo_environment(reset=reset, if_empty=if_empty)
        click.echo(result)

    @app.cli.command("backup-db")
    @click.option("--output", default=None, help="Destination directory.")
    @with_appcontext
    def backup_db(output):
        """Create a compressed database backup."""
        from scripts.backup_db import create_backup

        path = create_backup(output)
        click.echo(f"Backup written to {path}")

    @app.cli.command("run-scheduler")
    @with_appcontext
    def run_scheduler():
        """Run the background scheduler in the foreground."""
        from .tasks.scheduler import run_forever

        click.echo("Starting ClinicFlow background scheduler...")
        run_forever()

    @app.cli.command("purge-expired-sessions")
    @with_appcontext
    def purge_expired_sessions():
        """Placeholder for signed-cookie sessions (server stores no session rows)."""
        click.echo("ClinicFlow uses signed cookie sessions; no server-side session purge required.")
