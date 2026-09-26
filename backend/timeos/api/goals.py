"""GET/POST/PATCH /v1/goals — §12.2's Goal CRUD, §38 Phase 6 output.

No dedicated mapping endpoint exists in the spec's API table, so a goal's
`goal_activity_mapping` rows travel with the goal itself: POST/PATCH's `mappings` field, when
supplied, REPLACES the goal's full mapping set (see timeos.schemas.goals's module docstring).
Goals are archived, never deleted (§38 failure case: "archived goals in historical windows" —
their alignment history must remain reconstructable), so there's no DELETE here; PATCH with
`archived: true` is how a goal is retired.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.analytics.goals import GoalMapping, attainment_ratio
from timeos.api.deps import enforce_csrf, get_current_user, get_db
from timeos.jobs.goal_alignment import compute_goal_alignment
from timeos.jobs.seed_categories import ensure_system_categories
from timeos.models.activity_category import ActivityCategory
from timeos.models.goal import Goal
from timeos.models.goal_activity_mapping import GoalActivityMapping
from timeos.models.user import User
from timeos.schemas.goals import (
    GoalAlignmentResponse,
    GoalCreateRequest,
    GoalMappingIn,
    GoalMappingOut,
    GoalResponse,
    GoalUpdateRequest,
)

VALID_ALIGNMENT_WINDOWS = frozenset({7, 30, 90})  # mirrors §12.2's `/v1/trends?window=7|30|90`

router = APIRouter(prefix="/v1/goals", tags=["goals"])


async def _validate_category_ids(
    db: AsyncSession, user_id: uuid.UUID, mappings: list[GoalMappingIn]
) -> None:
    category_ids = {m.category_id for m in mappings if m.category_id is not None}
    if not category_ids:
        return
    rows = (
        await db.execute(
            select(ActivityCategory.id).where(
                ActivityCategory.user_id == user_id, ActivityCategory.id.in_(category_ids)
            )
        )
    ).scalars().all()
    missing = category_ids - set(rows)
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown category_id(s): {', '.join(str(m) for m in missing)}",
        )


async def _replace_mappings(
    db: AsyncSession, goal_id: uuid.UUID, mappings: list[GoalMappingIn]
) -> list[GoalActivityMapping]:
    await db.execute(delete(GoalActivityMapping).where(GoalActivityMapping.goal_id == goal_id))
    rows = [
        GoalActivityMapping(
            goal_id=goal_id, category_id=m.category_id, app_key=m.app_key, weight=m.weight
        )
        for m in mappings
    ]
    db.add_all(rows)
    await db.flush()
    return rows


async def _load_mappings(db: AsyncSession, goal_id: uuid.UUID) -> list[GoalActivityMapping]:
    return list(
        (
            await db.execute(
                select(GoalActivityMapping).where(GoalActivityMapping.goal_id == goal_id)
            )
        )
        .scalars()
        .all()
    )


def _to_response(goal: Goal, mappings: list[GoalActivityMapping]) -> GoalResponse:
    return GoalResponse(
        id=goal.id,
        name=goal.name,
        priority=goal.priority,
        target_minutes_per_week=float(goal.target_minutes_per_week),
        target_behavior=goal.target_behavior,
        active_from=goal.active_from,
        active_to=goal.active_to,
        archived=goal.archived_at is not None,
        mappings=[
            GoalMappingOut(
                id=m.id, category_id=m.category_id, app_key=m.app_key, weight=float(m.weight)
            )
            for m in mappings
        ],
    )


async def _get_owned_goal(db: AsyncSession, user_id: uuid.UUID, goal_id: uuid.UUID) -> Goal:
    goal = await db.get(Goal, goal_id)
    if goal is None or goal.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "goal not found")
    return goal


@router.get("", response_model=list[GoalResponse])
async def list_goals(
    include_archived: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GoalResponse]:
    query = select(Goal).where(Goal.user_id == user.id)
    if not include_archived:
        query = query.where(Goal.archived_at.is_(None))
    goals = (await db.execute(query.order_by(Goal.priority, Goal.created_at))).scalars().all()

    responses = []
    for goal in goals:
        mappings = await _load_mappings(db, goal.id)
        responses.append(_to_response(goal, mappings))
    return responses


@router.post("", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
async def create_goal(
    body: GoalCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(enforce_csrf),
) -> GoalResponse:
    await _validate_category_ids(db, user.id, body.mappings)

    goal = Goal(
        user_id=user.id,
        name=body.name,
        priority=body.priority,
        target_minutes_per_week=body.target_minutes_per_week,
        target_behavior=body.target_behavior,
        active_from=body.active_from,
        active_to=body.active_to,
    )
    db.add(goal)
    await db.flush()

    mappings = await _replace_mappings(db, goal.id, body.mappings)
    await db.commit()
    return _to_response(goal, mappings)


@router.patch("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: uuid.UUID,
    body: GoalUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(enforce_csrf),
) -> GoalResponse:
    goal = await _get_owned_goal(db, user.id, goal_id)

    if body.mappings is not None:
        await _validate_category_ids(db, user.id, body.mappings)

    if body.name is not None:
        goal.name = body.name
    if body.priority is not None:
        goal.priority = body.priority
    if body.target_minutes_per_week is not None:
        goal.target_minutes_per_week = body.target_minutes_per_week
    if body.target_behavior is not None:
        goal.target_behavior = body.target_behavior
    if body.active_from is not None:
        goal.active_from = body.active_from
    if body.active_to is not None:
        goal.active_to = body.active_to
    if body.archived is not None:
        goal.archived_at = datetime.now(UTC) if body.archived else None

    if body.mappings is not None:
        mappings = await _replace_mappings(db, goal.id, body.mappings)
    else:
        mappings = await _load_mappings(db, goal.id)

    await db.commit()
    return _to_response(goal, mappings)


@router.get("/{goal_id}/alignment", response_model=GoalAlignmentResponse)
async def get_goal_alignment(
    goal_id: uuid.UUID,
    window: int = 7,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GoalAlignmentResponse:
    if window not in VALID_ALIGNMENT_WINDOWS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "window must be one of 7, 30, 90"
        )

    goal = await _get_owned_goal(db, user.id, goal_id)
    mapping_rows = await _load_mappings(db, goal.id)
    mappings = [
        GoalMapping(category_id=m.category_id, app_key=m.app_key, weight=float(m.weight))
        for m in mapping_rows
    ]

    category_key_to_id = await ensure_system_categories(db, user.id)
    result, avg_coverage_ratio = await compute_goal_alignment(
        db, user, mappings, category_key_to_id, window
    )
    target_minutes = float(goal.target_minutes_per_week) * (window / 7.0)

    return GoalAlignmentResponse(
        goal_id=goal.id,
        window_days=window,
        target_minutes=target_minutes,
        aligned_minutes=result.aligned_minutes,
        range_low_minutes=result.range_low_minutes,
        range_high_minutes=result.range_high_minutes,
        attainment_ratio=attainment_ratio(result.aligned_minutes, target_minutes),
        coverage_ratio=avg_coverage_ratio,
    )
