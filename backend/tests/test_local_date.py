"""Pure unit tests for local_date_for_event — §13's day boundary, [local day_start_hour, next)."""

from datetime import UTC, datetime

from timeos.ingest.service import local_date_for_event


def _millis(y, mo, d, h, mi=0, tz=UTC):
    return int(datetime(y, mo, d, h, mi, tzinfo=tz).timestamp() * 1000)


def test_event_after_day_start_hour_belongs_to_that_calendar_day():
    # 09:00 UTC, day_start_hour=4 -> still the same calendar day
    ts = _millis(2026, 3, 15, 9, 0)
    assert local_date_for_event(ts, "UTC", 4).isoformat() == "2026-03-15"


def test_event_before_day_start_hour_belongs_to_the_previous_day():
    # 02:00 UTC is before the 04:00 boundary -> counts as the PREVIOUS day
    ts = _millis(2026, 3, 15, 2, 0)
    assert local_date_for_event(ts, "UTC", 4).isoformat() == "2026-03-14"


def test_exactly_at_day_start_hour_belongs_to_the_new_day():
    ts = _millis(2026, 3, 15, 4, 0)
    assert local_date_for_event(ts, "UTC", 4).isoformat() == "2026-03-15"


def test_zero_day_start_hour_matches_plain_midnight_boundary():
    ts = _millis(2026, 3, 15, 0, 30)
    assert local_date_for_event(ts, "UTC", 0).isoformat() == "2026-03-15"


def test_uses_the_events_timezone_not_utc():
    # 23:30 UTC on the 14th is 05:00 on the 15th in Asia/Kolkata (+05:30) -- past the 04:00
    # boundary, so it's the 15th in that timezone even though it's still the 14th in UTC.
    ts = _millis(2026, 3, 14, 23, 30)
    assert local_date_for_event(ts, "Asia/Kolkata", 4).isoformat() == "2026-03-15"
    assert local_date_for_event(ts, "UTC", 4).isoformat() == "2026-03-14"
