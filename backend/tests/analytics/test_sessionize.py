"""§14.1 app session construction — each test maps to one numbered rule in the spec."""

from datetime import UTC, datetime, timedelta

import pytest

from timeos.analytics.sessionize import MAX_SESSION, build_sessions
from timeos.analytics.types import AnalyticsEvent

T0 = datetime(2026, 9, 14, 8, 0, 0, tzinfo=UTC)


def ev(offset_s: float, type_: str, package: str | None = None) -> AnalyticsEvent:
    payload = {"package": package} if package is not None else {}
    return AnalyticsEvent(ts_utc=T0 + timedelta(seconds=offset_s), type=type_, payload=payload)


def test_foreground_then_background_produces_one_session():
    events = [ev(0, "APP_FOREGROUND", "com.a"), ev(10, "APP_BACKGROUND", "com.a")]
    sessions = build_sessions(events)
    assert len(sessions) == 1
    assert sessions[0].app_key == "com.a"
    assert sessions[0].start_ts == T0
    assert sessions[0].end_ts == T0 + timedelta(seconds=10)
    assert not sessions[0].truncated


@pytest.mark.parametrize(
    "closing_type", ["SCREEN_OFF", "DEVICE_LOCK", "DEVICE_SHUTDOWN", "COLLECTOR_STOP"]
)
def test_session_closes_on_system_events(closing_type):
    events = [ev(0, "APP_FOREGROUND", "com.a"), ev(60, closing_type)]
    sessions = build_sessions(events)
    assert len(sessions) == 1
    assert sessions[0].end_ts == T0 + timedelta(seconds=60)


def test_another_apps_foreground_closes_the_previous_session():
    events = [
        ev(0, "APP_FOREGROUND", "com.a"),
        ev(100, "APP_FOREGROUND", "com.b"),
        ev(200, "APP_BACKGROUND", "com.b"),
    ]
    sessions = build_sessions(events)
    assert [s.app_key for s in sessions] == ["com.a", "com.b"]
    assert sessions[0].end_ts == T0 + timedelta(seconds=100)
    assert sessions[1].start_ts == T0 + timedelta(seconds=100)


def test_unterminated_session_truncates_at_last_known_event_not_now():
    events = [ev(0, "APP_FOREGROUND", "com.a"), ev(120, "USER_INTERACTION")]
    sessions = build_sessions(events)
    assert len(sessions) == 1
    assert sessions[0].truncated
    # Must close at the last event we actually saw, not extend to "now".
    assert sessions[0].end_ts == T0 + timedelta(seconds=120)


def test_unterminated_session_caps_at_four_hours_even_if_later_events_exist():
    far_future = T0 + MAX_SESSION + timedelta(hours=10)
    events = [
        ev(0, "APP_FOREGROUND", "com.a"),
        # A much later event exists (device kept running), but it never closed com.a's session
        # (e.g. it's a different app's session) — com.a must still cap at 4h, not run to it.
        AnalyticsEvent(ts_utc=far_future, type="APP_FOREGROUND", payload={"package": "com.b"}),
    ]
    sessions = build_sessions(events)
    com_a = next(s for s in sessions if s.app_key == "com.a")
    assert com_a.truncated
    assert com_a.end_ts == T0 + MAX_SESSION


def test_sessions_shorter_than_three_seconds_are_dropped():
    events = [
        ev(0, "APP_FOREGROUND", "com.a"),
        ev(1, "APP_BACKGROUND", "com.a"),  # 1s flick — dropped
        ev(2, "APP_FOREGROUND", "com.b"),
        ev(62, "APP_BACKGROUND", "com.b"),
    ]
    sessions = build_sessions(events)
    assert [s.app_key for s in sessions] == ["com.b"]


def test_same_app_bounce_within_merge_gap_is_merged():
    events = [
        ev(0, "APP_FOREGROUND", "com.a"),
        ev(10, "APP_BACKGROUND", "com.a"),
        ev(15, "APP_FOREGROUND", "com.a"),  # 5s gap, < 30s merge window
        ev(40, "APP_BACKGROUND", "com.a"),
    ]
    sessions = build_sessions(events)
    assert len(sessions) == 1
    assert sessions[0].start_ts == T0
    assert sessions[0].end_ts == T0 + timedelta(seconds=40)
    assert sessions[0].merged_from == 2


def test_same_app_gap_of_30s_or_more_does_not_merge():
    events = [
        ev(0, "APP_FOREGROUND", "com.a"),
        ev(10, "APP_BACKGROUND", "com.a"),
        ev(40, "APP_FOREGROUND", "com.a"),  # exactly 30s gap
        ev(70, "APP_BACKGROUND", "com.a"),
    ]
    sessions = build_sessions(events)
    assert len(sessions) == 2


def test_user_interaction_increments_the_open_sessions_count():
    events = [
        ev(0, "APP_FOREGROUND", "com.a"),
        ev(5, "USER_INTERACTION"),
        ev(6, "USER_INTERACTION"),
        ev(10, "APP_BACKGROUND", "com.a"),
    ]
    sessions = build_sessions(events)
    assert sessions[0].interaction_count == 2


def test_user_interaction_with_no_open_session_is_a_noop():
    events = [ev(0, "USER_INTERACTION"), ev(5, "APP_FOREGROUND", "com.a"), ev(65, "APP_BACKGROUND", "com.a")]
    sessions = build_sessions(events)
    assert len(sessions) == 1
    assert sessions[0].interaction_count == 0


def test_empty_input_produces_no_sessions():
    assert build_sessions([]) == []


def test_rerunning_over_the_same_events_is_byte_identical():
    events = [
        ev(0, "APP_FOREGROUND", "com.a"),
        ev(70, "APP_BACKGROUND", "com.a"),
        ev(71, "APP_FOREGROUND", "com.b"),
        ev(200, "SCREEN_OFF"),
    ]
    assert build_sessions(events) == build_sessions(list(events))
