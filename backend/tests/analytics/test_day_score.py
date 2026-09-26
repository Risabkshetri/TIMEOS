"""§23.3 rule 3's deterministic reference score."""

from timeos.analytics.day_score import NEUTRAL_SCORE, compute_reference_day_score
from timeos.schemas.ai_context import (
    AIContext,
    Baselines,
    DataQuality,
    FocusSummary,
    GoalSummary,
    Totals,
)


def _context(**focus_overrides) -> AIContext:
    focus_defaults = {
        "sessions": 0,
        "deep_sessions": 0,
        "longest_minutes": 0,
        "average_minutes": 0,
        "total_focus_minutes": 0,
        "avg_quality": 0.0,
        "fragmentation_index": None,
        "context_switches": 0,
        "switches_per_hour": 0.0,
        "interruptions": 0,
    }
    focus_defaults.update(focus_overrides)
    return AIContext(
        scope="day",
        date="2026-09-13",
        weekday="Sunday",
        data_quality=DataQuality(
            coverage_ratio=0.9,
            unknown_ratio=0.0,
            devices_reporting=["android"],
            unobserved_minutes=0,
            offline_minutes=0,
        ),
        totals=Totals(
            day_minutes=1440, observed_minutes=500, screen_minutes=400, active_minutes=350
        ),
        focus=FocusSummary(**focus_defaults),
        baselines=Baselines(
            window_days=30,
            valid_days=20,
            screen_minutes_mean=400,
            deep_work_minutes_mean=50,
            fragmentation_mean=0.4,
        ),
    )


def test_an_empty_neutral_day_scores_exactly_neutral():
    context = _context()
    assert compute_reference_day_score(context) == round(NEUTRAL_SCORE)


def test_deep_focus_and_low_fragmentation_raise_the_score_above_neutral():
    context = _context(
        deep_sessions=3, total_focus_minutes=180, fragmentation_index=0.1, interruptions=0
    )
    assert compute_reference_day_score(context) > NEUTRAL_SCORE


def test_high_fragmentation_and_interruptions_lower_the_score_below_neutral():
    context = _context(fragmentation_index=0.9, interruptions=20)
    assert compute_reference_day_score(context) < NEUTRAL_SCORE


def test_score_is_clamped_to_0_100():
    context = _context(deep_sessions=100, total_focus_minutes=10000, interruptions=0)
    assert compute_reference_day_score(context) <= 100

    context = _context(fragmentation_index=1.0, interruptions=1000)
    assert compute_reference_day_score(context) >= 0


def test_low_coverage_pulls_an_otherwise_extreme_score_toward_neutral():
    good_day = _context(deep_sessions=3, total_focus_minutes=180, fragmentation_index=0.1)
    good_score = compute_reference_day_score(good_day)

    low_coverage_data_quality = DataQuality(
        coverage_ratio=0.2,
        unknown_ratio=0.0,
        devices_reporting=["android"],
        unobserved_minutes=0,
        offline_minutes=0,
    )
    low_coverage_day = good_day.model_copy(update={"data_quality": low_coverage_data_quality})
    low_coverage_score = compute_reference_day_score(low_coverage_day)

    assert abs(low_coverage_score - NEUTRAL_SCORE) < abs(good_score - NEUTRAL_SCORE)


def test_goal_attainment_above_pace_raises_the_score():
    on_pace = _context()
    ahead = on_pace.model_copy(
        update={
            "goals": [
                GoalSummary(
                    name="Build",
                    priority=1,
                    target_weekly_minutes=600,
                    aligned_minutes_today=200,
                    uncertainty=10,
                    week_attainment=1.2,
                )
            ]
        }
    )
    behind = on_pace.model_copy(
        update={
            "goals": [
                GoalSummary(
                    name="Build",
                    priority=1,
                    target_weekly_minutes=600,
                    aligned_minutes_today=10,
                    uncertainty=5,
                    week_attainment=0.1,
                )
            ]
        }
    )
    assert compute_reference_day_score(ahead) > compute_reference_day_score(on_pace)
    assert compute_reference_day_score(behind) < compute_reference_day_score(on_pace)
