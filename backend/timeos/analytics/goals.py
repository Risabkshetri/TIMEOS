"""Goal Alignment Engine — §18.

`aligned_minutes(goal) = sum over activities: duration_min * mapping_weight * activity.confidence
* time_window_factor`. This module is a pure function of (activities, mappings, working-hours
membership) — it never touches the DB — matching every other analytics module in this package.

The spec gives the point-estimate formula exactly but not the uncertainty range ("range: ±,
derived from the confidence distribution and coverage"). This module's interpretation, documented
where it's implemented: wider when contributing activities are less confident, and wider still
when the day's own coverage_ratio is low (§14.3's gate) — an aligned-minutes figure computed from
a mostly-UNOBSERVED day should visibly say so, exactly like every other metric in this system.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

TIME_WINDOW_FACTOR_INSIDE_WORKING_HOURS = 1.0
TIME_WINDOW_FACTOR_OUTSIDE_WORKING_HOURS = 0.85


@dataclass(frozen=True, slots=True)
class ActivityForAlignment:
    category_id: uuid.UUID
    app_key: str | None
    duration_s: float
    confidence: float
    is_within_working_hours: bool


@dataclass(frozen=True, slots=True)
class GoalMapping:
    category_id: uuid.UUID | None
    app_key: str | None
    weight: float


@dataclass(frozen=True, slots=True)
class AlignmentResult:
    aligned_minutes: float
    range_low_minutes: float
    range_high_minutes: float


def _matching_weight(activity: ActivityForAlignment, mappings: list[GoalMapping]) -> float:
    """§18's failure case: "overlapping goal mappings (weights must not exceed 1 per activity)".
    If more than one of a goal's OWN mappings matches the same activity (e.g. both a category
    mapping and an app mapping happen to match), summing their weights could attribute more than
    100% of that activity's own duration to a single goal — capped at 1.0 so one activity's time
    can never count for more than itself within one goal's alignment total."""
    matched = [
        m.weight
        for m in mappings
        if (m.category_id is not None and m.category_id == activity.category_id)
        or (m.app_key is not None and m.app_key == activity.app_key)
    ]
    return min(sum(matched), 1.0) if matched else 0.0


def _is_work_type_goal(
    mappings: list[GoalMapping], work_category_ids: frozenset[uuid.UUID]
) -> bool:
    """A goal is "work-type" (and thus subject to the working-hours time_window_factor) if any of
    its category mappings points at a work-group category. An app-only-mapped goal (e.g. "limit
    Instagram") isn't work-type — working hours have no bearing on it."""
    return any(m.category_id in work_category_ids for m in mappings if m.category_id is not None)


def compute_alignment(
    activities: list[ActivityForAlignment],
    mappings: list[GoalMapping],
    work_category_ids: frozenset[uuid.UUID],
    coverage_ratio: float,
) -> AlignmentResult:
    is_work_type = _is_work_type_goal(mappings, work_category_ids)

    aligned_seconds = 0.0
    uncertainty_seconds = 0.0

    for activity in activities:
        weight = _matching_weight(activity, mappings)
        if weight <= 0:
            continue
        time_window_factor = (
            (
                TIME_WINDOW_FACTOR_INSIDE_WORKING_HOURS
                if activity.is_within_working_hours
                else TIME_WINDOW_FACTOR_OUTSIDE_WORKING_HOURS
            )
            if is_work_type
            else 1.0
        )
        contribution = activity.duration_s * weight * activity.confidence * time_window_factor
        aligned_seconds += contribution
        # This activity's own uncertainty (1 - confidence) widens the range in proportion to how
        # much of the aligned total it contributed.
        uncertainty_seconds += contribution * (1 - activity.confidence)

    # §14.3: a day's own observation gap widens uncertainty on every metric derived from it, not
    # just the ones this module computes directly — half the unobserved fraction of the aligned
    # total, so a fully-observed day (coverage_ratio=1) adds no extra penalty at all.
    coverage_penalty_seconds = aligned_seconds * (1 - coverage_ratio) * 0.5

    half_width_seconds = uncertainty_seconds + coverage_penalty_seconds
    aligned_minutes = aligned_seconds / 60
    half_width_minutes = half_width_seconds / 60

    return AlignmentResult(
        aligned_minutes=aligned_minutes,
        range_low_minutes=max(aligned_minutes - half_width_minutes, 0.0),
        range_high_minutes=aligned_minutes + half_width_minutes,
    )


def attainment_ratio(aligned_minutes: float, target_minutes_per_week: float) -> float:
    if target_minutes_per_week <= 0:
        return 0.0
    return aligned_minutes / target_minutes_per_week
