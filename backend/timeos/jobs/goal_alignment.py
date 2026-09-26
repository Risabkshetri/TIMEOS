"""§18's goal-alignment computation, shared between `GET /v1/goals/{id}/alignment` (Phase 6) and
the AI context builder (Phase 7, `timeos.jobs.build_ai_context`). Lives in `timeos.jobs` — not
`timeos.api.goals`, where this logic originally lived — because an analytics/job module must never
depend on an API module (that dependency direction would run backwards through the whole
codebase's layering); `timeos.api.goals` now calls this instead of the reverse.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.analytics.goals import (
    ActivityForAlignment,
    AlignmentResult,
    GoalMapping,
    compute_alignment,
)
from timeos.ingest.service import local_date_for_event
from timeos.jobs.pipeline import ensure_day_computed
from timeos.jobs.seed_categories import TAXONOMY
from timeos.models.activity import Activity
from timeos.models.app_session import AppSession
from timeos.models.user import User
from timeos.models.working_hours import WorkingHours


def work_category_ids(category_key_to_id: dict[str, uuid.UUID]) -> frozenset[uuid.UUID]:
    """§18: "time_window_factor ... for work-type goals" — a goal counts as work-type when one of
    its category mappings falls under seed_categories.TAXONOMY's "Work" group (its own key or any
    child: deep_work, focused_work, development, research, writing, meetings, admin)."""
    work_keys = {"work"} | {
        child_key
        for parent_key, _label, _is_system, children in TAXONOMY
        if parent_key == "work"
        for child_key, _child_label, _child_is_system in children
    }
    return frozenset(category_key_to_id[key] for key in work_keys if key in category_key_to_id)


async def compute_goal_alignment(
    db: AsyncSession,
    user: User,
    mappings: list[GoalMapping],
    category_key_to_id: dict[str, uuid.UUID],
    window_days: int,
    as_of_date: date | None = None,
) -> tuple[AlignmentResult, float]:
    """Returns (alignment over the trailing `window_days` ending at `as_of_date` inclusive,
    average coverage_ratio across those days). `as_of_date` defaults to the user's current local
    date (wall-clock "today") — the live `/v1/goals/{id}/alignment` endpoint always wants that;
    the AI context builder passes the specific historical date it's assembling a context FOR,
    since "today" there means "the day this context describes", not the day the builder happens
    to run. Callers derive `target_minutes`/`attainment_ratio` themselves — those are
    goal-specific, not part of what this shared computation needs to know."""
    categorized_work_ids = work_category_ids(category_key_to_id)

    working_hours_by_weekday = {
        row.weekday: row
        for row in (
            (await db.execute(select(WorkingHours).where(WorkingHours.user_id == user.id)))
            .scalars()
            .all()
        )
    }
    tz = ZoneInfo(user.timezone)

    anchor_date = as_of_date or local_date_for_event(
        int(datetime.now(UTC).timestamp() * 1000), user.timezone, user.day_start_hour
    )
    window_dates = [anchor_date - timedelta(days=i) for i in range(window_days)]

    activities_for_alignment: list[ActivityForAlignment] = []
    coverage_ratios: list[float] = []

    for local_date in window_dates:
        metrics = await ensure_day_computed(db, user, local_date)
        coverage_ratios.append(float(metrics.coverage_ratio))

        activity_rows = (
            (
                await db.execute(
                    select(Activity).where(
                        Activity.user_id == user.id,
                        Activity.start_ts >= metrics.day_start_utc,
                        Activity.start_ts < metrics.day_end_utc,
                        Activity.superseded_by.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not activity_rows:
            continue

        session_ids = {sid for a in activity_rows for sid in a.source_session_ids}
        app_key_by_session_id: dict[uuid.UUID, str] = {}
        if session_ids:
            rows = (
                await db.execute(
                    select(AppSession.id, AppSession.app_key).where(
                        AppSession.id.in_(session_ids)
                    )
                )
            ).all()
            app_key_by_session_id = dict(rows)

        for activity in activity_rows:
            # An activity can consolidate sessions from more than one app (activities.py's own
            # docstring: "an IDE/Terminal/Browser cluster"). App-key mapping match uses the
            # lowest app_key deterministically rather than modelling a set here — matches
            # timeos.analytics.goals.ActivityForAlignment's single-app_key shape, which every
            # other caller (and its test suite) already relies on.
            app_keys = {
                app_key_by_session_id[sid]
                for sid in activity.source_session_ids
                if sid in app_key_by_session_id
            }
            app_key = min(app_keys) if app_keys else None

            local_start = activity.start_ts.astimezone(tz)
            working_hours = working_hours_by_weekday.get(local_start.weekday())
            is_within_working_hours = (
                working_hours is not None
                and working_hours.start_local <= local_start.time() < working_hours.end_local
            )
            activities_for_alignment.append(
                ActivityForAlignment(
                    category_id=activity.category_id,
                    app_key=app_key,
                    duration_s=float(activity.duration_s),
                    confidence=float(activity.confidence),
                    is_within_working_hours=is_within_working_hours,
                )
            )

    avg_coverage_ratio = sum(coverage_ratios) / len(coverage_ratios) if coverage_ratios else 0.0

    result = compute_alignment(
        activities_for_alignment, mappings, categorized_work_ids, avg_coverage_ratio
    )
    return result, avg_coverage_ratio
