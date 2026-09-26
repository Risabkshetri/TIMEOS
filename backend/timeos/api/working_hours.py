"""GET/PUT /v1/working-hours — §38 Phase 6 output "working hours", backing §18's alignment engine
and §19's Personal Context Engine. See timeos.schemas.working_hours's docstring for why this
exists despite not being in §12.2's endpoint table, and why PUT replaces the whole week."""

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.api.deps import enforce_csrf, get_current_user, get_db
from timeos.models.user import User
from timeos.models.working_hours import WorkingHours
from timeos.schemas.working_hours import WorkingHoursEntry, WorkingHoursReplaceRequest

router = APIRouter(prefix="/v1/working-hours", tags=["working-hours"])


@router.get("", response_model=list[WorkingHoursEntry])
async def get_working_hours(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkingHoursEntry]:
    rows = (
        (
            await db.execute(
                select(WorkingHours)
                .where(WorkingHours.user_id == user.id)
                .order_by(WorkingHours.weekday)
            )
        )
        .scalars()
        .all()
    )
    return [
        WorkingHoursEntry(weekday=r.weekday, start_local=r.start_local, end_local=r.end_local)
        for r in rows
    ]


@router.put("", response_model=list[WorkingHoursEntry])
async def replace_working_hours(
    body: WorkingHoursReplaceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(enforce_csrf),
) -> list[WorkingHoursEntry]:
    await db.execute(delete(WorkingHours).where(WorkingHours.user_id == user.id))
    db.add_all(
        [
            WorkingHours(
                user_id=user.id,
                weekday=e.weekday,
                start_local=e.start_local,
                end_local=e.end_local,
            )
            for e in body.entries
        ]
    )
    await db.commit()
    return body.entries
