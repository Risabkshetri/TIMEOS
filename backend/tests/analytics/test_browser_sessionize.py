"""§11.2/§14.1 browser (domain) session construction — mirrors test_sessionize.py's app-session
rules exactly, since browser_sessionize.py is a deliberate structural mirror of sessionize.py."""

from datetime import UTC, datetime, timedelta

from timeos.analytics.browser_sessionize import MAX_SESSION, build_browser_sessions
from timeos.analytics.types import AnalyticsEvent

T0 = datetime(2026, 9, 14, 8, 0, 0, tzinfo=UTC)


def ev(offset_s: float, type_: str, domain: str | None = None) -> AnalyticsEvent:
    payload = {"domain": domain} if domain is not None else {}
    return AnalyticsEvent(ts_utc=T0 + timedelta(seconds=offset_s), type=type_, payload=payload)


def test_focus_start_then_end_produces_one_session():
    events = [ev(0, "DOMAIN_FOCUS_START", "github.com"), ev(10, "DOMAIN_FOCUS_END", "github.com")]
    sessions = build_browser_sessions(events)
    assert len(sessions) == 1
    assert sessions[0].domain == "github.com"
    assert sessions[0].start_ts == T0
    assert sessions[0].end_ts == T0 + timedelta(seconds=10)
    assert not sessions[0].truncated


def test_another_domains_focus_start_closes_the_previous_session():
    events = [
        ev(0, "DOMAIN_FOCUS_START", "github.com"),
        ev(100, "DOMAIN_FOCUS_START", "youtube.com"),
        ev(200, "DOMAIN_FOCUS_END", "youtube.com"),
    ]
    sessions = build_browser_sessions(events)
    assert [s.domain for s in sessions] == ["github.com", "youtube.com"]
    assert sessions[0].end_ts == T0 + timedelta(seconds=100)
    assert sessions[1].start_ts == T0 + timedelta(seconds=100)


def test_unterminated_session_truncates_at_last_known_event_not_now():
    events = [ev(0, "DOMAIN_FOCUS_START", "github.com"), ev(300, "HEALTH")]
    sessions = build_browser_sessions(events)
    assert len(sessions) == 1
    assert sessions[0].end_ts == T0 + timedelta(seconds=300)
    assert sessions[0].truncated


def test_session_longer_than_4h_is_capped_and_truncated():
    events = [
        ev(0, "DOMAIN_FOCUS_START", "github.com"),
        ev(MAX_SESSION.total_seconds() + 3600, "DOMAIN_FOCUS_END", "github.com"),
    ]
    sessions = build_browser_sessions(events)
    assert len(sessions) == 1
    assert sessions[0].end_ts == T0 + MAX_SESSION
    assert sessions[0].truncated


def test_sub_3s_sessions_are_dropped():
    events = [ev(0, "DOMAIN_FOCUS_START", "github.com"), ev(1, "DOMAIN_FOCUS_END", "github.com")]
    assert build_browser_sessions(events) == []


def test_same_domain_bounce_within_merge_gap_is_merged():
    events = [
        ev(0, "DOMAIN_FOCUS_START", "github.com"),
        ev(10, "DOMAIN_FOCUS_END", "github.com"),
        ev(20, "DOMAIN_FOCUS_START", "github.com"),  # 10s gap, well under the 30s merge window
        ev(40, "DOMAIN_FOCUS_END", "github.com"),
    ]
    sessions = build_browser_sessions(events)
    assert len(sessions) == 1
    assert sessions[0].start_ts == T0
    assert sessions[0].end_ts == T0 + timedelta(seconds=40)
    assert sessions[0].merged_from == 2


def test_a_stray_focus_end_with_no_matching_start_is_ignored():
    events = [ev(0, "DOMAIN_FOCUS_END", "github.com"), ev(10, "DOMAIN_FOCUS_START", "youtube.com")]
    sessions = build_browser_sessions(events)
    assert len(sessions) == 0 or sessions[0].domain == "youtube.com"


def test_a_duplicate_focus_start_for_the_same_domain_does_not_reopen_a_session():
    events = [
        ev(0, "DOMAIN_FOCUS_START", "github.com"),
        ev(5, "DOMAIN_FOCUS_START", "github.com"),  # spurious re-focus, same domain
        ev(10, "DOMAIN_FOCUS_END", "github.com"),
    ]
    sessions = build_browser_sessions(events)
    assert len(sessions) == 1
    assert sessions[0].start_ts == T0
    assert sessions[0].end_ts == T0 + timedelta(seconds=10)


def test_empty_events_produce_no_sessions():
    assert build_browser_sessions([]) == []
