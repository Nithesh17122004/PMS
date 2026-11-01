"""WSGI entry point for ClinicFlow.

Local development:
    flask --app wsgi run --debug

Production (Render):
    gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 wsgi:app
"""
from __future__ import annotations

import os

from backend import create_app

app = create_app(os.environ.get("APP_ENV"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=app.config.get("DEBUG", False))
