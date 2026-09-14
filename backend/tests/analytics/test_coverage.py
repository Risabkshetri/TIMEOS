"""§14.3 device coverage reconstruction — one test per row of the state table."""

from datetime import UTC, datetime, timedelta

from timeos.analytics.coverage import (
    DEVICE_OFFLINE,
    IDLE,
    TRACKED,
    UNOBSERVED,
    build_coverage,
    coverage_ratio,
)
from timeos.analytics.types import AnalyticsEvent

T0 = datetime(2026, 9, 14, 4, 0, 0, tzinfo=UTC)
DAY = timedelta(hours=24)


def ev(offset_s: float, type_: str) -> AnalyticsEvent:
    return AnalyticsEvent(ts_utc=T0 + timedelta(seconds=offset_s), type=type_)


def test_screen_on_with_interaction_is_tracked():
    events = [ev(0, "SCREEN_ON"), ev(10, "USER_INTERACTION")]
    window_end = T0 + timedelta(seconds=60)
    intervals = build_coverage(events, T0, window_end)
    assert all(i.state == TRACKED for i in intervals)


def test_screen_on_with_no_interaction_past_threshold_is_idle():
    events = [ev(0, "SCREEN_ON")]
    window_end = T0 + timedelta(minutes=20)
    intervals = build_coverage(events, T0, window_end)
    states = [(i.state, i.duration_s) for i in intervals]
    assert states[0][0] == TRACKED  # first 5 minutes since screen-on
    assert states[1][0] == IDLE  # the rest


def test_screen_off_with_collector_alive_is_tracked():
    events = [ev(0, "SCREEN_OFF")]
    window_end = T0 + timedelta(minutes=10)
    intervals = build_coverage(events, T0, window_end)
    assert all(i.state == TRACKED for i in intervals)


def test_shutdown_to_startup_is_device_offline():
    events = [ev(0, "DEVICE_SHUTDOWN"), ev(600, "DEVICE_STARTUP")]
    window_end = T0 + timedelta(seconds=700)
    intervals = build_coverage(events, T0, window_end)
    offline = [i for i in intervals if i.state == DEVICE_OFFLINE]
    assert offline
    assert offline[0].start_ts == T0
    assert offline[0].end_ts == T0 + timedelta(seconds=600)


def test_gap_of_at_least_double_poll_interval_is_unobserved():
    poll = timedelta(minutes=15)
    events = [ev(0, "SCREEN_ON"), ev(1, "USER_INTERACTION")]
    window_end = T0 + timedelta(seconds=1) + 2 * poll
    intervals = build_coverage(events, T0, window_end, poll_interval=poll)
    assert intervals[-1].state == UNOBSERVED


def test_short_gap_under_double_poll_interval_is_not_unobserved():
    poll = timedelta(minutes=15)
    events = [ev(0, "SCREEN_ON"), ev(1, "USER_INTERACTION")]
    window_end = T0 + timedelta(minutes=20)  # < 2*15min
    intervals = build_coverage(events, T0, window_end, poll_interval=poll)
    assert all(i.state != UNOBSERVED for i in intervals)


def test_collector_stopped_is_unobserved_regardless_of_gap_length():
    events = [ev(0, "SCREEN_ON"), ev(1, "USER_INTERACTION"), ev(30, "COLLECTOR_STOP")]
    window_end = T0 + timedelta(seconds=60)  # short gap, but collector explicitly stopped
    intervals = build_coverage(events, T0, window_end)
    assert intervals[-1].state == UNOBSERVED
    assert intervals[-1].start_ts == T0 + timedelta(seconds=30)


def test_coverage_ratio_only_counts_tracked_and_idle():
    events = [ev(0, "SCREEN_ON"), ev(1, "USER_INTERACTION")]
    window_seconds = 3600.0
    window_end = T0 + timedelta(seconds=window_seconds)
    intervals = build_coverage(events, T0, window_end, poll_interval=timedelta(hours=1))
    ratio = coverage_ratio(intervals, window_seconds)
    assert 0.99 <= ratio <= 1.0


def test_no_events_and_no_gap_gate_is_fully_unobserved():
    # An entire day with zero events must be a valid all-UNOBSERVED day, not a crash — this is a
    # named Phase 4 failure case.
    intervals = build_coverage([], T0, T0 + DAY)
    assert len(intervals) == 1
    assert intervals[0].state == UNOBSERVED
    assert coverage_ratio(intervals, DAY.total_seconds()) == 0.0


def test_intervals_never_exceed_the_window_and_are_contiguous():
    events = [
        ev(0, "SCREEN_ON"),
        ev(30, "USER_INTERACTION"),
        ev(3600, "SCREEN_OFF"),
        ev(7200, "DEVICE_SHUTDOWN"),
    ]
    window_end = T0 + DAY
    intervals = build_coverage(events, T0, window_end)
    assert intervals[0].start_ts == T0
    assert intervals[-1].end_ts == window_end
    for prev, nxt in zip(intervals, intervals[1:], strict=False):
        assert prev.end_ts == nxt.start_ts


def test_rerunning_over_the_same_events_is_byte_identical():
    events = [ev(0, "SCREEN_ON"), ev(30, "USER_INTERACTION"), ev(3600, "SCREEN_OFF")]
    window_end = T0 + DAY
    assert build_coverage(events, T0, window_end) == build_coverage(list(events), T0, window_end)
