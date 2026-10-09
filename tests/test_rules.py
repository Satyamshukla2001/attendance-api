from datetime import datetime, timedelta, timezone
from app.rules import (
    duration_minutes,
    to_utc,
    validate_interval,
    work_date_ist,
)

T = datetime(
    2026, 10, 9, 4, 0, tzinfo=timezone.utc
)  # 09:30 IST


def test_naive_is_ist():
    assert to_utc(datetime(2026, 10, 9, 9, 30)) == T


def test_work_date_uses_ist():
    late_utc = datetime(
        2026, 10, 9, 20, 0, tzinfo=timezone.utc
    )  # 01:30 IST next day
    assert work_date_ist(late_utc) == "2026-10-10"


def test_validate():
    assert validate_interval(T, None) is None
    assert validate_interval(T, T) is not None
    assert validate_interval(T, T + timedelta(hours=17)) is not None
    assert validate_interval(T, T + timedelta(hours=8)) is None
    assert duration_minutes(T, T + timedelta(hours=8)) == 480
