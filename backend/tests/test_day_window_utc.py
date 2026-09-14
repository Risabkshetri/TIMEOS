"""day_window_utc — the inverse of local_date_for_event, and its own function (round-tripping and
correctness across a DST transition)."""

from datetime import UTC, date, datetime, timedelta

from timeos.ingest.service import day_window_utc, local_date_for_event


def test_utc_day_matches_the_plain_day_start_hour_boundary():
    start, end = day_window_utc(date(2026, 3, 15), "UTC", 4)
    assert start == datetime(2026, 3, 15, 4, tzinfo=UTC)
    assert end == datetime(2026, 3, 16, 4, tzinfo=UTC)


def test_window_is_exactly_24_hours_outside_dst_transitions():
    start, end = day_window_utc(date(2026, 3, 15), "UTC", 4)
    assert end - start == timedelta(hours=24)


def test_round_trips_with_local_date_for_event_across_the_window():
    tz_name, day_start_hour = "Asia/Kolkata", 4
    local_date = date(2026, 6, 10)
    start, end = day_window_utc(local_date, tz_name, day_start_hour)

    # A moment just inside the window, at each end, must resolve back to this exact local_date.
    just_after_start = int(start.timestamp() * 1000) + 1000
    just_before_end = int(end.timestamp() * 1000) - 1000
    assert local_date_for_event(just_after_start, tz_name, day_start_hour) == local_date
    assert local_date_for_event(just_before_end, tz_name, day_start_hour) == local_date

    # A moment exactly at the end boundary belongs to the NEXT day, not this one.
    at_end = int(end.timestamp() * 1000)
    assert local_date_for_event(at_end, tz_name, day_start_hour) == local_date + timedelta(days=1)


def test_spring_forward_day_is_twenty_three_hours():
    # America/New_York springs forward on 2026-03-08 at 02:00 local -> 03:00.
    start, end = day_window_utc(date(2026, 3, 8), "America/New_York", 0)
    assert end - start == timedelta(hours=23)


def test_fall_back_day_is_twenty_five_hours():
    # America/New_York falls back on 2026-11-01 at 02:00 local -> 01:00.
    start, end = day_window_utc(date(2026, 11, 1), "America/New_York", 0)
    assert end - start == timedelta(hours=25)
