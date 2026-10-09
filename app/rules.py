"""Pure business-rule helpers (no DB) so they are easy to unit test."""
from datetime import datetime, timedelta, timezone
from .config import IST, MAX_SHIFT_HOURS, MIN_SHIFT_MINUTES


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """Naive datetimes are interpreted as IST; aware ones are converted
    to UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(timezone.utc)


def work_date_ist(dt: datetime) -> str:
    return dt.astimezone(IST).date().isoformat()


def validate_interval(
    punch_in: datetime,
    punch_out: datetime | None,
) -> str | None:
    """Return an error message, or None if the interval is valid."""
    if punch_out is None:
        return None
    if punch_out < punch_in + timedelta(
        minutes=MIN_SHIFT_MINUTES
    ):
        return "punch_out must be after punch_in"
    if punch_out - punch_in > timedelta(hours=MAX_SHIFT_HOURS):
        return f"shift cannot exceed {MAX_SHIFT_HOURS} hours"
    return None


def duration_minutes(punch_in: datetime, punch_out: datetime) -> int:
    return int((punch_out - punch_in).total_seconds() // 60)
