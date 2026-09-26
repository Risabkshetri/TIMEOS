"""§21's AI Context Builder, the DB-touching half: gathers real rows for one (user, local_date)
and turns them into `timeos.analytics.ai_context.AIContextInputs`, then calls that module's pure
`build_ai_context`. This module is NOT `timeos.ai` — it has full DB access, same as
`timeos.jobs.pipeline` — and its output must still pass through
`timeos.privacy.gate.enforce_privacy_gate` before anything downstream (an LLM, a preview endpoint)
ever sees it. Nothing here calls an LLM; Phase 7's objective is the boundary, not the client.

`time_of_day` is deliberately returned empty: per-slot distraction minutes would need the literal
time intervals DISTRACTION_BURST occurrences cover, and only their COUNT/strength is persisted
today (`behavioral_patterns.support`), not their intervals. Emitting a fabricated 0 there would
violate the same "never a fabricated number" principle §22 states for AI *output* — better an
honestly empty list than a number nothing actually measured. Filling this in needs either
persisting burst intervals or recomputing them on demand; deferred, not guessed.
"""

from __future__ import annotations

import statistics
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.analytics.ai_context import (
    AIContext,
    AIContextInputs,
    BaselinesInput,
    CategoryInput,
    DataQualityInput,
    FocusInput,
    GoalInput,
    PatternInput,
    TopAttentionInput,
    TotalsInput,
    build_ai_context,
)
from timeos.analytics.focus import FocusSession
from timeos.analytics.goals import GoalMapping, attainment_ratio
from timeos.analytics.metrics import COVERAGE_GATE_RATIO
from timeos.jobs.goal_alignment import compute_goal_alignment
from timeos.jobs.pipeline import ensure_day_computed
from timeos.jobs.seed_categories import ensure_system_categories
from timeos.models.activity import Activity
from timeos.models.activity_category import ActivityCategory
from timeos.models.app_session import AppSession
from timeos.models.behavioral_pattern import BehavioralPattern
from timeos.models.daily_metric import DailyMetric
from timeos.models.device import Device
from timeos.models.device_coverage import DeviceCoverage
from timeos.models.focus_session import FocusSessionRow
from timeos.models.goal import Goal
from timeos.models.goal_activity_mapping import GoalActivityMapping
from timeos.models.user import User

BASELINE_WINDOW_DAYS = 30
GOAL_ALIGNMENT_WEEK_DAYS = 7


async def _data_quality(db: AsyncSession, user: User, metrics: DailyMetric) -> DataQualityInput:
    platforms = (
        (
            await db.execute(
                select(Device.platform)
                .distinct()
                .join(DeviceCoverage, DeviceCoverage.device_id == Device.id)
                .where(
                    Device.user_id == user.id,
                    DeviceCoverage.start_ts < metrics.day_end_utc,
                    DeviceCoverage.end_ts > metrics.day_start_utc,
                )
            )
        )
        .scalars()
        .all()
    )
    return DataQualityInput(
        coverage_ratio=float(metrics.coverage_ratio),
        unknown_ratio=float(metrics.unknown_ratio),
        devices_reporting=sorted(platforms),
        unobserved_minutes=round(float(metrics.unobserved_s) / 60),
        offline_minutes=round(float(metrics.offline_s) / 60),
    )


