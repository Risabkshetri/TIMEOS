"""§17 distraction engine — the 4 v1 detectors implementable without Phase 6/11 infrastructure."""

from datetime import UTC, datetime, timedelta

from timeos.analytics.distraction import (
    detect_distraction_burst,
    detect_habitual_checking,
    detect_post_task_avoidance,
    detect_switch_storm,
)
from timeos.analytics.focus import ClassifiedSession

T0 = datetime(2026, 9, 14, 9, 0, 0, tzinfo=UTC)
WORK = frozenset({"development", "writing"})


def cs(category: str, start_offset_s: float, duration_s: float, app_key: str | None = None) -> ClassifiedSession:
    start = T0 + timedelta(seconds=start_offset_s)
    return ClassifiedSession(
        app_key=app_key or category,
        category_key=category,
        start_ts=start,
        end_ts=start + timedelta(seconds=duration_s),
    )


# --- DISTRACTION_BURST ------------------------------------------------------------------------


def test_distraction_burst_needs_at_least_three_sessions_and_five_minutes_total():
    sessions = [
        cs("social", 0, 120, "a"),
        cs("social", 200, 120, "b"),
        cs("entertainment", 400, 120, "c"),  # 3 sessions, 360s total, all within 15 min
    ]
    occurrences = detect_distraction_burst(sessions, WORK)
    assert len(occurrences) == 1
    assert occurrences[0].pattern_type == "DISTRACTION_BURST"


def test_two_non_work_sessions_do_not_trigger_a_burst():
    sessions = [cs("social", 0, 200, "a"), cs("social", 300, 200, "b")]
    assert detect_distraction_burst(sessions, WORK) == []


def test_work_sessions_are_excluded_from_burst_detection():
    sessions = [cs("development", 0, 120), cs("development", 200, 120), cs("development", 400, 120)]
    assert detect_distraction_burst(sessions, WORK) == []


def test_sessions_spread_beyond_fifteen_minutes_do_not_form_one_burst():
    sessions = [
        cs("social", 0, 120, "a"),
        cs("social", 1000, 120, "b"),
        cs("social", 2000, 120, "c"),  # spans >15 min total
    ]
    assert detect_distraction_burst(sessions, WORK) == []


# --- HABITUAL_CHECKING -------------------------------------------------------------------------


def test_habitual_checking_needs_five_opens_and_low_median_duration():
    sessions = [cs("social", i * 300, 10, "insta") for i in range(5)]  # 5 opens over 20 min, 10s each
    occurrences = detect_habitual_checking(sessions)
    assert len(occurrences) == 1
    assert occurrences[0].support["app_key"] == "insta"


def test_four_opens_do_not_trigger_habitual_checking():
    sessions = [cs("social", i * 300, 10, "insta") for i in range(4)]
    assert detect_habitual_checking(sessions) == []


def test_five_opens_with_long_sessions_do_not_trigger_habitual_checking():
    # Real engagement, not checking: 5 opens but each is a genuine 25-minute session.
    sessions = [cs("social", i * 1600, 1500, "insta") for i in range(5)]
    assert detect_habitual_checking(sessions) == []


def test_different_apps_are_tracked_independently():
    sessions = [cs("social", i * 300, 10, "insta") for i in range(3)] + [
        cs("social", i * 300, 10, "twitter") for i in range(3)
    ]
    # 3 opens each — below the 5-open threshold for either app individually.
    assert detect_habitual_checking(sessions) == []


# --- SWITCH_STORM --------------------------------------------------------------------------------


def test_switch_storm_needs_twenty_context_switches_in_twenty_minutes():
    # Alternate between two categories 21 times inside a 20-minute window.
    sessions = [
        cs("development" if i % 2 == 0 else "social", i * 50, 10, f"app{i}") for i in range(21)
    ]
    occurrences = detect_switch_storm(sessions)
    assert len(occurrences) == 1
    assert occurrences[0].support["context_switches"] >= 20


def test_same_category_sequence_never_triggers_switch_storm():
    sessions = [cs("development", i * 50, 10, f"app{i}") for i in range(30)]
    assert detect_switch_storm(sessions) == []


# --- POST_TASK_AVOIDANCE -------------------------------------------------------------------------


def test_post_task_avoidance_detected_when_work_does_not_resume():
    sessions = [
        cs("development", 0, 25 * 60, "ide"),  # >=20 min work
        cs("social", 25 * 60 + 60, 15 * 60, "insta"),  # begins 1 min later, lasts 15 min (>=10 min)
        # no work session at all afterwards
    ]
    occurrences = detect_post_task_avoidance(sessions, WORK)
    assert len(occurrences) == 1
    assert occurrences[0].pattern_type == "POST_TASK_AVOIDANCE"


def test_no_avoidance_when_work_resumes_within_thirty_minutes():
    sessions = [
        cs("development", 0, 25 * 60, "ide"),
        cs("social", 25 * 60 + 60, 15 * 60, "insta"),
        cs("development", 25 * 60 + 60 + 15 * 60 + 10, 10 * 60, "ide"),  # resumes well inside 30 min
    ]
    assert detect_post_task_avoidance(sessions, WORK) == []


def test_no_avoidance_when_work_session_is_too_short():
    sessions = [
        cs("development", 0, 10 * 60, "ide"),  # < 20 min work
        cs("social", 10 * 60 + 60, 15 * 60, "insta"),
    ]
    assert detect_post_task_avoidance(sessions, WORK) == []


def test_no_avoidance_when_followup_is_too_brief():
    sessions = [
        cs("development", 0, 25 * 60, "ide"),
        cs("social", 25 * 60 + 60, 60, "insta"),  # only 1 min, below the 10-min followup bar
    ]
    assert detect_post_task_avoidance(sessions, WORK) == []


def test_no_avoidance_when_followup_starts_outside_the_three_minute_window():
    sessions = [
        cs("development", 0, 25 * 60, "ide"),
        cs("social", 25 * 60 + 5 * 60, 15 * 60, "insta"),  # starts 5 min later, outside 3-min window
    ]
    assert detect_post_task_avoidance(sessions, WORK) == []
