"""§18 Goal Alignment Engine."""

import uuid

import pytest

from timeos.analytics.goals import (
    ActivityForAlignment,
    GoalMapping,
    attainment_ratio,
    compute_alignment,
)

DEV_CATEGORY = uuid.uuid4()
WRITING_CATEGORY = uuid.uuid4()
SOCIAL_CATEGORY = uuid.uuid4()
WORK_CATEGORIES = frozenset({DEV_CATEGORY, WRITING_CATEGORY})


def activity(
    category_id=DEV_CATEGORY,
    app_key=None,
    duration_s=3600,
    confidence=1.0,
    is_within_working_hours=True,
) -> ActivityForAlignment:
    return ActivityForAlignment(
        category_id=category_id,
        app_key=app_key,
        duration_s=duration_s,
        confidence=confidence,
        is_within_working_hours=is_within_working_hours,
    )


def test_full_confidence_full_weight_activity_counts_in_full():
    mappings = [GoalMapping(category_id=DEV_CATEGORY, app_key=None, weight=1.0)]
    result = compute_alignment(
        [activity(duration_s=3600, confidence=1.0)], mappings, WORK_CATEGORIES, coverage_ratio=1.0
    )
    assert result.aligned_minutes == pytest.approx(60.0)


def test_confidence_weighting_scales_the_contribution():
    # §18's own formula: duration_min * weight * confidence * time_window_factor.
    mappings = [GoalMapping(category_id=DEV_CATEGORY, app_key=None, weight=1.0)]
    result = compute_alignment(
        [activity(duration_s=3600, confidence=0.5)], mappings, WORK_CATEGORIES, coverage_ratio=1.0
    )
    assert result.aligned_minutes == pytest.approx(30.0)


def test_mapping_weight_scales_the_contribution():
    mappings = [GoalMapping(category_id=DEV_CATEGORY, app_key=None, weight=0.5)]
    result = compute_alignment(
        [activity(duration_s=3600, confidence=1.0)], mappings, WORK_CATEGORIES, coverage_ratio=1.0
    )
    assert result.aligned_minutes == pytest.approx(30.0)


def test_activities_matching_no_mapping_are_unallocated_not_redistributed():
    # §18's failure case: "unallocated time never redistributed" — an activity that matches
    # NEITHER of a goal's mappings must contribute exactly zero, never get spread across the
    # goal's other matching activities to inflate their share.
    mappings = [GoalMapping(category_id=DEV_CATEGORY, app_key=None, weight=1.0)]
    activities = [
        activity(category_id=DEV_CATEGORY, duration_s=1800, confidence=1.0),
        activity(category_id=SOCIAL_CATEGORY, duration_s=1800, confidence=1.0),  # doesn't match
    ]
    result = compute_alignment(activities, mappings, WORK_CATEGORIES, coverage_ratio=1.0)
    assert result.aligned_minutes == pytest.approx(30.0)  # only the matching 1800s, not 3600s


def test_working_hours_penalty_applies_to_work_type_goals_outside_hours():
    mappings = [GoalMapping(category_id=DEV_CATEGORY, app_key=None, weight=1.0)]
    result = compute_alignment(
        [activity(duration_s=3600, confidence=1.0, is_within_working_hours=False)],
        mappings,
        WORK_CATEGORIES,
        coverage_ratio=1.0,
    )
    assert result.aligned_minutes == pytest.approx(60.0 * 0.85)


def test_working_hours_penalty_does_not_apply_to_non_work_type_goals():
    # An app-only-mapped goal (e.g. "limit Instagram") isn't work-type — working hours are
    # irrelevant to it regardless of when the matching activity happened.
    mappings = [GoalMapping(category_id=None, app_key="com.instagram.android", weight=1.0)]
    result = compute_alignment(
        [
            activity(
                category_id=SOCIAL_CATEGORY,
                app_key="com.instagram.android",
                duration_s=3600,
                confidence=1.0,
                is_within_working_hours=False,
            )
        ],
        mappings,
        WORK_CATEGORIES,
        coverage_ratio=1.0,
    )
    assert result.aligned_minutes == pytest.approx(60.0)


def test_overlapping_mappings_on_one_activity_are_capped_at_full_weight():
    # §18's failure case: "overlapping goal mappings (weights must not exceed 1 per activity)".
    # Both a category mapping and an app mapping match the SAME activity here; summing their
    # weights (0.7 + 0.7 = 1.4) must not let this one activity count for more than its own
    # actual duration.
    mappings = [
        GoalMapping(category_id=DEV_CATEGORY, app_key=None, weight=0.7),
        GoalMapping(category_id=None, app_key="com.example.ide", weight=0.7),
    ]
    result = compute_alignment(
        [
            activity(
                category_id=DEV_CATEGORY,
                app_key="com.example.ide",
                duration_s=3600,
                confidence=1.0,
            )
        ],
        mappings,
        WORK_CATEGORIES,
        coverage_ratio=1.0,
    )
    assert result.aligned_minutes == pytest.approx(60.0)  # capped, not 84.0


def test_low_confidence_widens_the_uncertainty_range():
    mappings = [GoalMapping(category_id=DEV_CATEGORY, app_key=None, weight=1.0)]
    confident = compute_alignment(
        [activity(duration_s=3600, confidence=1.0)], mappings, WORK_CATEGORIES, coverage_ratio=1.0
    )
    uncertain = compute_alignment(
        [activity(duration_s=3600, confidence=0.6)], mappings, WORK_CATEGORIES, coverage_ratio=1.0
    )
    assert (confident.range_high_minutes - confident.range_low_minutes) == pytest.approx(0.0)
    assert (uncertain.range_high_minutes - uncertain.range_low_minutes) > 0.0


def test_low_coverage_widens_the_range_even_at_full_confidence():
    mappings = [GoalMapping(category_id=DEV_CATEGORY, app_key=None, weight=1.0)]
    full_coverage = compute_alignment(
        [activity(duration_s=3600, confidence=1.0)], mappings, WORK_CATEGORIES, coverage_ratio=1.0
    )
    low_coverage = compute_alignment(
        [activity(duration_s=3600, confidence=1.0)], mappings, WORK_CATEGORIES, coverage_ratio=0.3
    )
    assert (
        full_coverage.range_high_minutes - full_coverage.range_low_minutes
    ) == pytest.approx(0.0)
    assert (low_coverage.range_high_minutes - low_coverage.range_low_minutes) > 0.0


def test_range_never_goes_negative():
    mappings = [GoalMapping(category_id=DEV_CATEGORY, app_key=None, weight=1.0)]
    result = compute_alignment(
        [activity(duration_s=60, confidence=0.1)], mappings, WORK_CATEGORIES, coverage_ratio=0.0
    )
    assert result.range_low_minutes >= 0.0


def test_attainment_ratio_is_aligned_over_target():
    assert attainment_ratio(90.0, 60.0) == pytest.approx(1.5)


def test_attainment_ratio_with_zero_target_is_zero_not_a_crash():
    assert attainment_ratio(30.0, 0.0) == 0.0
