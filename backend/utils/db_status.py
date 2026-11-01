"""Database readiness helpers."""
from __future__ import annotations

import logging

from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError

logger = logging.getLogger(__name__)


def database_schema_ready() -> bool:
    """Return True if the core database tables (users) exist and are queryable."""
    try:
        from ..models import User

        User.query.count()
        return True
    except (OperationalError, ProgrammingError, DBAPIError, Exception) as exc:  # noqa: BLE001
        logger.error(
            "Database schema is not initialized or unavailable. "
            "Run 'flask --app wsgi init-db' against the production database. Detail: %s",
            exc,
        )
        return False
