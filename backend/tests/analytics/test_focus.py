"""§16 focus engine — context switches, interruption tolerance, focus/deep-work thresholds."""

from datetime import UTC, datetime, timedelta

import pytest

from timeos.analytics.focus import (
    ClassifiedSession,
    build_focus_sessions,
    count_context_switches,
    fragmentation_index,
)

T0 = datetime(2026, 9, 14, 9, 0, 0, tzinfo=UTC)


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


def test_same_category_different_app_is_a_tool_switch_not_a_context_switch():
    sessions = [cs("development", 0, 60, "ide"), cs("development", 60, 60, "terminal")]
    context_switches, tool_switches = count_context_switches(sessions)
    assert context_switches == 0
    assert tool_switches == 1


def test_different_category_is_a_context_switch():
    sessions = [cs("development", 0, 60), cs("social", 60, 60)]
    context_switches, tool_switches = count_context_switches(sessions)
    assert context_switches == 1
    assert tool_switches == 0


def test_twenty_minute_uninterrupted_block_is_a_focus_session():
    sessions = [cs("development", 0, 20 * 60)]
    focus = build_focus_sessions(sessions)
    assert len(focus) == 1
    assert focus[0].duration_s == 20 * 60
    assert focus[0].attributed_ratio == 1.0
    assert not focus[0].is_deep_work  # too short for deep work


def test_block_shorter_than_fifteen_minutes_is_not_a_focus_session():
    sessions = [cs("development", 0, 10 * 60)]
    assert build_focus_sessions(sessions) == []


def test_short_interruption_under_ninety_seconds_is_tolerated_and_excluded_from_work_time():
    sessions = [
        cs("development", 0, 10 * 60, "ide"),
        cs("social", 10 * 60, 30, "phone-notif"),  # 30s interruption, well under tolerance
        cs("development", 10 * 60 + 30, 10 * 60, "ide"),
    ]
    focus = build_focus_sessions(sessions)
    assert len(focus) == 1
    assert focus[0].interruption_count == 1
    # Work time excludes the 30s interruption; window spans start to end including it.
    assert focus[0].attributed_ratio < 1.0
    assert focus[0].attributed_ratio > 0.95


def test_interruption_longer_than_ninety_seconds_breaks_focus_into_two_pieces():
    sessions = [
        cs("development", 0, 20 * 60, "ide"),
        cs("social", 20 * 60, 100, "insta"),  # 100s > 90s tolerance
        cs("development", 20 * 60 + 100, 20 * 60, "ide"),
    ]
    focus = build_focus_sessions(sessions)
    assert len(focus) == 2
    assert all(f.interruption_count == 0 for f in focus)


def test_two_short_interruptions_within_five_minutes_break_focus():
    sessions = [
        cs("development", 0, 20 * 60, "ide"),
        cs("social", 20 * 60, 30, "a"),
        cs("development", 20 * 60 + 30, 60, "ide"),
        cs("social", 20 * 60 + 90, 30, "b"),  # second interruption < 5 min after the first
        cs("development", 20 * 60 + 120, 20 * 60, "ide"),
    ]
    focus = build_focus_sessions(sessions)
    # The block must end at the second (clustered) interruption, not absorb it.
    assert all(f.interruption_count <= 1 for f in focus)


def test_communication_session_is_always_an_interruption_regardless_of_duration():
    sessions = [
        cs("development", 0, 10 * 60, "ide"),
        cs("communication", 10 * 60, 15, "sms"),  # tiny, but communication -> interruption
        cs("development", 10 * 60 + 15, 10 * 60, "ide"),
    ]
    focus = build_focus_sessions(sessions)
    assert len(focus) == 1
    assert focus[0].interruption_count == 1


def test_deep_work_requires_forty_five_minutes_and_a_deep_capable_category():
    sessions = [cs("development", 0, 46 * 60)]
    focus = build_focus_sessions(sessions, deep_capable_categories=frozenset({"development"}))
    assert focus[0].is_deep_work

    focus_not_capable = build_focus_sessions(
        sessions, deep_capable_categories=frozenset({"writing"})
    )
    assert not focus_not_capable[0].is_deep_work


def test_deep_work_rejected_below_ninety_percent_attribution():
    # No interruption session at all here — just a silent gap between two same-category
    # sessions (e.g. unaccounted idle time), which is exactly what should erode attribution:
    # the window (start-to-end) grows across the gap but work_s (summed session durations)
    # doesn't, so a big enough gap drops attributed_ratio below the deep-work bar even though
    # the block's own duration still clears 45 minutes and it never triggers the interruption
    # rules (there's nothing here to count as an interruption).
    sessions = [
        cs("development", 0, 40 * 60, "ide"),
        cs("development", 40 * 60 + 400, 400, "ide"),  # 400s (~6.7 min) unaccounted gap first
    ]
    focus = build_focus_sessions(sessions, deep_capable_categories=frozenset({"development"}))
    assert len(focus) == 1
    assert focus[0].duration_s >= 45 * 60
    assert focus[0].attributed_ratio < 0.90
    assert focus[0].attributed_ratio >= 0.80  # still a valid focus session, just not deep work
    assert not focus[0].is_deep_work


@pytest.mark.parametrize(
    "switches_per_hour,focused_s,work_s,median_block_min,expected",
    [
        (0, 3600, 3600, 30, 0.0),  # no switching, fully focused, healthy block size -> minimum
        (12, 0, 3600, 0, 1.0),  # max switching, zero focus, zero block size -> maximum
    ],
)
def test_fragmentation_index_boundaries(
    switches_per_hour, focused_s, work_s, median_block_min, expected
):
    actual = fragmentation_index(switches_per_hour, focused_s, work_s, median_block_min)
    assert actual == pytest.approx(expected)


def test_quality_score_matches_the_spec_formula_by_hand():
    sessions = [cs("development", 0, 60 * 60, "ide")]  # 60 min, no interruptions, no tool switches
    focus = build_focus_sessions(sessions)[0]
    score = focus.quality_score(goal_alignment_weight=0.5)
    # q = 0.35*min(60/60,1) + 0.25*(1-0/max(1,60/15)) + 0.20*(1-min(0/6,1)) + 0.20*0.5
    #   = 0.35*1 + 0.25*1 + 0.20*1 + 0.10 = 0.90
    assert score == pytest.approx(0.90)
