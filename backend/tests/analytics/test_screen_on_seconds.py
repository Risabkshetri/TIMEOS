"""screen_on_seconds must report real screen-on time, distinct from coverage's TRACKED state
(which per §14.3's table also covers screen-off-but-alive time under the same label)."""

from datetime import UTC, datetime, timedelta

import pytest

from timeos.analytics.coverage import screen_on_seconds
from timeos.analytics.types import AnalyticsEvent

T0 = datetime(2026, 9, 14, 4, 0, 0, tzinfo=UTC)


def ev(offset_s: float, type_: str) -> AnalyticsEvent:
    return AnalyticsEvent(ts_utc=T0 + timedelta(seconds=offset_s), type=type_)


def test_simple_screen_on_off_pair():
    events = [ev(0, "SCREEN_ON"), ev(20, "SCREEN_OFF")]
    assert screen_on_seconds(events, T0, T0 + timedelta(seconds=100)) == 20.0


def test_events_in_between_do_not_double_count():
    events = [ev(0, "SCREEN_ON"), ev(10, "USER_INTERACTION"), ev(20, "SCREEN_OFF")]
    assert screen_on_seconds(events, T0, T0 + timedelta(seconds=100)) == 20.0


def test_screen_off_period_contributes_zero():
    events = [ev(0, "SCREEN_OFF")]
    assert screen_on_seconds(events, T0, T0 + timedelta(hours=8)) == 0.0


def test_screen_on_still_open_at_window_end_counts_up_to_window_end():
    events = [ev(0, "SCREEN_ON")]
    window_end = T0 + timedelta(seconds=50)
    assert screen_on_seconds(events, T0, window_end) == 50.0


def test_device_lock_turns_screen_off_like_screen_off_event():
    events = [ev(0, "SCREEN_ON"), ev(15, "DEVICE_LOCK"), ev(30, "SCREEN_ON"), ev(45, "SCREEN_OFF")]
    # on [0,15) = 15s, off [15,30), on [30,45) = 15s -> 30s total
    assert screen_on_seconds(events, T0, T0 + timedelta(seconds=100)) == 30.0


def test_no_events_at_all_is_zero():
    assert screen_on_seconds([], T0, T0 + timedelta(hours=24)) == 0.0


def test_unterminated_screen_on_does_not_fabricate_hours_of_silence():
    # Screen turns on, a few more events happen, then the device stops reporting entirely for
    # the rest of a 24h day (collector killed, sync never happened, etc.) — must NOT be read as
    # "screen stayed on for the remaining ~23 hours".
    events = [ev(0, "SCREEN_ON"), ev(30, "USER_INTERACTION"), ev(60, "APP_FOREGROUND")]
    window_end = T0 + timedelta(hours=24)
    result = screen_on_seconds(events, T0, window_end, poll_interval=timedelta(minutes=15))
    # Capped at last_event + 2*poll_interval (30 min), not extended to the 24h window end.
    assert result == pytest.approx(60 + 30 * 60)


def test_short_trailing_gap_within_the_poll_cap_still_counts_to_window_end():
    events = [ev(0, "SCREEN_ON")]
    window_end = T0 + timedelta(minutes=10)  # well within 2*15min of the last (only) event
    result = screen_on_seconds(events, T0, window_end, poll_interval=timedelta(minutes=15))
    assert result == timedelta(minutes=10).total_seconds()
