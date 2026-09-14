"""daily_metrics aggregation — coverage + classified sessions + focus + distraction -> one row."""

from datetime import UTC, datetime, timedelta

import pytest

from timeos.analytics.coverage import CoverageInterval
from timeos.analytics.distraction import PatternOccurrence
from timeos.analytics.focus import ClassifiedSession, FocusSession
from timeos.analytics.metrics import compute_daily_metrics

T0 = datetime(2026, 9, 14, 4, 0, 0, tzinfo=UTC)
DAY = timedelta(hours=24)


def cs(
    category: str, start_offset_s: float, duration_s: float, app_key: str | None = None
) -> ClassifiedSession:
    start = T0 + timedelta(seconds=start_offset_s)
    return ClassifiedSession(
        app_key=app_key or category,
        category_key=category,
        start_ts=start,
        end_ts=start + timedelta(seconds=duration_s),
    )


def test_zero_events_day_is_a_valid_all_unobserved_result_not_a_crash():
    result = compute_daily_metrics(
        window_start=T0,
        window_end=T0 + DAY,
        coverage_intervals=[CoverageInterval(T0, T0 + DAY, "UNOBSERVED")],
        screen_time_s=0.0,
        classified_sessions=[],
        focus_sessions=[],
        distraction_bursts=[],
        unlock_count=0,
    )
    assert result.coverage_ratio == 0.0
    assert result.unobserved_s == DAY.total_seconds()
    assert result.fragmentation_index is None  # below the 0.6 coverage gate
    assert result.unknown_ratio == 0.0
    assert result.focus_session_count == 0


def test_coverage_ratio_matches_tracked_plus_idle_over_duration():
    intervals = [
        CoverageInterval(T0, T0 + timedelta(hours=20), "TRACKED"),
        CoverageInterval(T0 + timedelta(hours=20), T0 + DAY, "UNOBSERVED"),
    ]
    result = compute_daily_metrics(
        window_start=T0,
        window_end=T0 + DAY,
        coverage_intervals=intervals,
        screen_time_s=0.0,
        classified_sessions=[],
        focus_sessions=[],
        distraction_bursts=[],
        unlock_count=0,
    )
    assert result.coverage_ratio == pytest.approx(20 / 24)
    assert result.fragmentation_index is not None  # >= 0.6 gate cleared


def test_category_time_buckets_sum_matching_sessions():
    sessions = [
        cs("communication", 0, 600),
        cs("entertainment", 600, 300),
        cs("social", 900, 200),
        cs("unknown", 1100, 100),
    ]
    result = compute_daily_metrics(
        window_start=T0,
        window_end=T0 + DAY,
        coverage_intervals=[CoverageInterval(T0, T0 + DAY, "TRACKED")],
        screen_time_s=1200.0,
        classified_sessions=sessions,
        focus_sessions=[],
        distraction_bursts=[],
        unlock_count=0,
    )
    assert result.communication_s == 600
    assert result.entertainment_s == 300
    assert result.social_s == 200
    assert result.unknown_s == 100
    assert result.unknown_ratio == pytest.approx(100 / 1200)


def test_deep_work_and_focused_work_and_shallow_work_partition_work_time():
    # 40 min of "development" category time total: 30 min of it forms one deep-work focus
    # session, the remaining 10 min never made it into any focus session (fragmented/shallow).
    sessions = [cs("development", 0, 30 * 60), cs("development", 40 * 60, 10 * 60)]
    focus = [
        FocusSession(
            category_key="development",
            start_ts=T0,
            end_ts=T0 + timedelta(minutes=30),
            interruption_count=0,
            tool_switch_count=0,
            attributed_ratio=1.0,
            is_deep_work=True,
        )
    ]
    result = compute_daily_metrics(
        window_start=T0,
        window_end=T0 + DAY,
        coverage_intervals=[CoverageInterval(T0, T0 + DAY, "TRACKED")],
        screen_time_s=2400.0,
        classified_sessions=sessions,
        focus_sessions=focus,
        distraction_bursts=[],
        unlock_count=0,
    )
    assert result.deep_work_s == 30 * 60
    assert result.focused_work_s == 0
    assert result.shallow_work_s == 10 * 60


def test_distraction_s_merges_overlapping_burst_occurrences():
    bursts = [
        PatternOccurrence("DISTRACTION_BURST", T0, T0 + timedelta(minutes=10), 0.5, {}),
        # Overlaps the first by 5 minutes -> merged span is 15 minutes, not 20.
        PatternOccurrence(
            "DISTRACTION_BURST",
            T0 + timedelta(minutes=5),
            T0 + timedelta(minutes=15),
            0.5,
            {},
        ),
    ]
    result = compute_daily_metrics(
        window_start=T0,
        window_end=T0 + DAY,
        coverage_intervals=[CoverageInterval(T0, T0 + DAY, "TRACKED")],
        screen_time_s=0.0,
        classified_sessions=[],
        focus_sessions=[],
        distraction_bursts=bursts,
        unlock_count=0,
    )
    assert result.distraction_s == 15 * 60


def test_active_time_excludes_idle_from_screen_time():
    intervals = [
        CoverageInterval(T0, T0 + timedelta(minutes=10), "TRACKED"),
        CoverageInterval(T0 + timedelta(minutes=10), T0 + timedelta(minutes=15), "IDLE"),
    ]
    result = compute_daily_metrics(
        window_start=T0,
        window_end=T0 + timedelta(minutes=15),
        coverage_intervals=intervals,
        screen_time_s=15 * 60,
        classified_sessions=[],
        focus_sessions=[],
        distraction_bursts=[],
        unlock_count=0,
    )
    assert result.idle_s == 5 * 60
    assert result.active_time_s == 10 * 60


def test_longest_and_average_focus_duration():
    focus = [
        FocusSession("development", T0, T0 + timedelta(minutes=20), 0, 0, 1.0, False),
        FocusSession("writing", T0, T0 + timedelta(minutes=40), 0, 0, 1.0, False),
    ]
    result = compute_daily_metrics(
        window_start=T0,
        window_end=T0 + DAY,
        coverage_intervals=[CoverageInterval(T0, T0 + DAY, "TRACKED")],
        screen_time_s=0.0,
        classified_sessions=[],
        focus_sessions=focus,
        distraction_bursts=[],
        unlock_count=0,
    )
    assert result.longest_focus_s == 40 * 60
    assert result.avg_focus_s == 30 * 60
    assert result.focus_session_count == 2
