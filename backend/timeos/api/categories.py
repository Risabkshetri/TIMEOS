"""GET/POST/PATCH /v1/categories — §38 Phase 6 output "custom taxonomy". See
timeos.schemas.categories's docstring for scope: additions and renames on top of the seeded
default taxonomy, never touching `is_system` rows."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.api.deps import enforce_csrf, get_current_user, get_db
from timeos.models.activity_category import ActivityCategory
from timeos.models.user import User
from timeos.schemas.categories import (
    CategoryCreateRequest,
    CategoryResponse,
    CategoryUpdateRequest,
)

router = APIRouter(prefix="/v1/categories", tags=["categories"])


def _to_response(row: ActivityCategory) -> CategoryResponse:
    return CategoryResponse(
        id=row.id, key=row.key, label=row.label, parent_id=row.parent_id, is_system=row.is_system
    )


async def _get_owned_category(
    db: AsyncSession, user_id: uuid.UUID, category_id: uuid.UUID
) -> ActivityCategory:
    row = await db.get(ActivityCategory, category_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    return row


async def _validate_parent(
    db: AsyncSession, user_id: uuid.UUID, parent_id: uuid.UUID | None
) -> None:
    if parent_id is None:
        return
    parent = await db.get(ActivityCategory, parent_id)
    if parent is None or parent.user_id != user_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown parent_id")


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CategoryResponse]:
    rows = (
        (
            await db.execute(
                select(ActivityCategory)
                .where(ActivityCategory.user_id == user.id)
                .order_by(ActivityCategory.key)
            )
        )
        .scalars()
        .all()
    )
    return [_to_response(row) for row in rows]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(enforce_csrf),
) -> CategoryResponse:
    await _validate_parent(db, user.id, body.parent_id)

    existing = (
        await db.execute(
            select(ActivityCategory).where(
                ActivityCategory.user_id == user.id, ActivityCategory.key == body.key
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "a category with this key already exists")

    row = ActivityCategory(
        user_id=user.id,
        key=body.key,
        label=body.label,
        parent_id=body.parent_id,
        is_system=False,
    )
    db.add(row)
    await db.commit()
    return _to_response(row)


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: uuid.UUID,
    body: CategoryUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(enforce_csrf),
) -> CategoryResponse:
    row = await _get_owned_category(db, user.id, category_id)
    if row.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "system categories are immutable")

    if body.parent_id is not None:
        await _validate_parent(db, user.id, body.parent_id)
        row.parent_id = body.parent_id
    if body.label is not None:
        row.label = body.label

    await db.commit()
    return _to_response(row)
