"""§25 dashboard read API: /v1/days/{date} and /v1/days/{date}/timeline.

Computes lazily rather than on a schedule: Phase 4's own outputs list calls for a "scheduled
pipeline", which doesn't exist yet (no cron/APScheduler job calls `recompute_day` — see
timeos/jobs/pipeline.py's module docstring for what's built vs. deferred there). For a
single-owner personal dashboard, computing on first view (and re-computing when `dirty_days`
says a day changed since it was last computed) is a reasonable substitute: the owner always sees
fresh data when they look, without needing a background worker running. This should be revisited
if the dashboard ever needs sub-second responses on a day with heavy backlog, or serves more than
one concurrent viewer.
"""

from datetime import date as date_type

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.api.deps import get_current_user, get_db
from timeos.jobs.pipeline import recompute_day
from timeos.models.activity import Activity
from timeos.models.activity_category import ActivityCategory
from timeos.models.app_session import AppSession as AppSessionRow
from timeos.models.daily_metric import DailyMetric
from timeos.models.device import Device
from timeos.models.device_coverage import DeviceCoverage
from timeos.models.dirty_day import DirtyDay
from timeos.models.focus_session import FocusSessionRow
from timeos.models.user import User
from timeos.schemas.days import (
    ActivitiesResponse,
    ActivityOut,
    AppSessionOut,
    CategoryBreakdown,
    CoverageIntervalOut,
    DailyMetricsOut,
    DayResponse,
    DeviceTimelineOut,
    FocusResponse,
    FocusSessionOut,
    TimelineResponse,
)

router = APIRouter(prefix="/v1/days", tags=["days"])


async def _ensure_computed(db: AsyncSession, user: User, local_date: date_type) -> DailyMetric:
    existing = await db.get(DailyMetric, (user.id, local_date))
    dirty = await db.get(DirtyDay, (user.id, local_date))
    if existing is not None and dirty is None:
        return existing
    return await recompute_day(db, user, local_date)


