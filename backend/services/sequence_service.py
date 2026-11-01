"""Race-safe document and daily token numbering.

PostgreSQL row locks (`SELECT ... FOR UPDATE`) serialise allocation. SQLite
falls back to unique-constraint retries, which the automated concurrency test
exercises. Sequence gaps are acceptable; duplicate numbers are not.
"""
from __future__ import annotations

import random
import re
import time
from datetime import date

from sqlalchemy.exc import IntegrityError, OperationalError

from ..extensions import db
from ..models import DocumentSequence, TokenSequence
from ..utils.errors import ApiError


def _retry_wait(attempt: int) -> None:
    time.sleep(min(0.5, 0.02 * (attempt + 1)) + random.random() * 0.01)


def next_document_number(clinic_id: str, kind: str, period: str = "", attempts: int = 12) -> int:
    last_error = None
    for attempt in range(attempts):
        try:
            with db.session.begin_nested():
                sequence = (
                    DocumentSequence.query.filter_by(
                        clinic_id=clinic_id, kind=kind, period=period
                    )
                    .with_for_update()
                    .first()
                )
                if sequence is None:
                    sequence = DocumentSequence(
                        clinic_id=clinic_id, kind=kind, period=period, last_number=0
                    )
                    db.session.add(sequence)
                    db.session.flush()
                sequence.last_number += 1
                number = sequence.last_number
                db.session.flush()
                return number
        except (IntegrityError, OperationalError) as exc:
            last_error = exc
            db.session.rollback()
            _retry_wait(attempt)
    raise ApiError(
        "numbering_failed",
        "Could not allocate a document number. Please try again.",
        503,
    )


def allocate_token_number(clinic_id: str, token_date: date, queue_key: str, attempts: int = 12) -> int:
    """Must be called inside the caller's transaction; does not commit."""
    last_error = None
    for attempt in range(attempts):
        try:
            with db.session.begin_nested():
                sequence = (
                    TokenSequence.query.filter_by(
                        clinic_id=clinic_id, token_date=token_date, queue_key=queue_key
                    )
                    .with_for_update()
                    .first()
                )
                if sequence is None:
                    sequence = TokenSequence(
                        clinic_id=clinic_id,
                        token_date=token_date,
                        queue_key=queue_key,
                        last_number=0,
                    )
                    db.session.add(sequence)
                    db.session.flush()
                sequence.last_number += 1
                number = sequence.last_number
                db.session.flush()
                return number
        except (IntegrityError, OperationalError) as exc:
            last_error = exc
            db.session.rollback()
            _retry_wait(attempt)
    raise ApiError(
        "token_numbering_failed",
        "Could not allocate a token number due to high demand. Please try again.",
        503,
    )


def format_document_number(prefix: str, number: int, width: int = 6, period: str = "") -> str:
    prefix = (prefix or "").strip()
    core = f"{number:0{width}d}"
    if period:
        core = f"{period}-{core}"
    return f"{prefix}{core}" if prefix else core


def format_token_number(prefix: str, number: int) -> str:
    prefix = re.sub(r"[^A-Za-z0-9-]", "", prefix or "")[:8]
    return f"{prefix}{number:03d}" if prefix else f"{number:03d}"
