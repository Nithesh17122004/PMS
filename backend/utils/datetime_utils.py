from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from ..utils.errors import ValidationError


def clinic_timezone(clinic) -> ZoneInfo:
    name = None
    if clinic is not None and getattr(clinic, "settings", None):
        name = clinic.settings.timezone
    try:
        return ZoneInfo(name or "Asia/Kolkata")
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def clinic_now(clinic) -> datetime:
    return datetime.now(clinic_timezone(clinic))


def clinic_today(clinic) -> date:
    return clinic_now(clinic).date()


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_clinic(dt: datetime | None, clinic) -> datetime | None:
    dt = as_utc(dt)
    if dt is None:
        return None
    return dt.astimezone(clinic_timezone(clinic))


def utc_bounds_for_local_day(clinic, day: date) -> tuple[datetime, datetime]:
    tz = clinic_timezone(clinic)
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def utc_bounds_for_local_range(clinic, start: date, end: date) -> tuple[datetime, datetime]:
    """Inclusive local dates -> [start_utc, end_utc)."""
    tz = clinic_timezone(clinic)
    start_local = datetime.combine(start, time.min, tzinfo=tz)
    end_local = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def parse_date(value, field="date", required=True) -> date | None:
    if value in (None, ""):
        if required:
            raise ValidationError(f"{field} is required.")
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ValidationError(f"{field} must be a valid date (YYYY-MM-DD).")


def parse_time(value, field="time", required=True) -> time | None:
    if value in (None, ""):
        if required:
            raise ValidationError(f"{field} is required.")
        return None
    if isinstance(value, time):
        return value
    text = str(value).strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValidationError(f"{field} must be a valid time (HH:MM).")


def parse_datetime(value, field="date time", required=True) -> datetime | None:
    if value in (None, ""):
        if required:
            raise ValidationError(f"{field} is required.")
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError(f"{field} must be a valid date time.")
    return as_utc(parsed)


def iso(dt: datetime | None) -> str | None:
    dt = as_utc(dt)
    return dt.isoformat() if dt else None


def minutes_between(start: datetime | None, end: datetime | None) -> int | None:
    start, end = as_utc(start), as_utc(end)
    if not start or not end:
        return None
    return max(0, int((end - start).total_seconds() // 60))
