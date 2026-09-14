"""Liveness/readiness endpoints (§29) plus §25's System Health collector view."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.api.deps import get_current_user, get_db
from timeos.db import check_ready
from timeos.models.device import Device
from timeos.models.sync_batch import SyncBatch
from timeos.models.user import User
from timeos.schemas.health import CollectorHealth, CollectorsHealthResponse

router = APIRouter(prefix="/v1/health", tags=["health"])


@router.get("/live")
async def live() -> dict:
    """Process is up. Never checks the database — that's /ready's job."""
    return {"status": "live"}


@router.get("/ready")
async def ready(response: Response) -> dict:
    """Database reachable. Docker Compose healthchecks and the deploy script poll this."""
    ok = await check_ready()
    if not ok:
        response.status_code = 503
        return {"status": "not_ready"}
    return {"status": "ready"}


@router.get("/collectors", response_model=CollectorsHealthResponse)
async def collectors(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectorsHealthResponse:
    devices = (await db.execute(select(Device).where(Device.user_id == user.id))).scalars().all()

    device_ids = [d.id for d in devices]
    rejected_counts = dict(
        (
            await db.execute(
                select(SyncBatch.device_id, func.count())
                .where(SyncBatch.device_id.in_(device_ids), SyncBatch.status == "rejected")
                .group_by(SyncBatch.device_id)
            )
        ).all()
    )

    return CollectorsHealthResponse(
        collectors=[
            CollectorHealth(
                device_id=str(device.id),
                name=device.name,
                platform=device.platform,
                last_seen_at=device.last_seen_at,
                last_seq=device.last_seq,
                revoked=device.revoked_at is not None,
                rejected_batch_count=rejected_counts.get(device.id, 0),
            )
            for device in devices
        ]
    )