async def _categories_and_top_attention(
    db: AsyncSession, user: User, metrics: DailyMetric
) -> tuple[list[CategoryInput], list[TopAttentionInput]]:
    rows = (
        await db.execute(
            select(Activity, ActivityCategory.label)
            .join(ActivityCategory, ActivityCategory.id == Activity.category_id)
            .where(
                Activity.user_id == user.id,
                Activity.start_ts >= metrics.day_start_utc,
                Activity.start_ts < metrics.day_end_utc,
                Activity.superseded_by.is_(None),
                ActivityCategory.is_system.is_(False),
            )
        )
    ).all()

    category_minutes: dict[str, float] = {}
    category_sessions: dict[str, int] = {}
    category_confidence_sum: dict[str, float] = {}
    all_session_ids: set[uuid.UUID] = set()

    for activity, label in rows:
        minutes = float(activity.duration_s) / 60
        category_minutes[label] = category_minutes.get(label, 0.0) + minutes
        category_sessions[label] = category_sessions.get(label, 0) + 1
        category_confidence_sum[label] = category_confidence_sum.get(label, 0.0) + float(
            activity.confidence
        )
        all_session_ids.update(activity.source_session_ids)

    categories = [
        CategoryInput(
            category=label,
            minutes=round(minutes),
            sessions=category_sessions[label],
            avg_confidence=category_confidence_sum[label] / category_sessions[label],
        )
        for label, minutes in category_minutes.items()
    ]

    app_key_by_session_id: dict[uuid.UUID, str] = {}
    duration_by_session_id: dict[uuid.UUID, float] = {}
    if all_session_ids:
        session_rows = (
            await db.execute(
                select(AppSession.id, AppSession.app_key, AppSession.duration_s).where(
                    AppSession.id.in_(all_session_ids)
                )
            )
        ).all()
        for session_id, app_key, duration_s in session_rows:
            app_key_by_session_id[session_id] = app_key
            duration_by_session_id[session_id] = float(duration_s)

    app_minutes: dict[str, float] = {}
    app_sessions: dict[str, int] = {}
    app_category: dict[str, str] = {}
    for activity, label in rows:
        for session_id in activity.source_session_ids:
            app_key = app_key_by_session_id.get(session_id)
            if app_key is None:
                continue
            app_minutes[app_key] = app_minutes.get(app_key, 0.0) + (
                duration_by_session_id.get(session_id, 0.0) / 60
            )
            app_sessions[app_key] = app_sessions.get(app_key, 0) + 1
            app_category[app_key] = label  # an app's category is stable enough to just overwrite

    top_attention = [
        TopAttentionInput(
            category=app_category[app_key], total_minutes=minutes, sessions=app_sessions[app_key]
        )
        for app_key, minutes in app_minutes.items()
    ]

    return categories, top_attention


async def _focus(db: AsyncSession, user: User, metrics: DailyMetric) -> FocusInput:
    rows = (
        (
            await db.execute(
                select(FocusSessionRow).where(
                    FocusSessionRow.user_id == user.id,
                    FocusSessionRow.start_ts >= metrics.day_start_utc,
                    FocusSessionRow.start_ts < metrics.day_end_utc,
                )
            )
        )
        .scalars()
        .all()
    )

    durations_min = [float(r.duration_s) / 60 for r in rows]
    quality_scores = [
        FocusSession(
            category_key="",  # unused by quality_score(); avoids a redundant category lookup
            start_ts=r.start_ts,
            end_ts=r.end_ts,
            interruption_count=r.interruption_count,
            tool_switch_count=r.tool_switch_count,
            attributed_ratio=float(r.attributed_ratio),
            is_deep_work=r.is_deep_work,
        ).quality_score(0.0)
        for r in rows
    ]

    return FocusInput(
        sessions=len(rows),
        deep_sessions=sum(1 for r in rows if r.is_deep_work),
        longest_minutes=round(max(durations_min)) if durations_min else 0,
        average_minutes=round(statistics.mean(durations_min)) if durations_min else 0,
        total_focus_minutes=round(sum(durations_min)),
        avg_quality=statistics.mean(quality_scores) if quality_scores else 0.0,
        fragmentation_index=(
            float(metrics.fragmentation_index) if metrics.fragmentation_index is not None else None
        ),
        context_switches=metrics.context_switches,
        switches_per_hour=float(metrics.switches_per_hour),
        interruptions=metrics.interruptions,
    )


