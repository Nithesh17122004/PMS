from __future__ import annotations

import os

import click
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

    @app.cli.command("create-superadmin")
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
    @with_appcontext
    def seed_demo(reset, if_empty):
        """Load a realistic fictional demonstration environment."""
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
