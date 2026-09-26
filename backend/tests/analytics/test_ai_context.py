"""§21 AI Context Builder: "deterministic, versioned, hash-addressed... a pure function... with a
golden-file test." The golden fixture mirrors §21's own worked example as closely as the spec's
numbers allow — the one deliberate deviation is `weekday`: the spec's example labels 2026-09-13
"Saturday", but that date is a real Sunday on the Gregorian calendar (verified independently via
Python's own `date.strftime`) — a doc typo, not a contract this deterministic function should
reproduce. Every other number in the fixture is chosen to make §21's example values fall out of
this module's actual arithmetic (e.g. category share = minutes / totals.screen_minutes).
"""

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from timeos.analytics.ai_context import (
    MAX_TOP_ATTENTION,
    AIContextInputs,
    BaselinesInput,
    CategoryInput,
    DataQualityInput,
    FocusInput,
    GoalInput,
    PatternInput,
    TimeOfDaySlotInput,
    TopAttentionInput,
    TotalsInput,
    build_ai_context,
)
from timeos.schemas.ai_context import MAX_CATEGORIES, MAX_GOALS, MAX_PATTERNS

GOLDEN_PATH = Path(__file__).parent / "golden" / "ai_context_day.json"


def _golden_inputs() -> AIContextInputs:
    return AIContextInputs(
        scope="day",
        date=date(2026, 9, 13),
        data_quality=DataQualityInput(
            coverage_ratio=0.87,
            unknown_ratio=0.12,
            devices_reporting=["android", "desktop"],
            unobserved_minutes=95,
            offline_minutes=0,
            caveats=["laptop unobserved 13:10-14:45"],
        ),
        totals=TotalsInput(
            day_minutes=1440, observed_minutes=1252, screen_minutes=431, active_minutes=388
        ),
        categories=[
            CategoryInput(category="Development", minutes=186, sessions=22, avg_confidence=0.88)
        ],
        top_attention=[TopAttentionInput(category="Development", total_minutes=150, sessions=22)],
        focus=FocusInput(
            sessions=4,
            deep_sessions=1,
            longest_minutes=52,
            average_minutes=24,
            total_focus_minutes=96,
            avg_quality=0.61,
            fragmentation_index=0.58,
            context_switches=47,
            switches_per_hour=6.1,
            interruptions=13,
        ),
        time_of_day=[
            TimeOfDaySlotInput(slot="09:00-12:00", focus_minutes=62, distraction_minutes=18)
        ],
        goals=[
            GoalInput(
                name="Build",
                priority=1,
                target_weekly_minutes=1200,
                aligned_minutes_today=186,
                uncertainty_minutes=28,
                week_attainment=0.41,
            )
        ],
        patterns=[
            PatternInput(
                pattern_type="POST_TASK_AVOIDANCE", occurrences=3, strength=0.66, status="confirmed"
            )
        ],
        baselines=BaselinesInput(
            window_days=30,
            valid_days=26,
            screen_minutes_mean=452,
            deep_work_minutes_mean=61,
            fragmentation_mean=0.48,
            today_deep_work_minutes=70,
        ),
    )


def test_matches_the_golden_fixture_exactly():
    context = build_ai_context(_golden_inputs())
    expected = json.loads(GOLDEN_PATH.read_text())
    assert context.model_dump(mode="json") == expected


def test_is_deterministic_same_inputs_same_output():
    first = build_ai_context(_golden_inputs()).model_dump(mode="json")
    second = build_ai_context(_golden_inputs()).model_dump(mode="json")
    assert first == second


def test_category_share_is_relative_to_screen_minutes():
    inputs = _golden_inputs()
    context = build_ai_context(inputs)
    assert context.categories[0].share == pytest.approx(186 / 431, abs=0.005)


def test_categories_are_capped_and_sorted_by_minutes_descending():
    inputs = _golden_inputs()
    many_categories = [
        CategoryInput(category=f"cat{i}", minutes=i, sessions=1, avg_confidence=0.9)
        for i in range(MAX_CATEGORIES + 5)
    ]
    inputs = replace(inputs, categories=many_categories)

    context = build_ai_context(inputs)

    assert len(context.categories) == MAX_CATEGORIES
    minutes = [c.minutes for c in context.categories]
    assert minutes == sorted(minutes, reverse=True)


def test_goals_are_capped_at_max_goals():
    inputs = _golden_inputs()
    many_goals = [
        GoalInput(
            name=f"g{i}",
            priority=(i % 5) + 1,
            target_weekly_minutes=100,
            aligned_minutes_today=10,
            uncertainty_minutes=2,
            week_attainment=0.1,
        )
        for i in range(MAX_GOALS + 5)
    ]
    inputs = replace(inputs, goals=many_goals)

    context = build_ai_context(inputs)
    assert len(context.goals) == MAX_GOALS


def test_patterns_are_capped_at_max_patterns():
    inputs = _golden_inputs()
    many_patterns = [
        PatternInput(pattern_type=f"p{i}", occurrences=3, strength=0.5, status="confirmed")
        for i in range(MAX_PATTERNS + 5)
    ]
    inputs = replace(inputs, patterns=many_patterns)

    context = build_ai_context(inputs)
    assert len(context.patterns) == MAX_PATTERNS


def test_top_attention_never_carries_the_raw_minute_count():
    # §20.4: "the AI sees category + rank + duration bucket only" — the exact total_minutes value
    # (150) must never appear anywhere in the serialized top_attention entry.
    context = build_ai_context(_golden_inputs())
    entry = context.top_attention[0].model_dump()
    assert 150 not in entry.values()
    assert entry == {"rank": 1, "category": "Development", "bucket": "2-3h", "sessions": 22}


@pytest.mark.parametrize(
    "minutes,expected_bucket",
    [
        (0, "<15m"),
        (14.9, "<15m"),
        (15, "15-30m"),
        (59, "30-60m"),
        (119, "1-2h"),
        (179, "2-3h"),
        (239, "3-4h"),
        (240, "4h+"),
        (600, "4h+"),
    ],
)
def test_duration_bucket_boundaries(minutes, expected_bucket):
    inputs = replace(
        _golden_inputs(),
        top_attention=[TopAttentionInput(category="X", total_minutes=minutes, sessions=1)],
    )
    context = build_ai_context(inputs)
    assert context.top_attention[0].bucket == expected_bucket


def test_top_attention_is_capped_at_max_top_attention():
    inputs = _golden_inputs()
    many_apps = [
        TopAttentionInput(category=f"cat{i}", total_minutes=i, sessions=1)
        for i in range(MAX_TOP_ATTENTION + 5)
    ]
    inputs = replace(inputs, top_attention=many_apps)

    context = build_ai_context(inputs)
    assert len(context.top_attention) == MAX_TOP_ATTENTION
    assert context.top_attention[0].rank == 1


def test_null_fragmentation_index_omits_the_baseline_delta():
    inputs = _golden_inputs()
    focus_without_fragmentation = replace(inputs.focus, fragmentation_index=None)
    inputs = replace(inputs, focus=focus_without_fragmentation)

    context = build_ai_context(inputs)
    assert context.focus.fragmentation_index is None
    assert "fragmentation" not in context.baselines.today_vs_mean


def test_weekday_is_derived_from_the_real_calendar_not_hardcoded():
    monday_inputs = replace(_golden_inputs(), date=date(2026, 9, 14))
    context = build_ai_context(monday_inputs)
    assert context.weekday == "Monday"