async def _goals(
    db: AsyncSession, user: User, local_date: date, category_key_to_id: dict[str, uuid.UUID]
) -> list[GoalInput]:
    goal_rows = (
        (
            await db.execute(
                select(Goal).where(
                    Goal.user_id == user.id,
                    Goal.archived_at.is_(None),
                    Goal.active_from <= local_date,
                    (Goal.active_to.is_(None)) | (Goal.active_to >= local_date),
                )
            )
        )
        .scalars()
        .all()
    )

    goals: list[GoalInput] = []
    for goal in goal_rows:
        mapping_rows = (
            (
                await db.execute(
                    select(GoalActivityMapping).where(GoalActivityMapping.goal_id == goal.id)
                )
            )
            .scalars()
            .all()
        )
        mappings = [
            GoalMapping(category_id=m.category_id, app_key=m.app_key, weight=float(m.weight))
            for m in mapping_rows
        ]

        today_result, _today_coverage = await compute_goal_alignment(
            db, user, mappings, category_key_to_id, window_days=1, as_of_date=local_date
        )
        week_result, _week_coverage = await compute_goal_alignment(
            db,
            user,
            mappings,
            category_key_to_id,
            window_days=GOAL_ALIGNMENT_WEEK_DAYS,
            as_of_date=local_date,
        )

        goals.append(
            GoalInput(
                name=goal.name,
                priority=goal.priority,
                target_weekly_minutes=round(float(goal.target_minutes_per_week)),
                aligned_minutes_today=today_result.aligned_minutes,
                uncertainty_minutes=today_result.range_high_minutes - today_result.aligned_minutes,
                week_attainment=attainment_ratio(
                    week_result.aligned_minutes, float(goal.target_minutes_per_week)
                ),
            )
        )
    return goals


async def _patterns(db: AsyncSession, user: User) -> list[PatternInput]:
    # §17: only CONFIRMED patterns are allowed into the AI context.
    rows = (
        (
            await db.execute(
                select(BehavioralPattern).where(
                    BehavioralPattern.user_id == user.id,
                    BehavioralPattern.status == "confirmed",
                )
            )
        )
        .scalars()
        .all()
    )
    return [
        PatternInput(
            pattern_type=r.pattern_type,
            occurrences=r.occurrences,
            strength=float(r.strength),
            status=r.status,
        )
        for r in rows
    ]


async def _baselines(
    db: AsyncSession, user: User, local_date: date, today_focus: FocusInput
) -> BaselinesInput:
    window_start = local_date - timedelta(days=BASELINE_WINDOW_DAYS)
    rows = (
        (
            await db.execute(
                select(DailyMetric).where(
                    DailyMetric.user_id == user.id,
                    DailyMetric.local_date >= window_start,
                    DailyMetric.local_date < local_date,
                )
            )
        )
        .scalars()
        .all()
    )
    valid_rows = [r for r in rows if float(r.coverage_ratio) >= COVERAGE_GATE_RATIO]

    screen_minutes_mean = (
        statistics.mean(float(r.screen_time_s) / 60 for r in valid_rows) if valid_rows else 0.0
    )
    deep_work_minutes_mean = (
        statistics.mean(float(r.deep_work_s) / 60 for r in valid_rows) if valid_rows else 0.0
    )
    fragmentation_values = [
        float(r.fragmentation_index) for r in valid_rows if r.fragmentation_index is not None
    ]
    fragmentation_mean = statistics.mean(fragmentation_values) if fragmentation_values else 0.0

    return BaselinesInput(
        window_days=BASELINE_WINDOW_DAYS,
        valid_days=len(valid_rows),
        screen_minutes_mean=screen_minutes_mean,
        deep_work_minutes_mean=deep_work_minutes_mean,
        fragmentation_mean=fragmentation_mean,
        today_deep_work_minutes=today_focus.total_focus_minutes,
    )


async def build_ai_context_for_day(db: AsyncSession, user: User, local_date: date) -> AIContext:
    metrics = await ensure_day_computed(db, user, local_date)
    category_key_to_id = await ensure_system_categories(db, user.id)

    data_quality = await _data_quality(db, user, metrics)
    categories, top_attention = await _categories_and_top_attention(db, user, metrics)
    focus = await _focus(db, user, metrics)
    goals = await _goals(db, user, local_date, category_key_to_id)
    patterns = await _patterns(db, user)
    baselines = await _baselines(db, user, local_date, focus)

    inputs = AIContextInputs(
        scope="day",
        date=local_date,
        data_quality=data_quality,
        totals=TotalsInput(
            day_minutes=round(float(metrics.duration_seconds) / 60),
            observed_minutes=round(float(metrics.observed_s) / 60),
            screen_minutes=round(float(metrics.screen_time_s) / 60),
            active_minutes=round(float(metrics.active_time_s) / 60),
        ),
        categories=categories,
        top_attention=top_attention,
        focus=focus,
        time_of_day=[],
        goals=goals,
        patterns=patterns,
        baselines=baselines,
    )
    return build_ai_context(inputs)