@router.get("/{local_date}", response_model=DayResponse)
async def get_day(
    local_date: date_type,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DayResponse:
    metrics = await _ensure_computed(db, user, local_date)

    category_rows = (
        await db.execute(
            select(ActivityCategory.key, ActivityCategory.label, Activity.duration_s)
            .join(Activity, Activity.category_id == ActivityCategory.id)
            .where(
                Activity.user_id == user.id,
                Activity.start_ts >= metrics.day_start_utc,
                Activity.start_ts < metrics.day_end_utc,
            )
        )
    ).all()

    totals: dict[str, CategoryBreakdown] = {}
    for key, label, duration_s in category_rows:
        if key in totals:
            totals[key].duration_s += float(duration_s)
        else:
            totals[key] = CategoryBreakdown(key=key, label=label, duration_s=float(duration_s))

    return DayResponse(
        metrics=DailyMetricsOut.model_validate(metrics, from_attributes=True),
        categories=sorted(totals.values(), key=lambda c: c.duration_s, reverse=True),
    )


@router.get("/{local_date}/timeline", response_model=TimelineResponse)
async def get_day_timeline(
    local_date: date_type,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    metrics = await _ensure_computed(db, user, local_date)

    devices = (
        (await db.execute(select(Device).where(Device.user_id == user.id))).scalars().all()
    )

    device_timelines = []
    for device in devices:
        coverage_rows = (
            (
                await db.execute(
                    select(DeviceCoverage)
                    .where(
                        DeviceCoverage.device_id == device.id,
                        DeviceCoverage.start_ts >= metrics.day_start_utc,
                        DeviceCoverage.start_ts < metrics.day_end_utc,
                    )
                    .order_by(DeviceCoverage.start_ts)
                )
            )
            .scalars()
            .all()
        )
        session_rows = (
            (
                await db.execute(
                    select(AppSessionRow)
                    .where(
                        AppSessionRow.device_id == device.id,
                        AppSessionRow.start_ts >= metrics.day_start_utc,
                        AppSessionRow.start_ts < metrics.day_end_utc,
                    )
                    .order_by(AppSessionRow.start_ts)
                )
            )
            .scalars()
            .all()
        )
        if not coverage_rows and not session_rows:
            continue  # this device had no activity at all on this day — omit rather than pad
        device_timelines.append(
            DeviceTimelineOut(
                device_id=str(device.id),
                name=device.name,
                coverage=[
                    CoverageIntervalOut(start_ts=c.start_ts, end_ts=c.end_ts, state=c.state)
                    for c in coverage_rows
                ],
                sessions=[
                    AppSessionOut(
                        app_key=s.app_key,
                        start_ts=s.start_ts,
                        end_ts=s.end_ts,
                        duration_s=float(s.duration_s),
                        interaction_count=s.interaction_count,
                    )
                    for s in session_rows
                ],
            )
        )

    return TimelineResponse(local_date=local_date, devices=device_timelines)


@router.get("/{local_date}/focus", response_model=FocusResponse)
async def get_day_focus(
    local_date: date_type,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FocusResponse:
    metrics = await _ensure_computed(db, user, local_date)

    rows = (
        (
            await db.execute(
                select(FocusSessionRow, ActivityCategory.key, ActivityCategory.label)
                .join(ActivityCategory, ActivityCategory.id == FocusSessionRow.category_id)
                .where(
                    FocusSessionRow.user_id == user.id,
                    FocusSessionRow.start_ts >= metrics.day_start_utc,
                    FocusSessionRow.start_ts < metrics.day_end_utc,
                )
                .order_by(FocusSessionRow.start_ts)
            )
        )
        .all()
    )

    return FocusResponse(
        local_date=local_date,
        sessions=[
            FocusSessionOut(
                category_key=key,
                category_label=label,
                start_ts=row.start_ts,
                end_ts=row.end_ts,
                duration_s=float(row.duration_s),
                interruption_count=row.interruption_count,
                tool_switch_count=row.tool_switch_count,
                attributed_ratio=float(row.attributed_ratio),
                is_deep_work=row.is_deep_work,
            )
            for row, key, label in rows
        ],
    )


@router.get("/{local_date}/activities", response_model=ActivitiesResponse)
async def get_day_activities(
    local_date: date_type,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivitiesResponse:
    """§15.4's correction unit: one row per `activities` entry, with the app_key(s) that made it
    up resolved via `source_session_ids` — what the "Where Time Went" view's correction
    affordance actually targets (not an app or a category, which have no single stable id)."""
    metrics = await _ensure_computed(db, user, local_date)

    rows = (
        (
            await db.execute(
                select(Activity, ActivityCategory.key, ActivityCategory.label)
                .join(ActivityCategory, ActivityCategory.id == Activity.category_id)
                .where(
                    Activity.user_id == user.id,
                    Activity.start_ts >= metrics.day_start_utc,
                    Activity.start_ts < metrics.day_end_utc,
                )
                .order_by(Activity.start_ts)
            )
        )
        .all()
    )

    all_session_ids = {sid for activity, _k, _l in rows for sid in activity.source_session_ids}
    app_keys_by_session_id: dict = {}
    if all_session_ids:
        session_rows = (
            await db.execute(
                select(AppSessionRow.id, AppSessionRow.app_key).where(
                    AppSessionRow.id.in_(all_session_ids)
                )
            )
        ).all()
        app_keys_by_session_id = dict(session_rows)

    return ActivitiesResponse(
        local_date=local_date,
        activities=[
            ActivityOut(
                id=str(activity.id),
                category_key=key,
                category_label=label,
                app_keys=sorted(
                    {
                        app_keys_by_session_id[sid]
                        for sid in activity.source_session_ids
                        if sid in app_keys_by_session_id
                    }
                ),
                start_ts=activity.start_ts,
                end_ts=activity.end_ts,
                duration_s=float(activity.duration_s),
                confidence=float(activity.confidence),
                classification_source=activity.classification_source,
            )
            for activity, key, label in rows
        ],
    )
