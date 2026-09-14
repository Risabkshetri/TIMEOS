"""Daily metrics aggregation — turns coverage + classified sessions + focus + distraction output
into the numeric fields of `daily_metrics` (§13, §14.3, §16).

This module only computes the ANALYTICALLY-derived fields. `day_start_utc`/`day_end_utc` (from the
user's `day_start_hour`), `tz_transition` (needs raw `tz_offset_min`, which isn't part of
`AnalyticsEvent`), `revised` (whether a row already existed for this date), `computed_at`, and
`pipeline_version` are the persistence layer's responsibility — this function has no way to know
any of them and shouldn't guess.

Category-time bucketing note: `deep_work_s`/`focused_work_s`/`shallow_work_s` are a three-way
partition of ALL work-type session time by how the focus engine treated it (inside a deep-work
session, inside a regular focus session, or "fragmented" — not in any focus session at all, per
§16's definition), not a partition by `activity_categories` leaf. `distraction_s` is the union of
time spans covered by DISTRACTION_BURST occurrences specifically (merged so overlaps aren't
double-counted) — the spec doesn't pin down this arithmetic precisely, and burst clusters are the
one detector whose occurrences describe a genuine, non-overlapping-by-construction span of "this
stretch of time looked like distraction", unlike HABITUAL_CHECKING (per-app, can overlap another
app's burst) or SWITCH_STORM/POST_TASK_AVOIDANCE (about switching behavior, not time spent).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime

from timeos.analytics.coverage import DEVICE_OFFLINE, IDLE, TRACKED, UNOBSERVED, CoverageInterval
from timeos.analytics.distraction import PatternOccurrence
from timeos.analytics.focus import (
    ClassifiedSession,
    FocusSession,
    count_context_switches,
    fragmentation_index,
)

WORK_CATEGORY_KEYS = frozenset(
    {"deep_work", "focused_work", "development", "research", "writing", "meetings", "admin"}
)

COVERAGE_GATE_RATIO = 0.6


@dataclass(frozen=True, slots=True)
class DailyMetricsResult:
    duration_seconds: float
    observed_s: float
    tracked_s: float
    idle_s: float
    unobserved_s: float
    offline_s: float
    coverage_ratio: float

    screen_time_s: float
    active_time_s: float

    deep_work_s: float
    focused_work_s: float
    shallow_work_s: float
    communication_s: float
    learning_s: float
    entertainment_s: float
    social_s: float
    distraction_s: float
    unknown_s: float
    unknown_ratio: float

    context_switches: int
    switches_per_hour: float
    interruptions: int
    fragmentation_index: float | None  # None when coverage_ratio < 0.6 gate (§14.3/§16)

    longest_focus_s: float
    avg_focus_s: float
    focus_session_count: int

    unlock_count: int


def compute_daily_metrics(
    *,
    window_start: datetime,
    window_end: datetime,
    coverage_intervals: list[CoverageInterval],
    screen_time_s: float,
    classified_sessions: list[ClassifiedSession],
    focus_sessions: list[FocusSession],
    distraction_bursts: list[PatternOccurrence],
    unlock_count: int,
) -> DailyMetricsResult:
    duration_seconds = (window_end - window_start).total_seconds()

    tracked_s = sum(i.duration_s for i in coverage_intervals if i.state == TRACKED)
    idle_s = sum(i.duration_s for i in coverage_intervals if i.state == IDLE)
    unobserved_s = sum(i.duration_s for i in coverage_intervals if i.state == UNOBSERVED)
    offline_s = sum(i.duration_s for i in coverage_intervals if i.state == DEVICE_OFFLINE)
    observed_s = tracked_s + idle_s
    ratio = observed_s / duration_seconds if duration_seconds > 0 else 0.0

    active_time_s = max(screen_time_s - idle_s, 0.0)

    total_session_s = sum(s.duration_s for s in classified_sessions)
    by_category: dict[str, float] = {}
    for s in classified_sessions:
        by_category[s.category_key] = by_category.get(s.category_key, 0.0) + s.duration_s

    deep_work_s = sum(f.duration_s for f in focus_sessions if f.is_deep_work)
    focused_work_s = sum(f.duration_s for f in focus_sessions if not f.is_deep_work)
    work_session_s = sum(v for k, v in by_category.items() if k in WORK_CATEGORY_KEYS)
    shallow_work_s = max(work_session_s - deep_work_s - focused_work_s, 0.0)

    communication_s = by_category.get("communication", 0.0)
    learning_s = by_category.get("learning", 0.0)
    entertainment_s = by_category.get("entertainment", 0.0)
    social_s = by_category.get("social", 0.0)
    unknown_s = by_category.get("unknown", 0.0)
    unknown_ratio = unknown_s / total_session_s if total_session_s > 0 else 0.0

    distraction_s = _merged_span_seconds(distraction_bursts)

    context_switches, _tool_switches = count_context_switches(classified_sessions)
    switches_per_hour = (
        context_switches / max(active_time_s / 3600, 1 / 3600) if active_time_s > 0 else 0.0
    )
    interruptions = sum(f.interruption_count for f in focus_sessions)

    frag_index = None
    if ratio >= COVERAGE_GATE_RATIO:
        work_sessions = [s for s in classified_sessions if s.category_key in WORK_CATEGORY_KEYS]
        median_work_block_min = (
            statistics.median(s.duration_s for s in work_sessions) / 60 if work_sessions else 0.0
        )
        focused_time_s = deep_work_s + focused_work_s
        frag_index = fragmentation_index(
            switches_per_hour,
            focused_time_s,
            max(work_session_s, focused_time_s),
            median_work_block_min,
        )

    focus_durations = [f.duration_s for f in focus_sessions]

    return DailyMetricsResult(
        duration_seconds=duration_seconds,
        observed_s=observed_s,
        tracked_s=tracked_s,
        idle_s=idle_s,
        unobserved_s=unobserved_s,
        offline_s=offline_s,
        coverage_ratio=ratio,
        screen_time_s=screen_time_s,
        active_time_s=active_time_s,
        deep_work_s=deep_work_s,
        focused_work_s=focused_work_s,
        shallow_work_s=shallow_work_s,
        communication_s=communication_s,
        learning_s=learning_s,
        entertainment_s=entertainment_s,
        social_s=social_s,
        distraction_s=distraction_s,
        unknown_s=unknown_s,
        unknown_ratio=unknown_ratio,
        context_switches=context_switches,
        switches_per_hour=switches_per_hour,
        interruptions=interruptions,
        fragmentation_index=frag_index,
        longest_focus_s=max(focus_durations, default=0.0),
        avg_focus_s=(sum(focus_durations) / len(focus_durations)) if focus_durations else 0.0,
        focus_session_count=len(focus_sessions),
        unlock_count=unlock_count,
    )


def _merged_span_seconds(occurrences: list[PatternOccurrence]) -> float:
    if not occurrences:
        return 0.0
    spans = sorted(((o.start_ts, o.end_ts) for o in occurrences), key=lambda span: span[0])
    total = 0.0
    current_start, current_end = spans[0]
    for start, end in spans[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += (current_end - current_start).total_seconds()
            current_start, current_end = start, end
    total += (current_end - current_start).total_seconds()
    return total
